import os
import time
import logging
import gradio as gr
from gcp_storage import initialize_gcp_credentials
from models import SessionLocal, Job, init_db
from job_manager import start_worker
from sqlalchemy import desc
import datetime
import shutil
import uuid
import json
import random
import numpy as np

# -------------------- 
# Configure Logging
# --------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configure logging for imported modules
logging.getLogger('job_manager').setLevel(logging.INFO)
logging.getLogger('services').setLevel(logging.INFO)

# -------------------- 
# Initialize database
# -------------------- 
try:
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialization complete")
except Exception as e:
    logger.critical(f"Database initialization failed: {e}")
    raise

# -------------------- 
# Configuration
# -------------------- 
SHARED_DIR = os.environ.get("SHARED_DIR", "/shared_data")
CHECKPOINT = os.environ.get("MODEL_CHECKPOINT", "/app/checkpoints/checkpoint.pth")
GEN_SEED = int(os.environ.get("GENERATION_SEED", "0"))

logger.info(f"Using shared directory: {SHARED_DIR}")
logger.info(f"Using checkpoint: {CHECKPOINT}")
logger.info(f"Using generation seed: {GEN_SEED}")

# Global variable to track current job
current_job_id = None

# Start background worker
try:
    logger.info("Starting background worker...")
    start_worker(CHECKPOINT, GEN_SEED, SHARED_DIR)
    logger.info("Background worker started")
except Exception as e:
    logger.critical(f"Failed to start background worker: {e}")
    raise

# -------------------- 
# Helper Functions
# -------------------- 
def create_job_directories(job_id):
    """Create job-specific directories for input, melody, and vocal results"""
    # Create job-specific directories
    job_input_dir = os.path.join(SHARED_DIR, "input", f"job_{job_id}")
    job_melody_dir = os.path.join(SHARED_DIR, "melody_results", f"job_{job_id}")
    job_vocal_dir = os.path.join(SHARED_DIR, "vocal_results", f"job_{job_id}")
    
    # Create directories if they don't exist
    os.makedirs(job_input_dir, exist_ok=True)
    os.makedirs(job_melody_dir, exist_ok=True)
    os.makedirs(job_vocal_dir, exist_ok=True)
    
    logger.info(f"Created job directories for job {job_id}")
    
    return job_input_dir, job_melody_dir, job_vocal_dir

def calculate_job_duration(job):
    """Calculate the duration of a job in seconds"""
    if not job.created_at or not job.updated_at:
        return None
    
    duration = (job.updated_at - job.created_at).total_seconds()
    return duration

def format_duration(seconds):
    """Format duration in seconds to a human-readable string"""
    if seconds is None:
        return "Unknown"
    
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"

def load_audio_file(file_path):
    """
    Load audio data from a file path.
    Returns a tuple of (sample_rate, audio_data) or None if the file doesn't exist.
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"Audio file not found: {file_path}")
        return None
    
    try:
        from scipy.io import wavfile
        
        # Check if the file is an MP3
        if file_path.lower().endswith('.mp3'):
            # For MP3 files, we need to convert them to WAV first
            try:
                import tempfile
                import subprocess
                
                # Create a temporary WAV file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                    temp_wav_path = temp_wav.name
                
                # Convert MP3 to WAV using ffmpeg
                subprocess.run(
                    ["ffmpeg", "-i", file_path, "-acodec", "pcm_s16le", "-ar", "44100", temp_wav_path],
                    check=True,
                    capture_output=True
                )
                
                # Read the WAV file
                sample_rate, audio_data = wavfile.read(temp_wav_path)
                
                # Clean up the temporary file
                os.unlink(temp_wav_path)
                
                return (sample_rate, audio_data)
                
            except Exception as e:
                logger.error(f"Error converting MP3 to WAV: {str(e)}")
                return None
        else:
            # For WAV files, read directly
            sample_rate, audio_data = wavfile.read(file_path)
            return (sample_rate, audio_data)
            
    except Exception as e:
        logger.error(f"Error loading audio file {file_path}: {str(e)}")
        return None

def copy_to_temp(file_path):
    """Copy a file to the temp directory to make it accessible to Gradio"""
    if not file_path or not os.path.exists(file_path):
        return None
        
    # Create a temp directory if it doesn't exist
    temp_dir = "/tmp/melody_generator"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Create a new filename in the temp directory
    filename = os.path.basename(file_path)
    temp_path = os.path.join(temp_dir, filename)
    
    # Copy the file
    try:
        shutil.copy2(file_path, temp_path)
        logger.info(f"Copied {file_path} to {temp_path} for Gradio access")
        return temp_path
    except Exception as e:
        logger.error(f"Failed to copy file to temp directory: {str(e)}")
        return None

# -------------------- 
# Job Polling Function
# -------------------- 
def poll_job_status(job_id, progress=None):
    """Poll the job status until it's completed or failed"""
    session = SessionLocal()
    max_attempts = 120  # 5 minutes (5s * 60)
    attempt = 0
    
    try:
        while attempt < max_attempts:
            # Get a fresh session for each check to avoid stale data
            if session:
                session.close()
            session = SessionLocal()
            
            job = session.query(Job).filter(Job.id == job_id).first()
            
            if not job:
                logger.error(f"Job {job_id} not found in database")
                return None, "failed"
            
            logger.info(f"Polling job {job_id}, current status: {job.status}")
            
            if job.status == "completed":
                logger.info(f"Job {job_id} completed successfully")
                return job.output_file, job.status
            
            if job.status == "failed":
                logger.error(f"Job {job_id} failed")
                return None, "failed"
            
            # Simple progress update without trying to set a specific value
            if progress is not None:
                try:
                    # Just update the message without trying to set a specific progress value
                    progress(None, f"Processing job {job_id}... (Attempt {attempt+1}/{max_attempts})")
                except Exception as e:
                    logger.warning(f"Failed to update progress: {e}")
            
            # Close the session before sleeping to avoid keeping it open too long
            session.close()
            session = None
            
            attempt += 1
            time.sleep(5)
        
        # If we get here, the job timed out
        logger.warning(f"Job {job_id} timed out after {max_attempts * 5} seconds")
        return None, "timeout"
    
    finally:
        if session:
            session.close()

# -------------------- 
# Recent Jobs Function
# -------------------- 
def get_recent_jobs():
    """Get a list of recent jobs for display in a table format with detailed file listings"""
    global current_job_id
    
    session = SessionLocal()
    try:
        jobs = session.query(Job).order_by(desc(Job.created_at)).limit(10).all()
        
        if not jobs:
            return "No recent jobs"
        
        # Create a table header with clean styling and toggle switch
        table_html = """
        <style>
        .job-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .job-table th, .job-table td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .current-job {
            font-weight: bold;
        }
        .status-completed {
            color: #10b981;
        }
        .status-failed {
            color: #ef4444;
        }
        .status-processing {
            color: #f59e0b;
        }
        .status-pending {
            color: #6b7280;
        }
        .file-list {
            max-height: 120px;
            overflow-y: auto;
            margin-top: 5px;
            border: 0px solid #ddd;
            border-radius: 5px;
            padding: 4px;
        }
        .file-item {
            display: flex;
            align-items: center;
            padding: 6px 10px;
            border-bottom: 1px solid #eee;
            text-decoration: none;
            color: #4b5563;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .file-item:last-child {
            border-bottom: none;
        }
        .file-item:hover {
            color: #2563eb;
        }
        .file-icon {
            margin-right: 6px;
            font-size: 1rem;
        }
        
        /* Toggle switch */
        .switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 24px;
        }
        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 24px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background-color: #2563eb;
        }
        input:checked + .slider:before {
            transform: translateX(36px);
        }
        .toggle-label {
            display: inline-flex;
            align-items: center;
            margin-bottom: 8px;
        }
        .toggle-text {
            margin-right: 10px;
        }
        </style>
        <table class="job-table">
            <thead>
                <tr>
                    <th>Job ID</th>
                    <th>Status</th>
                    <th>Processing Time</th>
                    <th>Parameters</th>
                    <th>Files</th>
                </tr>
            </thead>
            <tbody>
        """
        
        # Add rows for each job
        for job in jobs:
            # Calculate and format job duration
            duration = calculate_job_duration(job)
            duration_display = format_duration(duration) if duration else "In progress"
            
            # Add emoji and class based on status
            if job.status == "completed":
                status_emoji = "✅"
                status_class = "status-completed"
            elif job.status == "failed":
                status_emoji = "❌"
                status_class = "status-failed"
            elif job.status == "processing":
                status_emoji = "⏳"
                status_class = "status-processing"
            else:
                status_emoji = "⏱️"
                status_class = "status-pending"
            
            # Highlight current job
            row_class = "current-job" if current_job_id and job.id == current_job_id else ""
            
            # Format parameters for display
            parameters = job.parameters.replace(",", ", ") if job.parameters else "None"
            
            # Extract GCP URLs from dedicated JSON column
            gcp_urls = {}
            if job.gcp_urls_json:
                try:
                    gcp_urls = json.loads(job.gcp_urls_json)
                except Exception as e:
                    logger.error(f"Error parsing GCP URLs JSON: {str(e)}")
                    
                    # Fallback: If we have a parameter with gcp_urls_json
                    if job.parameters and "gcp_urls_json=" in job.parameters:
                        try:
                            # Extract the JSON string from the parameters - this is legacy support
                            params_dict = {}
                            for param in job.parameters.split(','):
                                if '=' in param:
                                    key, value = param.split('=', 1)
                                    params_dict[key] = value
                                    
                            if 'gcp_urls_json' in params_dict:
                                gcp_urls = json.loads(params_dict['gcp_urls_json'])
                        except Exception as e:
                            logger.error(f"Fallback parsing also failed: {str(e)}")
            
            # Create file listings HTML with toggle switch
            file_count = len(gcp_urls)
            files_html = ""
            
            if gcp_urls:
                toggle_id = f"toggle-job-{job.id}-files"
                container_id = f"job-{job.id}-files"
                
                files_html = f"""
                <div class="toggle-label">
                    <span class="toggle-text">Show/Hide Files</span>
                    <label class="switch">
                        <input type="checkbox" id="{toggle_id}" onchange="document.getElementById('{container_id}').style.display = this.checked ? 'block' : 'none';">
                        <span class="slider"></span>
                    </label>
                </div>
                <div id="{container_id}" class="file-list" style="display: none;">
                """
                
                # Loop through all files and create a vertical list with just filenames
                for key, url in gcp_urls.items():
                    # Determine file type icon based on extension
                    file_icon = "📄"  # Default icon
                    
                    # Get basic file extension
                    if ".mid" in key:
                        file_icon = "🎹"  # MIDI
                    elif ".wav" in key:
                        file_icon = "🔊"  # Audio
                    elif ".json" in key:
                        file_icon = "📋"  # JSON
                    
                    # Just use the filename as is - no mapping
                    files_html += f"""
                    <a href="{url}" target="_blank" class="file-item" title="{key}">
                        <span class="file-icon">{file_icon}</span> {key}
                    </a>
                    """
                
                files_html += "</div>"
            else:
                files_html = "No files available"
            
            table_html += f"""
            <tr class="{row_class}">
                <td>{job.id}</td>
                <td class="{status_class}">{status_emoji} {job.status}</td>
                <td>{duration_display}</td>
                <td>{parameters}</td>
                <td>{files_html}</td>
            </tr>
            """
        
        table_html += """
            </tbody>
        </table>
        """
        
        return table_html
    finally:
        session.close()

        
# Function to get current job status
def get_current_job_status():
    """Get the status of the current job if one exists"""
    global current_job_id
    
    if not current_job_id:
        return "No active job"
    
    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == current_job_id).first()
        
        if not job:
            return f"Job {current_job_id} not found"
        
        # Calculate duration
        duration = calculate_job_duration(job)
        duration_display = f" ({format_duration(duration)})" if duration else ""
        
        # Add emoji based on status
        if job.status == "completed":
            status_emoji = "✅"
        elif job.status == "failed":
            status_emoji = "❌"
        elif job.status == "processing":
            status_emoji = "⏳"
        else:
            status_emoji = "⏱️"
            
        return f"Current Job {job.id}: {status_emoji} {job.status}{duration_display}"
    finally:
        session.close()

# -------------------- 
# Gradio UI Functions
# -------------------- 
def process_audio(file, start_time, bpm, seed, randomize_seed, model_set, voice_type, enable_batch_mode=False, progress=gr.Progress()):
    global current_job_id
    
    if file is None:
        logger.warning("Job submission attempted with no file")
        return "⚠️ Please upload a backing track first", None, None, None, None, None, None, get_recent_jobs(), get_current_job_status()
    
    # Validate inputs
    if start_time > 0 and (not bpm or bpm <= 0):
        error = "If start_time is greater than 0, BPM must also be greater than 0."
        logger.warning(error)
        return error, None, None, None, None, None, None, get_recent_jobs(), get_current_job_status()
    
    try:
        progress(0, "Initializing...")
        
        # Set batch size based on enable_batch_mode checkbox and model_set
        # Only enable batch mode for model set 2 ("new")
        batch_size = 3 if enable_batch_mode and model_set == "set2" else 1
        
        # Handle randomized seed if checkbox is checked (for single track mode only)
        if randomize_seed and batch_size == 1:
            seed = random.randint(0, 10000)
            logger.info(f"Randomized seed to: {seed}")
        
        # Create a new job record in the database first to get the job ID
        session = SessionLocal()
        job = Job(
            status="pending",
            parameters=f"start_time={start_time},bpm={bpm},seed={seed},model_set={model_set},sex={voice_type},batch_size={batch_size}"
        )
        session.add(job)
        session.commit()
        job_id = job.id
        current_job_id = job_id  # Set the global current job ID
        logger.info(f"Created job {job_id} with model_set={model_set}, voice_type={voice_type}, batch_size={batch_size}")
        
        # Create job-specific directories
        job_input_dir, job_melody_dir, job_vocal_dir = create_job_directories(job_id)
        
        # Process the input file
        progress(0.1, "Processing audio file...")
        
        # Fix for the file.name error - handle both string paths and file objects
        if isinstance(file, str):
            original_filename = os.path.basename(file)
        else:
            original_filename = os.path.basename(file.name)
            
        # Remove file extension for use in output filenames
        input_filename_base, input_ext = os.path.splitext(original_filename)
        
        # Create job-specific input filename
        job_input_filename = f"job_{job_id}_{input_filename_base}{input_ext}"
        file_path = os.path.join(job_input_dir, job_input_filename)
        
        # Handle both string paths and file objects
        if isinstance(file, str):
            # If file is already a path, just copy it
            shutil.copy2(file, file_path)
        else:
            # Otherwise read and write the file
            with open(file_path, "wb") as f:
                f.write(file.read())
        
        logger.info(f"File saved to {file_path}")
        
        # Verify the file exists and has content
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Failed to save file to {file_path}")
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError(f"Saved file is empty: {file_path}")
            
        logger.info(f"File saved successfully: {file_path} ({file_size} bytes)")
        
        # Update the job with the input file path
        session = SessionLocal()
        job = session.query(Job).filter(Job.id == job_id).first()
        job.input_file = file_path
        session.commit()
        session.close()
        
        # Update the recent jobs display
        recent_jobs_html = get_recent_jobs()
        current_job_status = get_current_job_status()
        
        # Poll for job completion
        progress(0.3, f"Job submitted (ID: {job_id}). Waiting for processing...")
        output_file, status = poll_job_status(job_id, progress)

        # Process the results
        if status == "completed":
            # Generate a unique ID for this generation
            unique_id = str(uuid.uuid4())[:8]
            
            # Get the original filename base (without extension)
            if isinstance(file, str):
                original_filename = os.path.basename(file)
            else:
                original_filename = os.path.basename(file.name)
            
            input_filename_base, input_ext = os.path.splitext(original_filename)
            
            # Handle batch mode differently
            if batch_size > 1:
                # Get variant mix paths from job parameters
                session = SessionLocal()
                job = session.query(Job).filter(Job.id == job_id).first()
                
                variant_mixes = {}
                if job and job.variant_mixes_json:
                    try:
                        variant_mixes = json.loads(job.variant_mixes_json)
                        logger.info(f"Found variant mixes in job.variant_mixes_json: {list(variant_mixes.keys())}")
                    except Exception as e:
                        logger.error(f"Error parsing variant_mixes_json: {str(e)}")
                
                # If no variants were found in the JSON column, try to find them based on directory structure
                if not variant_mixes:
                    logger.info("No variant mixes found in job.variant_mixes_json, searching directories...")
                    model_suffix = f"_{model_set}"
                    
                    # Search for variant directories and files
                    for i in range(1, batch_size + 1):
                        variant_dir = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}", f"variant_{i}")
                        if os.path.exists(variant_dir):
                            # Look for mix files with different possible names
                            possible_mix_files = [
                                os.path.join(variant_dir, "mix.wav"),
                                os.path.join(variant_dir, "mix.mp3"),
                                # Add more patterns if needed
                            ]
                            
                            # Also look for any file with "mix" in the name
                            for file in os.listdir(variant_dir):
                                if "mix" in file.lower() and (file.endswith(".wav") or file.endswith(".mp3")):
                                    possible_mix_files.append(os.path.join(variant_dir, file))
                            
                            # Check each possible mix file
                            for mix_file in possible_mix_files:
                                if os.path.exists(mix_file):
                                    variant_mixes[f"variant_{i}"] = mix_file
                                    logger.info(f"Found variant mix: {mix_file}")
                                    break
                
                session.close()
           
                # If no variants were found, try to find them based on directory structure
                if not variant_mixes:
                    logger.info("No variant mixes found in job parameters, searching directories...")
                    model_suffix = f"_{model_set}"
                    for i in range(batch_size):
                        variant_dir = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}", f"variant_{i+1}")
                        if os.path.exists(variant_dir):
                            mix_file = os.path.join(variant_dir, "mix.wav")
                            if os.path.exists(mix_file):
                                variant_mixes[f"variant_{i+1}"] = mix_file
                                logger.info(f"Found variant mix: {mix_file}")
                
                # If still no variants found, try looking for MP3 files specifically
                if not variant_mixes:
                    logger.info("No variant mixes found with .wav extension, trying .mp3 files...")
                    for i in range(1, batch_size + 1):
                        variant_dir = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}", f"variant_{i}")
                        if os.path.exists(variant_dir):
                            # Look specifically for MP3 files
                            for file in os.listdir(variant_dir):
                                if file.endswith(".mp3") and ("mix" in file.lower() or "melody" in file.lower()):
                                    mp3_path = os.path.join(variant_dir, file)
                                    variant_mixes[f"variant_{i}"] = mp3_path
                                    logger.info(f"Found variant MP3 mix: {mp3_path}")
                                    break
                
                # Look for beat mix file
                beat_mix_path = os.path.join(SHARED_DIR, f"melody_results_{model_set}", f"job_{job_id}", "beat_mixed_synth_mix.wav")
                if not os.path.exists(beat_mix_path):
                    beat_mix_path = None
                    
                    # Try alternative locations
                    alternative_beat_mix_paths = [
                        os.path.join(SHARED_DIR, f"melody_results_{model_set}", "beat_mixed_synth_mix.wav"),
                        os.path.join(SHARED_DIR, f"melody_results", f"job_{job_id}", "beat_mixed_synth_mix.wav")
                    ]
                    
                    for path in alternative_beat_mix_paths:
                        if os.path.exists(path):
                            beat_mix_path = path
                            logger.info(f"Found beat mix file at alternative location: {beat_mix_path}")
                            break
                
                # Prepare the variants for display
                variant1 = variant_mixes.get("variant_1", None)
                variant2 = variant_mixes.get("variant_2", None)
                variant3 = variant_mixes.get("variant_3", None)
                
                if variant1 or variant2 or variant3:
                    success_message = f"✅ Generated {len(variant_mixes)} melody variants! (Job ID: {job_id}, Model: {model_set}, Voice: {voice_type})"
                    
                    # Update recent jobs display and current job status
                    recent_jobs_html = get_recent_jobs()
                    current_job_status = get_current_job_status()
                    
                    # Return the variants for display - in batch mode we don't show vocal or MIDI previews
                    return (
                        success_message, 
                        None,  # No vocal preview in batch mode
                        copy_to_temp(variant1) if variant1 else None,  # First variant as mixed preview
                        None,  # No MIDI preview in batch mode 
                        copy_to_temp(beat_mix_path) if beat_mix_path else None,
                        copy_to_temp(variant2) if variant2 else None,  # Second variant
                        copy_to_temp(variant3) if variant3 else None,  # Third variant
                        recent_jobs_html, 
                        current_job_status
                    )
                else:
                    error_message = f"⚠️ Job completed but no variant files found (Job ID: {job_id})"
                    return error_message, None, None, None, None, None, None, get_recent_jobs(), get_current_job_status()
            
            else:
                # Original single track processing logic
                # Define output filenames with the requested format
                model_display_name = "old" if model_set == "set1" else "new"
                vocal_filename = f"vocal_melody_{model_display_name}_{input_filename_base}_seed{seed}_{unique_id}.wav"
                mixed_filename = f"mixed_audio_{model_display_name}_{input_filename_base}_seed{seed}_{unique_id}.wav"
                midi_filename = f"melody_{model_display_name}_{input_filename_base}_seed{seed}_{unique_id}.mid"
                beat_mix_filename = f"beat_mix_{model_display_name}_{input_filename_base}_seed{seed}_{unique_id}.wav"
                
                # Add model set suffix to directories
                model_suffix = f"_{model_set}"
                
                # Define paths in job-specific directories
                vocal_path = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}", vocal_filename)
                mixed_path = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}", mixed_filename)
                midi_path = os.path.join(SHARED_DIR, f"melody_results{model_suffix}", f"job_{job_id}", midi_filename)
                beat_mix_path = os.path.join(SHARED_DIR, f"melody_results{model_suffix}", f"job_{job_id}", beat_mix_filename)
                
                # Get the original output paths
                if output_file:
                    output_dir = os.path.dirname(output_file)
                    vocal_melody_path = os.path.join(output_dir, "vocal.wav")
                    mixed_track_path = output_file  # This is the mix.wav file
                else:
                    logger.warning("Output file is None, using fallback paths")
                    output_dir = os.path.join(SHARED_DIR, f"vocal_results{model_suffix}", f"job_{job_id}")
                    vocal_melody_path = os.path.join(output_dir, "vocal.wav")
                    mixed_track_path = os.path.join(output_dir, "mix.wav")
                
                # Check multiple possible locations for the MIDI file
                possible_midi_paths = [
                    os.path.join(SHARED_DIR, f"melody_results{model_suffix}", "melody.mid"),
                    os.path.join(SHARED_DIR, f"melody_results{model_suffix}", f"job_{job_id}", "melody.mid"),
                    os.path.join(output_dir, "melody.mid")
                ]
                
                # Check multiple possible locations for the beat mix file
                possible_beat_mix_paths = [
                    os.path.join(SHARED_DIR, f"melody_results{model_suffix}", "beat_mixed_synth_mix.wav"),
                    os.path.join(SHARED_DIR, f"melody_results{model_suffix}", f"job_{job_id}", "beat_mixed_synth_mix.wav"),
                    os.path.join(output_dir, "beat_mixed_synth_mix.wav")
                ]
                
                midi_file_path = None
                for path in possible_midi_paths:
                    if os.path.exists(path):
                        midi_file_path = path
                        logger.info(f"Found MIDI file at: {midi_file_path}")
                        break
                
                beat_mix_file_path = None
                for path in possible_beat_mix_paths:
                    if os.path.exists(path):
                        beat_mix_file_path = path
                        logger.info(f"Found beat mix file at: {beat_mix_file_path}")
                        break
                
                # Copy files to job-specific directories if they exist
                files_copied = []
                
                if os.path.exists(vocal_melody_path):
                    os.makedirs(os.path.dirname(vocal_path), exist_ok=True)
                    shutil.copy2(vocal_melody_path, vocal_path)
                    logger.info(f"Copied vocal file to {vocal_path}")
                    files_copied.append("vocal")
                else:
                    logger.warning(f"Vocal file not found at {vocal_melody_path}")
                
                if os.path.exists(mixed_track_path):
                    os.makedirs(os.path.dirname(mixed_path), exist_ok=True)
                    shutil.copy2(mixed_track_path, mixed_path)
                    logger.info(f"Copied mixed file to {mixed_path}")
                    files_copied.append("mixed")
                else:
                    logger.warning(f"Mixed file not found at {mixed_track_path}")
                
                if midi_file_path and os.path.exists(midi_file_path):
                    os.makedirs(os.path.dirname(midi_path), exist_ok=True)
                    shutil.copy2(midi_file_path, midi_path)
                    logger.info(f"Copied MIDI file to {midi_path}")
                    files_copied.append("midi")
                else:
                    logger.warning("MIDI file not found in any of the expected locations")
                
                if beat_mix_file_path and os.path.exists(beat_mix_file_path):
                    os.makedirs(os.path.dirname(beat_mix_path), exist_ok=True)
                    shutil.copy2(beat_mix_file_path, beat_mix_path)
                    logger.info(f"Copied beat mix file to {beat_mix_path}")
                    files_copied.append("beat_mix")
                else:
                    logger.warning("Beat mix file not found in any of the expected locations")
                
                # Make sure the audio files are readable by the current user
                try:
                    for path in [vocal_path, mixed_path, midi_path, beat_mix_path]:
                        if os.path.exists(path):
                            os.chmod(path, 0o644)
                except Exception as e:
                    logger.warning(f"Could not set file permissions: {str(e)}")
                
                # Update the job record with the new output file path
                session = SessionLocal()
                job = session.query(Job).filter(Job.id == job_id).first()
                job.output_file = mixed_path if os.path.exists(mixed_path) else output_file
                session.commit()
                session.close()
                
                progress(1.0, "Generation complete!")
                
                # Consider the job successful if at least the mixed track is available
                if "mixed" in files_copied:
                    success_message = f"✅ Generation complete! (Job ID: {job_id}, Model: {model_set}, Voice: {voice_type})"
                    
                    # Log the paths being returned to the UI
                    if "vocal" in files_copied:
                        logger.info(f"Returning vocal path: {vocal_path}")
                    if "mixed" in files_copied:
                        logger.info(f"Returning mixed path: {mixed_path}")
                    if "midi" in files_copied:
                        logger.info(f"Returning MIDI path: {midi_path}")
                    if "beat_mix" in files_copied:
                        logger.info(f"Returning beat mix path: {beat_mix_path}")
                    
                    # Update recent jobs display and current job status
                    recent_jobs_html = get_recent_jobs()
                    current_job_status = get_current_job_status()
                    
                    # Return all outputs, using None for any missing files
                    # For non-batch mode, the variant outputs are None
                    return (
                        success_message, 
                        vocal_path if "vocal" in files_copied else None, 
                        mixed_path if "mixed" in files_copied else None, 
                        midi_path if "midi" in files_copied else None,
                        beat_mix_path if "beat_mix" in files_copied else None,
                        None,  # variant2 is None in single track mode
                        None,  # variant3 is None in single track mode
                        recent_jobs_html, 
                        current_job_status
                    )
                else:
                    error_message = f"⚠️ Job completed but essential files are missing (Job ID: {job_id})"
                    return error_message, None, None, None, None, None, None, get_recent_jobs(), get_current_job_status()

    except Exception as e:
        logger.error(f"Error generating melodies: {str(e)}", exc_info=True)
        return f"❌ Error: {str(e)}", None, None, None, None, None, None, get_recent_jobs(), get_current_job_status()


# Function to randomize the seed value
def randomize_seed_value():
    import random
    new_seed = random.randint(0, 10000)
    return gr.update(value=new_seed)

# -------------------- 
# Gradio Interface Setup
# -------------------- 
with gr.Blocks(title="Melody Generator") as demo:
    # Header section
    with gr.Row():
        with gr.Column(scale=3):
            gr.Markdown("# Melody Generator")
            gr.Markdown("Upload a backing track (WAV) to generate vocal melodies.")
        
        with gr.Column(scale=1, elem_id="status-panel"):
            gr.Markdown("### Current Job")
            current_job_status = gr.Markdown(get_current_job_status())
            refresh_btn = gr.Button("Refresh Status")
            refresh_btn.click(fn=get_current_job_status, outputs=current_job_status)

    # Main content
    with gr.Tabs():
        # Generate tab
        with gr.TabItem("Generate"):
            with gr.Row():
                # Left column - Input controls
                with gr.Column():
                    gr.Markdown("### Input")
                    file_input = gr.Audio(
                        label="Upload Backing Track (WAV)",
                        type="filepath"
                    )               

                    with gr.Accordion("Advanced Settings", open=False):
                        
                        gr.Markdown("#### Model Selection")
                        
                        with gr.Row():
                            model_set = gr.Radio(
                                label="Model Set",
                                choices=[("Old", "set1"), ("New", "set2")],
                                value="set1",
                                interactive=True
                            )
                            
                            voice_type = gr.Radio(
                                label="Voice Type",
                                choices=["female", "male"],
                                value="female",
                                interactive=True
                            )
                        
                        # New option for batch mode
                        enable_batch_mode = gr.Checkbox(
                            label="Generate Multiple Variants (New Model Only)",
                            value=False,
                            interactive=True
                        )
                        
                        # Help text for batch mode
                        batch_help = gr.Markdown(
                            "When enabled, 3 different melody variants will be generated with random seeds. "
                            "This feature only works with the New model. "
                            "Seed selection is disabled in this mode."
                        )

                        gr.Markdown("#### Beat Estimation")
                        gr.Markdown(
                            "You can optionally provide a start time and BPM for better control. "
                            "If left blank, the system will estimate these values automatically."
                        )
                        
                        with gr.Row():
                            start_time = gr.Number(
                                label="Song start time (seconds)",
                                value=0,
                                precision=2,
                                interactive=True
                            )
                            
                            bpm = gr.Number(
                                label="BPM (integer)",
                                value=0,
                                precision=0,
                                interactive=True
                            )
                        
                        # Seed controls in a group to control visibility
                        with gr.Group(elem_id="seed-controls") as seed_controls:
                            gr.Markdown("#### Randomization Control")
                            
                            with gr.Row():
                                seed = gr.Number(
                                    label="Seed (optional, integer)",
                                    value=0,
                                    precision=0,
                                    interactive=True
                                )
                                
                                randomize_seed = gr.Checkbox(
                                    label="Randomize Seed",
                                    value=True,
                                    interactive=True
                                )
                            
                            randomize_btn = gr.Button("New Random Seed")
                            randomize_btn.click(fn=randomize_seed_value, outputs=seed)
                    
                    status_message = gr.Markdown("Upload a track and click Generate.")
                    generate_btn = gr.Button("Generate Melodies", variant="primary", size="lg")
                
                # Right column - Preview outputs
                with gr.Column():
                    gr.Markdown("### Preview")
                    
                    # Single variant view (visible when batch mode is off)
                    with gr.Group(visible=True) as single_variant_view:
                        gr.Markdown("#### Vocal Melody")
                        vocal_preview = gr.Audio(
                            label="Vocal Track (WAV)",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=False,
                            show_download_button=True,
                        )

                        gr.Markdown("#### Mixed Track")
                        mixed_preview = gr.Audio(
                            label="Mixed Track (WAV)",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=True,
                            show_download_button=True,
                        )

                        gr.Markdown("#### Beat Estimation Mix")
                        beat_mix_preview = gr.Audio(
                            label="Beat Estimation Mix (WAV)",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=False,
                            show_download_button=True,
                        )
                        
                        gr.Markdown("#### MIDI File")
                        midi_preview = gr.File(
                            label="MIDI Melody",
                            value=None,  
                            interactive=False,
                            file_count="single",
                            type="filepath",
                        )
                    
                    # Multi-variant view (visible when batch mode is on)
                    with gr.Group(visible=False) as multi_variant_view:
                        gr.Markdown("### Melody Variants Comparison")
                        gr.Markdown("Listen to these three melody variants generated with different random seeds:")
                        
                        with gr.Row():
                            variant1_preview = gr.Audio(
                                label="Variant 1",
                                type="filepath",
                                value=None, 
                                interactive=False,
                                autoplay=False,
                                show_download_button=True,
                            )
                        
                        with gr.Row():
                            variant2_preview = gr.Audio(
                                label="Variant 2",
                                type="filepath",
                                value=None, 
                                interactive=False,
                                autoplay=False,
                                show_download_button=True,
                            )
                        
                        with gr.Row():
                            variant3_preview = gr.Audio(
                                label="Variant 3",
                                type="filepath",
                                value=None, 
                                interactive=False,
                                autoplay=False,
                                show_download_button=True,
                            )
                        
                        gr.Markdown("#### Beat Detection")
                        batch_beat_mix_preview = gr.Audio(
                            label="Beat Detection Mix",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=False,
                            show_download_button=True,
                        )
        
        # Recent Jobs tab
        with gr.TabItem("Recent Jobs"):
            gr.Markdown("### Recent Jobs")
            recent_jobs_list = gr.HTML(get_recent_jobs())
            refresh_jobs_btn = gr.Button("Refresh Jobs")
            refresh_jobs_btn.click(fn=get_recent_jobs, outputs=recent_jobs_list)
        
        # About tab
        with gr.TabItem("About"):
            gr.Markdown("""
            ## About Melody Generator
            
            This application uses AI to generate vocal melodies from backing tracks.
            
            ### How it works:
            
            1. Upload a backing track (WAV file)
            2. Optionally adjust settings like start time, BPM, and seed
            3. Select a model set and voice type in the Advanced Settings
            4. Click "Generate Melodies"
            5. The system will process your track and generate:
               - A vocal melody track
               - A mixed track (vocals + backing)
               - A MIDI file of the melody
               - A beat estimation mix
            
            ### Technical Details:
            
            The application uses Docker containers to run specialized AI models:
            - Melody generation model creates the initial melody
            - Vocal synthesis model converts the melody to vocals
            - Audio mixing combines the vocals with your backing track
            
            Two model sets are available:
            - Set 1: Default model set
            - Set 2: Alternative model set with different characteristics
            
            Jobs are processed in the background and results are available when processing completes.
            """)
    
    # Function to toggle UI elements based on batch mode
    def toggle_batch_mode(enable_batch, model_selection):
        """Toggle UI elements based on batch mode and model selection"""
        # Only enable batch mode for model set 2 ("new")
        is_new_model = model_selection == "set2"
        can_use_batch = enable_batch and is_new_model
        
        if can_use_batch:
            # Show batch view, hide single variant view, hide seed controls
            return (
                gr.update(visible=False),  # single_variant_view
                gr.update(visible=True),   # multi_variant_view
                gr.update(visible=False),  # seed_controls
                gr.update(value="When multiple variants mode is enabled, 3 different melody variants will be generated with random seeds. Individual downloads are disabled in this preview mode.") # batch_help
            )
        else:
            # If batch mode is checked but old model is selected
            if enable_batch and not is_new_model:
                help_text = "Multiple variants mode is only available with the New model. Please select the New model to enable this feature."
            else:
                help_text = "When enabled, 3 different melody variants will be generated with random seeds. This feature only works with the New model. Seed selection is disabled in this mode."
                
            # Show single variant view, hide batch view, show seed controls
            return (
                gr.update(visible=True),   # single_variant_view
                gr.update(visible=False),  # multi_variant_view
                gr.update(visible=True),   # seed_controls
                gr.update(value=help_text) # batch_help
            )
    
    # Connect the batch mode toggle to UI updates
    enable_batch_mode.change(
        fn=toggle_batch_mode,
        inputs=[enable_batch_mode, model_set],
        outputs=[single_variant_view, multi_variant_view, seed_controls, batch_help]
    )
    
    # Also update when model set changes
    model_set.change(
        fn=toggle_batch_mode,
        inputs=[enable_batch_mode, model_set],
        outputs=[single_variant_view, multi_variant_view, seed_controls, batch_help]
    )
    
    # Connect the generate button to the process function
    generate_btn.click(
        fn=process_audio,
        inputs=[file_input, start_time, bpm, seed, randomize_seed, model_set, voice_type, enable_batch_mode],
        outputs=[
            status_message, 
            vocal_preview, 
            mixed_preview, 
            midi_preview,
            beat_mix_preview,
            variant2_preview,  # New output for variant 2
            variant3_preview,  # New output for variant 3
            recent_jobs_list,
            current_job_status
        ]
    )

if __name__ == "__main__":

    try:
        logger.info("Starting Gradio server...")
        demo.launch(
            server_name="0.0.0.0", 
            server_port=int(os.environ.get("PORT", 7860)),
            debug=True,
            show_error=True,
            allowed_paths=[
                SHARED_DIR + "/*",  # Base wildcard
                "/tmp/melody_generator/*",  # Temp directory for copied files
                # Add specific paths for all job directories
                os.path.join(SHARED_DIR, "vocal_results"),
                os.path.join(SHARED_DIR, "melody_results"),
                os.path.join(SHARED_DIR, "vocal_results_set1"),
                os.path.join(SHARED_DIR, "vocal_results_set2"),
                os.path.join(SHARED_DIR, "melody_results_set1"),
                os.path.join(SHARED_DIR, "melody_results_set2"),
                # Add wildcards for job subdirectories
                os.path.join(SHARED_DIR, "vocal_results_set1", "job_*"),
                os.path.join(SHARED_DIR, "vocal_results_set2", "job_*"),
                os.path.join(SHARED_DIR, "melody_results_set1", "job_*"),
                os.path.join(SHARED_DIR, "melody_results_set2", "job_*"),
                # Add wildcards for variant subdirectories
                os.path.join(SHARED_DIR, "vocal_results_set1", "job_*", "variant_*"),
                os.path.join(SHARED_DIR, "vocal_results_set2", "job_*", "variant_*"),
            ],
            prevent_thread_lock=True  # Add this to prevent UI freezing
        )
    except Exception as e:
        logger.critical(f"Failed to start Gradio server: {e}", exc_info=True)
        raise
