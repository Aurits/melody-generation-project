# app.py
# Improved Melody Generator interface with better file handling and job organization
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
        
        # Create a table header with additional styling for the file listings
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
        .file-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .file-item {
            display: flex;
            align-items: center;
            padding: 6px 10px;
            background-color: #f3f4f6;
            border-radius: 4px;
            font-size: 0.8rem;
            transition: background-color 0.2s;
            text-decoration: none;
            color: #4b5563;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .file-item:hover {
            background-color: #e5e7eb;
        }
        .file-icon {
            margin-right: 6px;
            font-size: 1rem;
        }
        .files-container {
            margin-top: 8px;
        }
        .files-toggle-btn {
            background-color: #f3f4f6;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            padding: 4px 10px;
            cursor: pointer;
            color: #4b5563;
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            margin-bottom: 8px;
        }
        .files-toggle-btn:hover {
            background-color: #e5e7eb;
        }
        .file-count {
            display: inline-block;
            background-color: #e5e7eb;
            border-radius: 9999px;
            padding: 2px 8px;
            font-size: 0.75rem;
            margin-left: 6px;
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
            
            # Format parameters for display (excluding the gcp_urls_json parameter)
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
            
            # Create file listings HTML without mapping - just showing raw filenames
            file_count = len(gcp_urls)
            files_html = ""
            
            if gcp_urls:
                # Create a better toggle button implementation
                toggle_id = f"toggle-job-{job.id}-files"
                container_id = f"job-{job.id}-files"
                
                files_html = f"""
                <div class="files-container">
                    <button id="{toggle_id}" class="files-toggle-btn" onclick="document.getElementById('{container_id}').style.display = document.getElementById('{container_id}').style.display === 'none' ? 'grid' : 'none';">
                        Show/Hide Files <span class="file-count">{file_count}</span>
                    </button>
                    <div id="{container_id}" class="file-grid" style="display: none;">
                """
                
                # Loop through all files and create a grid of file links with just the raw filenames
                for key, url in gcp_urls.items():
                    # Determine file type icon based on extension (simplified)
                    file_icon = "📄"  # Default icon
                    
                    # Get basic file extension
                    if key.endswith('.mid'):
                        file_icon = "🎹"  # MIDI
                    elif key.endswith('.wav'):
                        file_icon = "🔊"  # Audio
                    elif key.endswith('.json'):
                        file_icon = "📋"  # JSON
                    
                    # Just use the filename as is - no mapping
                    files_html += f"""
                    <a href="{url}" target="_blank" class="file-item" title="{key}">
                        <span class="file-icon">{file_icon}</span> {key}
                    </a>
                    """
                
                files_html += "</div></div>"
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
def process_audio(file, start_time, bpm, seed, randomize_seed, progress=gr.Progress()):
    global current_job_id
    
    if file is None:
        logger.warning("Job submission attempted with no file")
        return "⚠️ Please upload a backing track first", None, None, None, None, get_recent_jobs(), get_current_job_status()
    
    # Validate inputs
    if start_time > 0 and (not bpm or bpm <= 0):
        error = "If start_time is greater than 0, BPM must also be greater than 0."
        logger.warning(error)
        return error, None, None, None, None, get_recent_jobs(), get_current_job_status()
    
    try:
        progress(0, "Initializing...")
        
        # Handle randomized seed if checkbox is checked
        if randomize_seed:
            import random
            seed = random.randint(0, 10000)
            logger.info(f"Randomized seed to: {seed}")
        
        # Create a new job record in the database first to get the job ID
        session = SessionLocal()
        job = Job(
            status="pending",
            parameters=f"start_time={start_time},bpm={bpm},seed={seed}"
        )
        session.add(job)
        session.commit()
        job_id = job.id
        current_job_id = job_id  # Set the global current job ID
        logger.info(f"Created job {job_id}")
        
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
            
            # Define output filenames with the requested format
            vocal_filename = f"vocal_melody_{input_filename_base}_seed{seed}_{unique_id}.wav"
            mixed_filename = f"mixed_audio_{input_filename_base}_seed{seed}_{unique_id}.wav"
            midi_filename = f"melody_{input_filename_base}_seed{seed}_{unique_id}.mid"
            beat_mix_filename = f"beat_mix_{input_filename_base}_seed{seed}_{unique_id}.wav"
            
            # Define paths in job-specific directories
            vocal_path = os.path.join(job_vocal_dir, vocal_filename)
            mixed_path = os.path.join(job_vocal_dir, mixed_filename)
            midi_path = os.path.join(job_melody_dir, midi_filename)
            beat_mix_path = os.path.join(job_melody_dir, beat_mix_filename)
            
            # Get the original output paths
            output_dir = os.path.dirname(output_file)
            vocal_melody_path = os.path.join(output_dir, "vocal.wav")
            mixed_track_path = output_file  # This is the mix.wav file
            
            # Check multiple possible locations for the MIDI file
            possible_midi_paths = [
                os.path.join(SHARED_DIR, "melody_results", "melody.mid"),
                os.path.join(job_melody_dir, "melody.mid"),
                os.path.join(SHARED_DIR, "melody_results", f"job_{job_id}", "melody.mid"),
                os.path.join(output_dir, "melody.mid")
            ]
            
            # Check multiple possible locations for the beat mix file
            possible_beat_mix_paths = [
                os.path.join(SHARED_DIR, "melody_results", "beat_mixed_synth_mix.wav"),
                os.path.join(job_melody_dir, "beat_mixed_synth_mix.wav"),
                os.path.join(SHARED_DIR, "melody_results", f"job_{job_id}", "beat_mixed_synth_mix.wav"),
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
                shutil.copy2(vocal_melody_path, vocal_path)
                logger.info(f"Copied vocal file to {vocal_path}")
                files_copied.append("vocal")
            else:
                logger.warning(f"Vocal file not found at {vocal_melody_path}")
            
            if os.path.exists(mixed_track_path):
                shutil.copy2(mixed_track_path, mixed_path)
                logger.info(f"Copied mixed file to {mixed_path}")
                files_copied.append("mixed")
            else:
                logger.warning(f"Mixed file not found at {mixed_track_path}")
            
            if midi_file_path and os.path.exists(midi_file_path):
                shutil.copy2(midi_file_path, midi_path)
                logger.info(f"Copied MIDI file to {midi_path}")
                files_copied.append("midi")
            else:
                logger.warning("MIDI file not found in any of the expected locations")
            
            if beat_mix_file_path and os.path.exists(beat_mix_file_path):
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
            
            # Store the beat mix file path in the job parameters if available
            if "beat_mix" in files_copied:
                # Add beat_mix_file to job parameters
                if job.parameters:
                    job.parameters += f",beat_mix_file={beat_mix_path}"
                else:
                    job.parameters = f"beat_mix_file={beat_mix_path}"
                logger.info(f"Added beat mix file to job parameters: {beat_mix_path}")
            
            session.commit()
            session.close()
            
            progress(1.0, "Generation complete!")
            
            # Consider the job successful if at least the mixed track is available
            if "mixed" in files_copied:
                success_message = f"✅ Generation complete! (Job ID: {job_id})"
                
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
                return (
                    success_message, 
                    vocal_path if "vocal" in files_copied else None, 
                    mixed_path if "mixed" in files_copied else None, 
                    midi_path if "midi" in files_copied else None,
                    beat_mix_path if "beat_mix" in files_copied else None,  # Add beat mix file
                    recent_jobs_html, 
                    current_job_status
                )
            else:
                error_message = f"⚠️ Job completed but essential files are missing (Job ID: {job_id})"
                return error_message, None, None, None, None, get_recent_jobs(), get_current_job_status()

    except Exception as e:
        logger.error(f"Error generating melodies: {str(e)}", exc_info=True)
        return f"❌ Error: {str(e)}", None, None, None, None, get_recent_jobs(), get_current_job_status()

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
            3. Click "Generate Melodies"
            4. The system will process your track and generate:
               - A vocal melody track
               - A mixed track (vocals + backing)
               - A MIDI file of the melody
            
            ### Technical Details:
            
            The application uses Docker containers to run specialized AI models:
            - Melody generation model creates the initial melody
            - Vocal synthesis model converts the melody to vocals
            - Audio mixing combines the vocals with your backing track
            
            Jobs are processed in the background and results are available when processing completes.
            """)
    
    # Connect the generate button to the process function
    generate_btn.click(
        fn=process_audio,
        inputs=[file_input, start_time, bpm, seed, randomize_seed],
        outputs=[
            status_message, 
            vocal_preview, 
            mixed_preview, 
            midi_preview,
            beat_mix_preview, 
            recent_jobs_list,
            current_job_status
        ]
    )

if __name__ == "__main__":
    # Launch without share=True to avoid the bug with JSON schema conversion.
    # Also, binding to "0.0.0.0" lets the container serve the app on all interfaces.
    try:
        logger.info("Starting Gradio server...")
        demo.launch(
            server_name="0.0.0.0", 
            server_port=int(os.environ.get("PORT", 7860)),
            debug=True,
            show_error=True,
            allowed_paths=[
                SHARED_DIR,
                os.path.join(SHARED_DIR, "input"),
                os.path.join(SHARED_DIR, "melody_results"),
                os.path.join(SHARED_DIR, "vocal_results")
            ],
            prevent_thread_lock=True  # Add this to prevent UI freezing
        )
    except Exception as e:
        logger.critical(f"Failed to start Gradio server: {e}", exc_info=True)
        raise