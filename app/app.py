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

# Function to create a download link for audio files
def create_audio_download_link(audio_path, label="Download Audio"):
    return create_download_link(audio_path, label)

# -------------------- 
# Recent Jobs Function
# -------------------- 
def get_recent_jobs():
    """Get a list of recent jobs for display"""
    global current_job_id
    
    session = SessionLocal()
    try:
        jobs = session.query(Job).order_by(desc(Job.created_at)).limit(5).all()
        job_list = []
        
        for job in jobs:
            created_at = job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else "Unknown"
            status_emoji = "✅" if job.status == "completed" else "⏳" if job.status == "processing" else "❌" if job.status == "failed" else "⏱️"
            
            # Highlight current job if it exists
            if current_job_id and job.id == current_job_id:
                job_list.append(f"**Job {job.id}: {status_emoji} {job.status} ({created_at})**")
            else:
                job_list.append(f"Job {job.id}: {status_emoji} {job.status} ({created_at})")
                
        return "\n".join(job_list) if job_list else "No recent jobs"
    finally:
        session.close()

# Function to get detailed job information
def get_job_details(job_id):
    """Get detailed information about a specific job"""
    if not job_id:
        return "Please select a job to view details"
    
    try:
        job_id = int(job_id)
    except ValueError:
        return "Invalid job ID"
    
    session = SessionLocal()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            return f"Job {job_id} not found"
        
        created_at = job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else "Unknown"
        updated_at = job.updated_at.strftime("%Y-%m-%d %H:%M:%S") if job.updated_at else "Unknown"
        
        # Calculate duration if possible
        duration = "N/A"
        if job.created_at and job.updated_at and job.status in ["completed", "failed"]:
            duration_seconds = (job.updated_at - job.created_at).total_seconds()
            minutes, seconds = divmod(duration_seconds, 60)
            duration = f"{int(minutes)}m {int(seconds)}s"
        
        # Format parameters for display
        parameters = job.parameters.replace(",", ", ") if job.parameters else "None"
        
        # Create download links if job is completed
        output_links = ""
        if job.status == "completed" and job.output_file:
            output_dir = os.path.dirname(job.output_file)
            vocal_path = os.path.join(output_dir, "vocal.wav")
            mixed_path = job.output_file
            midi_path = os.path.join(SHARED_DIR, "melody_results", "melody.mid")
            
            if os.path.exists(vocal_path):
                output_links += f"<p>{create_audio_download_link(vocal_path, 'Download Vocal Track')}</p>"
            
            if os.path.exists(mixed_path):
                output_links += f"<p>{create_audio_download_link(mixed_path, 'Download Mixed Track')}</p>"
                
            if os.path.exists(midi_path):
                output_links += f"<p>{create_midi_download_link(midi_path)}</p>"
        
        # Build the details string
        details = f"""
## Job {job_id} Details

**Status:** {job.status}  
**Created:** {created_at}  
**Updated:** {updated_at}  
**Duration:** {duration}  

### Input
**File:** {os.path.basename(job.input_file) if job.input_file else "None"}  
**Parameters:** {parameters}  

### Output
**Output File:** {os.path.basename(job.output_file) if job.output_file else "None"}  

{output_links}
"""
        return details
    finally:
        session.close()

# -------------------- 
# Gradio UI Functions
# -------------------- 
def process_audio(file, start_time, bpm, seed, randomize_seed, progress=gr.Progress()):
    global current_job_id
    
    if file is None:
        logger.warning("Job submission attempted with no file")
        return "⚠️ Please upload a backing track first", None, None, None, None, None, None, get_recent_jobs()
    
    # Validate inputs
    if start_time and start_time > 0:
        if not bpm or bpm <= 0:
            error = "If start_time is provided, BPM must also be greater than 0."
            logger.warning(error)
            return error, None, None, None, None, None, None, get_recent_jobs()
    elif bpm and bpm > 0:
        if not start_time or start_time <= 0:
            error = "If BPM is provided, start_time must also be greater than 0."
            logger.warning(error)
            return error, None, None, None, None, None, None, get_recent_jobs()
    
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
        
        # Poll for job completion
        progress(0.3, f"Job submitted (ID: {job_id}). Waiting for processing...")
        output_file, status = poll_job_status(job_id, progress)

        # Process the results
        if status == "completed":
            # Get the paths for the generated files
            output_dir = os.path.dirname(output_file)
            vocal_melody_path = os.path.join(output_dir, "vocal.wav")
            mixed_track_path = output_file  # This is the mix.wav file
            midi_file_path = os.path.join(SHARED_DIR, "melody_results", "melody.mid")
            
            # Verify output files exist and log their sizes
            files_exist = True
            
            if os.path.exists(mixed_track_path):
                logger.info(f"Mixed track file found: {mixed_track_path} ({os.path.getsize(mixed_track_path)} bytes)")
            else:
                logger.warning(f"Mixed track file not found: {mixed_track_path}")
                files_exist = False
                
            if os.path.exists(vocal_melody_path):
                logger.info(f"Vocal melody file found: {vocal_melody_path} ({os.path.getsize(vocal_melody_path)} bytes)")
            else:
                logger.warning(f"Vocal melody file not found: {vocal_melody_path}")
                files_exist = False
                
            if os.path.exists(midi_file_path):
                logger.info(f"MIDI file found: {midi_file_path} ({os.path.getsize(midi_file_path)} bytes)")
            else:
                logger.warning(f"MIDI file not found: {midi_file_path}")
                files_exist = False
            
            # Make sure the audio files are readable by the current user
            try:
                if os.path.exists(vocal_melody_path):
                    os.chmod(vocal_melody_path, 0o644)
                if os.path.exists(mixed_track_path):
                    os.chmod(mixed_track_path, 0o644)
                if os.path.exists(midi_file_path):
                    os.chmod(midi_file_path, 0o644)
            except Exception as e:
                logger.warning(f"Could not set file permissions: {str(e)}")
            
            progress(1.0, "Generation complete!")
            
            if files_exist:
                success_message = f"✅ Generation complete! (Job ID: {job_id})"
                
                # Create download links
                vocal_download_link = create_audio_download_link(vocal_melody_path, "Download Vocal Track")
                mixed_download_link = create_audio_download_link(mixed_track_path, "Download Mixed Track")
                midi_download_link = create_midi_download_link(midi_file_path)
                
                # For MIDI file info
                midi_info = f"MIDI file saved at: {midi_file_path}"
                
                # Log the paths being returned to the UI
                logger.info(f"Returning vocal path: {vocal_melody_path}")
                logger.info(f"Returning mixed path: {mixed_track_path}")
                
                # Update recent jobs display
                recent_jobs_html = get_recent_jobs()
                
                # Return all outputs
                return success_message, vocal_melody_path, mixed_track_path, midi_info, midi_download_link, vocal_download_link, mixed_download_link, recent_jobs_html
            else:
                error_message = f"⚠️ Job completed but some files are missing (Job ID: {job_id})"
                return error_message, None, None, None, None, None, None, get_recent_jobs()
        else:
            error_message = f"❌ Job failed or timed out (Job ID: {job_id})"
            return error_message, None, None, None, None, None, None, get_recent_jobs()

    except Exception as e:
        logger.error(f"Error generating melodies: {str(e)}", exc_info=True)
        return f"❌ Error: {str(e)}", None, None, None, None, None, None, get_recent_jobs()

def randomize_seed_value():
    import random
    new_seed = random.randint(0, 10000)
    return gr.update(value=new_seed)

def update_job_details(job_id):
    """Update the job details display when a job is selected"""
    return get_job_details(job_id)

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
            recent_jobs_display = gr.Markdown(get_recent_jobs())
            refresh_btn.click(fn=get_recent_jobs, outputs=recent_jobs_display)

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
                        vocal_output = gr.Audio(
                            label="Vocal Track (WAV)",
                            type="filepath",
                            interactive=False,
                            show_download_button=True,
                            format="wav",
                            elem_id="vocal_output",
                            streaming=False  # Prevent auto-refresh
                        )
                        vocal_download = gr.HTML(
                            value="Download link will appear after generation."
                        )

                    with gr.Accordion("Mixed Track", open=True):
                        mixed_output = gr.Audio(
                            label="Mixed Track (WAV)",
                            type="filepath",
                            interactive=False,
                            autoplay=False,  # Prevent auto-refresh
                            show_download_button=True,
                            format="wav",
                            elem_id="mixed_output",
                            streaming=False  # Prevent auto-refresh
                        )
                        mixed_download = gr.HTML(
                            value="Download link will appear after generation."
                        )
                    
                    with gr.Accordion("MIDI File", open=True):
                        # Text information about the MIDI file
                        midi_output = gr.Markdown(
                            value="MIDI file will appear here after generation."
                        )
                        # Download link for the MIDI file
                        midi_download = gr.HTML(
                            value="Download link will appear after generation."
                        )
        
        with gr.TabItem("Recent Jobs"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Recent Jobs")
                    job_list_dropdown = gr.Dropdown(
                        label="Select a job to view details",
                        choices=lambda: [str(job.id) for job in SessionLocal().query(Job).order_by(desc(Job.created_at)).limit(10).all()],
                        interactive=True
                    )
                    refresh_jobs_btn = gr.Button("Refresh Job List")
                
                with gr.Column(scale=2):
                    job_details = gr.Markdown("Select a job from the dropdown to view details")
            
            # Set up the refresh and selection functionality
            refresh_jobs_btn.click(
                fn=lambda: gr.update(choices=[str(job.id) for job in SessionLocal().query(Job).order_by(desc(Job.created_at)).limit(10).all()]),
                outputs=job_list_dropdown
            )
            job_list_dropdown.change(
                fn=update_job_details,
                inputs=job_list_dropdown,
                outputs=job_details
            )
        
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
            vocal_output, 
            mixed_output, 
            midi_output, 
            midi_download,
            vocal_download,
            mixed_download,
            recent_jobs_display
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
            prevent_thread_lock=True,  # Add this to prevent UI freezing
            # Add this to prevent automatic refresh on file download
            _js="() => {document.querySelectorAll('audio').forEach(el => {el.onplay = null; el.onpause = null;})}"
        )
    except Exception as e:
        logger.critical(f"Failed to start Gradio server: {e}", exc_info=True)
        raise