# job_manager.py
import threading
import time
import datetime
import logging
import os
from models import SessionLocal, Job
from services import process_song, check_container_running
from gcp_storage import upload_job_results


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
        
        if job.parameters:
            params = dict(param.split('=') for param in job.parameters.split(','))
            start_time = float(params.get('start_time', 0))
            bpm = int(float(params.get('bpm', 0)))
            
            # Extract the job-specific seed if available
            if 'seed' in params:
                job_seed = int(float(params.get('seed', gen_seed)))
                logger.info(f"Using job-specific seed: {job_seed}")
        
        # Check if the input file exists
        if not os.path.exists(job.input_file):
            error_msg = f"Input file {job.input_file} does not exist"
            logger.error(error_msg)
            job.status = "failed"
            session.commit()
            return
            
        # Run the complete song processing (melody generation and vocal mix)
        # Pass the job_id, parameters, and job-specific seed to process_song
        logger.info(f"Calling process_song with input file: {job.input_file}")
        final_mix = process_song(shared_dir, job.input_file, checkpoint, job_seed, job_id, start_time, bpm)
        
        logger.info(f"Processing complete. Output file: {final_mix}")
        job.output_file = final_mix
        
        # Try to upload files to GCP
        gcp_urls = None
        try:
            # Get paths to all generated files
            job_melody_dir = os.path.join(shared_dir, "melody_results", f"job_{job_id}")
            job_vocal_dir = os.path.join(shared_dir, "vocal_results", f"job_{job_id}")
            
            # Find the MIDI file
            midi_file = None
            possible_midi_paths = [
                os.path.join(job_melody_dir, "melody.mid"),
                os.path.join(shared_dir, "melody_results", "melody.mid")
            ]
            for path in possible_midi_paths:
                if os.path.exists(path):
                    midi_file = path
                    break
            
            # Find the vocal file
            vocal_file = os.path.join(job_vocal_dir, "vocal.wav")
            if not os.path.exists(vocal_file):
                vocal_file = None
            
            # Upload files to GCP using the correct function
            gcp_urls = upload_job_results(
                job_id, 
                input_file=job.input_file,
                melody_file=midi_file,
                vocal_file=vocal_file,
                mixed_file=final_mix
            )
            
            # Store the GCP URL in the job record if available
            if gcp_urls and 'mixed' in gcp_urls:
                job.gcp_url = gcp_urls['mixed']
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
    
    # Check if required containers are running
    melody_container = "melody-generation"
    vocal_container = "vocal-mix"
    
    if not check_container_running(melody_container):
        logger.error(f"Required container '{melody_container}' is not running")
    
    if not check_container_running(vocal_container):
        logger.error(f"Required container '{vocal_container}' is not running")
    
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