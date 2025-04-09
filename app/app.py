# app.py
# Improved Melody Generator interface with proper integration to backend services
import os
import time
import logging
import gradio as gr
from models import SessionLocal, Job, init_db
from job_manager import start_worker
from sqlalchemy import desc
import datetime
import shutil
import uuid

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
# Job Polling Function
# -------------------- 
def poll_job_status(job_id, progress=None):
    """Poll the job status until it's completed or failed"""
    session = SessionLocal()
    max_attempts = 60  # 5 minutes (5s * 60)
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

# Function to create download links
def create_download_link(file_path, label="Download File"):
    if not file_path or not os.path.exists(file_path):
        return "No file available"
    
    filename = os.path.basename(file_path)
    return f"<a href='/file={file_path}' download='{filename}' target='_blank'>{label}</a>"

# Function to create a download link for MIDI files
def create_midi_download_link(midi_path):
    return create_download_link(midi_path, "Download MIDI File")

# -------------------- 
# Recent Jobs Function
# -------------------- 
def get_recent_jobs():
    """Get a list of recent jobs for display"""
    global current_job_id
    
    session = SessionLocal()
    try:
        jobs = session.query(Job).order_by(desc(Job.created_at)).limit(10).all()
        job_list = []
        
        for job in jobs:
            created_at = job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else "Unknown"
            
            # Add emoji based on status
            if job.status == "completed":
                status_emoji = "✅"
            elif job.status == "failed":
                status_emoji = "❌"
            elif job.status == "processing":
                status_emoji = "⏳"
            else:
                status_emoji = "⏱️"
                
            job_list.append(f"Job {job.id}: {status_emoji} {job.status} ({created_at})")
                
        return "\n".join(job_list) if job_list else "No recent jobs"
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
        
        created_at = job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else "Unknown"
        
        # Add emoji based on status
        if job.status == "completed":
            status_emoji = "✅"
        elif job.status == "failed":
            status_emoji = "❌"
        elif job.status == "processing":
            status_emoji = "⏳"
        else:
            status_emoji = "⏱️"
            
        return f"Current Job {job.id}: {status_emoji} {job.status} ({created_at})"
    finally:
        session.close()

# -------------------- 
# Gradio UI Functions
# -------------------- 
def process_audio(file, start_time, bpm, seed, randomize_seed, progress=gr.Progress()):
    global current_job_id
    
    if file is None:
        logger.warning("Job submission attempted with no file")
        return "⚠️ Please upload a backing track first", None, None, None, get_recent_jobs(), get_current_job_status()
    
    # Validate inputs
    if start_time and start_time > 0:
        if not bpm or bpm <= 0:
            error = "If start_time is provided, BPM must also be greater than 0."
            logger.warning(error)
            return error, None, None, None, get_recent_jobs(), get_current_job_status()
    elif bpm and bpm > 0:
        if not start_time or start_time <= 0:
            error = "If BPM is provided, start_time must also be greater than 0."
            logger.warning(error)
            return error, None, None, None, get_recent_jobs(), get_current_job_status()
    
    try:
        progress(0, "Initializing...")
        
        # Handle randomized seed if checkbox is checked
        if randomize_seed:
            import random
            seed = random.randint(0, 10000)
            logger.info(f"Randomized seed to: {seed}")
        
        # Create a timestamp-based filename to avoid collisions
        timestamp = int(time.time())
        
        # Fix for the file.name error - handle both string paths and file objects
        if isinstance(file, str):
            original_filename = os.path.basename(file)
        else:
            original_filename = os.path.basename(file.name)
            
        # Remove file extension for use in output filenames
        input_filename_base = os.path.splitext(original_filename)[0]
        
        # Generate a unique ID for this job
        unique_id = str(uuid.uuid4())[:8]
        
        filename = f"{timestamp}_{original_filename}"
        
        # Save the uploaded file into the shared input directory
        input_dir = os.path.join(SHARED_DIR, "input")
        os.makedirs(input_dir, exist_ok=True)
        file_path = os.path.join(input_dir, filename)
        
        progress(0.1, "Processing audio file...")
        
        # Handle both string paths and file objects
        if isinstance(file, str):
            # If file is already a path, just copy it
            import shutil
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
        
        # Create a new job record in the database
        progress(0.2, "Creating job...")
        session = SessionLocal()
        job = Job(
            input_file=file_path,  # Use the absolute path
            status="pending",  # Set to pending for the worker to pick up
            parameters=f"start_time={start_time},bpm={bpm},seed={seed}"
        )
        session.add(job)
        session.commit()
        job_id = job.id
        current_job_id = job_id  # Set the global current job ID
        logger.info(f"Created job {job_id} with input file {file_path}")
        session.close()
        
        # Update the recent jobs display
        recent_jobs_html = get_recent_jobs()
        current_job_status = get_current_job_status()
        
        # Poll for job completion
        progress(0.3, f"Job submitted (ID: {job_id}). Waiting for processing...")
        output_file, status = poll_job_status(job_id, progress)

        # Process the results
        if status == "completed":
            # Get the paths for the generated files
            output_dir = os.path.dirname(output_file)
            
            # Create new filenames with the requested format
            new_vocal_filename = f"vocal_melody_{input_filename_base}_seed{seed}_{unique_id}.wav"
            new_mixed_filename = f"mixed_audio_{input_filename_base}_seed{seed}_{unique_id}.wav"
            new_midi_filename = f"melody_{input_filename_base}_seed{seed}_{unique_id}.mid"
            
            # Original paths
            vocal_melody_path = os.path.join(output_dir, "vocal.wav")
            mixed_track_path = output_file  # This is the mix.wav file
            midi_file_path = os.path.join(SHARED_DIR, "melody_results", "melody.mid")
            
            # New paths
            new_vocal_path = os.path.join(output_dir, new_vocal_filename)
            new_mixed_path = os.path.join(output_dir, new_mixed_filename)
            new_midi_path = os.path.join(SHARED_DIR, "melody_results", new_midi_filename)
            
            # Copy files with new names
            if os.path.exists(vocal_melody_path):
                shutil.copy2(vocal_melody_path, new_vocal_path)
                logger.info(f"Copied vocal file to {new_vocal_path}")
            
            if os.path.exists(mixed_track_path):
                shutil.copy2(mixed_track_path, new_mixed_path)
                logger.info(f"Copied mixed file to {new_mixed_path}")
                
            if os.path.exists(midi_file_path):
                shutil.copy2(midi_file_path, new_midi_path)
                logger.info(f"Copied MIDI file to {new_midi_path}")
            
            # Verify output files exist and log their sizes
            files_exist = True
            
            if os.path.exists(new_mixed_path):
                logger.info(f"Mixed track file found: {new_mixed_path} ({os.path.getsize(new_mixed_path)} bytes)")
            else:
                logger.warning(f"Mixed track file not found: {new_mixed_path}")
                files_exist = False
                
            if os.path.exists(new_vocal_path):
                logger.info(f"Vocal melody file found: {new_vocal_path} ({os.path.getsize(new_vocal_path)} bytes)")
            else:
                logger.warning(f"Vocal melody file not found: {new_vocal_path}")
                files_exist = False
                
            if os.path.exists(new_midi_path):
                logger.info(f"MIDI file found: {new_midi_path} ({os.path.getsize(new_midi_path)} bytes)")
            else:
                logger.warning(f"MIDI file not found: {new_midi_path}")
                files_exist = False
            
            # Make sure the audio files are readable by the current user
            try:
                if os.path.exists(new_vocal_path):
                    os.chmod(new_vocal_path, 0o644)
                if os.path.exists(new_mixed_path):
                    os.chmod(new_mixed_path, 0o644)
                if os.path.exists(new_midi_path):
                    os.chmod(new_midi_path, 0o644)
            except Exception as e:
                logger.warning(f"Could not set file permissions: {str(e)}")
            
            progress(1.0, "Generation complete!")
            
            if files_exist:
                success_message = f"✅ Generation complete! (Job ID: {job_id})"
                
                # Log the paths being returned to the UI
                logger.info(f"Returning vocal path: {new_vocal_path}")
                logger.info(f"Returning mixed path: {new_mixed_path}")
                logger.info(f"Returning MIDI path: {new_midi_path}")
                
                # Update recent jobs display and current job status
                recent_jobs_html = get_recent_jobs()
                current_job_status = get_current_job_status()
                
                # Return all outputs
                return success_message, new_vocal_path, new_mixed_path, new_midi_path, recent_jobs_html, current_job_status
            else:
                error_message = f"⚠️ Job completed but some files are missing (Job ID: {job_id})"
                return error_message, None, None, None, get_recent_jobs(), get_current_job_status()
        else:
            error_message = f"❌ Job failed or timed out (Job ID: {job_id})"
            return error_message, None, None, None, get_recent_jobs(), get_current_job_status()

    except Exception as e:
        logger.error(f"Error generating melodies: {str(e)}", exc_info=True)
        return f"❌ Error: {str(e)}", None, None, None, get_recent_jobs(), get_current_job_status()

def randomize_seed_value():
    import random
    new_seed = random.randint(0, 10000)
    return gr.update(value=new_seed)

# -------------------- 
# Gradio Interface Setup
# -------------------- 
with gr.Blocks(title="Melody Generator") as demo:
    with gr.Row():
        with gr.Column(scale=3):
            gr.Markdown("# Melody Generator")
            gr.Markdown("Upload a backing track (WAV) to generate vocal melodies.")
        
        with gr.Column(scale=1):
            refresh_btn = gr.Button("Refresh Status", size="sm")
            current_job_status = gr.Markdown(get_current_job_status())
            refresh_btn.click(fn=get_current_job_status, outputs=current_job_status)

    with gr.Tabs():
        with gr.TabItem("Generate"):
            with gr.Row():
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
                    
                    generate_btn = gr.Button("Generate Melodies", variant="primary")
                    status_message = gr.Markdown("Upload a track and click Generate.")
                
                with gr.Column():
                    gr.Markdown("### Preview")
                    
                    with gr.Accordion("Vocal Melody", open=True):
                        vocal_preview = gr.Audio(
                            label="Vocal Melody (WAV)",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=False,
                            show_download_button=True,
                        )

                    with gr.Accordion("Mixed Track", open=True):
                        mixed_preview = gr.Audio(
                            label="Mixed Track (WAV)",
                            type="filepath",
                            value=None, 
                            interactive=False,
                            autoplay=True,
                            show_download_button=True,
                        )
                    
                    with gr.Accordion("MIDI File", open=True):
                        midi_preview = gr.File(
                            label="MIDI Melody",
                            value=None,  
                            interactive=False,
                            file_count="single",
                            type="filepath",
                        )
        
        with gr.TabItem("Recent Jobs"):
            gr.Markdown("### Recent Jobs")
            recent_jobs_list = gr.Markdown(get_recent_jobs())
            refresh_jobs_btn = gr.Button("Refresh Jobs")
            refresh_jobs_btn.click(fn=get_recent_jobs, outputs=recent_jobs_list)
        
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
            allowed_paths=["/shared_data/vocal_results", "/shared_data/melody_results"],
            prevent_thread_lock=True  # Add this to prevent UI freezing
        )
    except Exception as e:
        logger.critical(f"Failed to start Gradio server: {e}", exc_info=True)
        raise