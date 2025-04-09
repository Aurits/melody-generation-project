# job_manager.py
import threading
import time
import datetime
import logging
import os
from models import SessionLocal, Job
from services import process_song, check_container_running

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
        
        # Check if the input file exists
        if not os.path.exists(job.input_file):
            error_msg = f"Input file {job.input_file} does not exist"
            logger.error(error_msg)
            job.status = "failed"
            session.commit()
            return
            
        # Run the complete song processing (melody generation and vocal mix)
        # Pass the job_id to process_song for job-specific directories
        logger.info(f"Calling process_song with input file: {job.input_file}")
        final_mix = process_song(shared_dir, job.input_file, checkpoint, gen_seed, job_id)
        
        logger.info(f"Processing complete. Output file: {final_mix}")
        job.output_file = final_mix
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