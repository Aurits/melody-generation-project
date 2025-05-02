import threading
import time
import datetime
import logging
import os
from models import SessionLocal, Job
from services import process_song, check_container_running
from gcp_storage import upload_job_results
from gcp_storage import upload_job_files
import json

# Set up logging
logger = logging.getLogger(__name__)

def process_job(job_id, checkpoint, gen_seed, shared_dir):
    """
    Process a single job by ID.
    """
    session = SessionLocal()
    job = session.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        logger.error(f"Job {job_id} not found in database")
        return
        
    try:
        logger.info(f"Starting to process job {job_id}")
        job.status = "processing"
        job.updated_at = datetime.datetime.utcnow()
        session.commit()
        
        # Log job details
        logger.info(f"Processing job {job.id} with input file {job.input_file}")
        logger.info(f"Job parameters: {job.parameters}")
        
        # Parse job parameters
        start_time = 0
        bpm = 0
        job_seed = gen_seed  # Default to global seed
        model_set = "set1"   # Default to set1
        sex = "female"       # Default to female voice
        
        if job.parameters:
            params = dict(param.split('=') for param in job.parameters.split(','))
            start_time = float(params.get('start_time', 0))
            bpm = int(float(params.get('bpm', 0)))
            
            # Extract the job-specific seed if available
            if 'seed' in params:
                job_seed = int(float(params.get('seed', gen_seed)))
                logger.info(f"Using job-specific seed: {job_seed}")
                
            # Extract model_set if available
            if 'model_set' in params:
                model_set = params.get('model_set', 'set1')
                logger.info(f"Using model set: {model_set}")
                
            # Extract sex parameter if available
            if 'sex' in params:
                sex = params.get('sex', 'female')
                logger.info(f"Using voice type: {sex}")
        
        # Store the model_set in the database
        # Update the parameters to include model_set if it's not already there
        if job.parameters and 'model_set=' not in job.parameters:
            job.parameters += f",model_set={model_set}"
        elif not job.parameters:
            job.parameters = f"model_set={model_set}"
        session.commit()
        
        # Check if the input file exists
        if not os.path.exists(job.input_file):
            error_msg = f"Input file {job.input_file} does not exist"
            logger.error(error_msg)
            job.status = "failed"
            session.commit()
            return
            
        # Run the complete song processing (melody generation and vocal mix)
        logger.info(f"Calling process_song with input file: {job.input_file} and model_set: {model_set}")
        final_mix, beat_mix_file = process_song(
            shared_dir=shared_dir, 
            input_bgm=job.input_file, 
            checkpoint=checkpoint, 
            gen_seed=job_seed, 
            job_id=job_id, 
            start_time=start_time, 
            bpm=bpm,
            model_set=model_set,
            sex=sex
        )
        
        logger.info(f"Processing complete. Output file: {final_mix}")
        job.output_file = final_mix
        
        # Try to upload files to GCP using the enhanced method
        try:
            # Upload ALL files from job-specific directories using the upload_job_files function
            # This will include timestamps in folder names and scan all files in the directories
            # Removed model_set parameter as requested
            gcp_urls = upload_job_files(job_id, shared_dir)
            
            # Store all GCP URLs in the dedicated JSON column
            if gcp_urls:
                # Store the JSON directly in the dedicated column
                job.gcp_urls_json = json.dumps(gcp_urls)
                logger.info(f"Stored all GCP URLs in dedicated JSON column")
                
                # Also store the mixed track URL in the gcp_url field for backward compatibility
                if any(k for k in gcp_urls.keys() if 'mixed' in k):
                    # Find the first key containing 'mixed'
                    mixed_key = next((k for k in gcp_urls.keys() if 'mixed' in k), None)
                    if mixed_key:
                        job.gcp_url = gcp_urls[mixed_key]
                        logger.info(f"Stored GCP URL in job record: {job.gcp_url}")
            
        except Exception as e:
            logger.error(f"Error uploading files to GCP: {str(e)}", exc_info=True)
            logger.info("Continuing with job processing despite GCP upload failure")
        
        
        # Mark job as completed
        job.status = "completed"
        job.updated_at = datetime.datetime.utcnow()
        session.commit()
        logger.info(f"Job {job_id} marked as completed")
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}", exc_info=True)
        job.status = "failed"
        session.commit()
    finally:
        session.close()

def job_worker(checkpoint, gen_seed, shared_dir):
    """
    Background worker that continuously checks for pending jobs.
    """
    logger.info("Job worker started")
    
    # Check if required containers for both model sets are running
    melody_container_set1 = "melody-generation-set1"
    vocal_container_set1 = "vocal-mix-set1"
    melody_container_set2 = "melody-generation-set2"
    vocal_container_set2 = "vocal-mix-set2"
    
    # Check set1 containers
    if not check_container_running(melody_container_set1):
        logger.error(f"Required container '{melody_container_set1}' is not running")
    
    if not check_container_running(vocal_container_set1):
        logger.error(f"Required container '{vocal_container_set1}' is not running")
    
    # Check set2 containers
    if not check_container_running(melody_container_set2):
        logger.warning(f"Container '{melody_container_set2}' is not running. Set2 models will not be available.")
    
    if not check_container_running(vocal_container_set2):
        logger.warning(f"Container '{vocal_container_set2}' is not running. Set2 models will not be available.")
    
    while True:
        try:
            session = SessionLocal()
            pending_jobs = session.query(Job).filter(Job.status == "pending").all()
            
            if pending_jobs:
                logger.info(f"Found {len(pending_jobs)} pending jobs")
                for job in pending_jobs:
                    logger.info(f"Starting thread for job {job.id}")
                    thread = threading.Thread(
                        target=process_job, 
                        args=(job.id, checkpoint, gen_seed, shared_dir),
                        name=f"job-{job.id}"
                    )
                    thread.start()
            else:
                logger.debug("No pending jobs found")
                
            session.close()
        except Exception as e:
            logger.error(f"Error in job worker: {str(e)}", exc_info=True)
        
        time.sleep(5)

def start_worker(checkpoint, gen_seed, shared_dir):
    """
    Start the background worker thread.
    """
    logger.info(f"Starting worker with checkpoint: {checkpoint}, seed: {gen_seed}, shared_dir: {shared_dir}")
    worker_thread = threading.Thread(
        target=job_worker, 
        args=(checkpoint, gen_seed, shared_dir), 
        daemon=True,
        name="job-worker-main"
    )
    worker_thread.start()
    logger.info(f"Worker thread started: {worker_thread.name}")