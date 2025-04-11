# gcp_storage.py
# Simple module for uploading melody generation files to Google Cloud Storage

import os
import json
import logging
from google.cloud import storage
import glob

# Set up logging
logger = logging.getLogger(__name__)

# Path to the service account key file
SERVICE_ACCOUNT_FILE = "access.json"

# GCP bucket name
BUCKET_NAME = "melody_generation_api_bucket"

def get_storage_client():
    """
    Create and return a Google Cloud Storage client using service account credentials.
    """
    try:
        # Use the service account file for authentication
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            return storage.Client.from_service_account_json(SERVICE_ACCOUNT_FILE)
        else:
            logger.error(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
            return None
    except Exception as e:
        logger.error(f"Failed to create GCP storage client: {str(e)}")
        return None

def upload_file(local_file_path, gcp_path):
    """
    Upload a single file to GCP Storage.
    
    Args:
        local_file_path: Path to the local file
        gcp_path: Destination path in GCP bucket
        
    Returns:
        Public URL of the uploaded file if successful, None otherwise
    """
    if not os.path.exists(local_file_path):
        logger.warning(f"File not found: {local_file_path}")
        return None
        
    try:
        client = get_storage_client()
        if not client:
            return None
            
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(gcp_path)
        
        # Upload the file
        blob.upload_from_filename(local_file_path)
        
        # Make it publicly accessible
        blob.make_public()
        
        logger.info(f"Uploaded {local_file_path} to gs://{BUCKET_NAME}/{gcp_path}")
        return blob.public_url
        
    except Exception as e:
        logger.error(f"Error uploading {local_file_path}: {str(e)}")
        return None

def upload_job_files(job_id, shared_dir):
    """
    Upload all files for a specific job to GCP.
    
    Args:
        job_id: The job ID
        shared_dir: Base shared directory containing job files
        
    Returns:
        Dictionary with file types and their public URLs
    """
    urls = {}
    
    try:
        # Define job-specific directories
        job_input_dir = os.path.join(shared_dir, "input", f"job_{job_id}")
        job_melody_dir = os.path.join(shared_dir, "melody_results", f"job_{job_id}")
        job_vocal_dir = os.path.join(shared_dir, "vocal_results", f"job_{job_id}")
        
        # Upload input files
        input_files = glob.glob(os.path.join(job_input_dir, "*"))
        for input_file in input_files:
            filename = os.path.basename(input_file)
            gcp_path = f"job_{job_id}/input/{filename}"
            url = upload_file(input_file, gcp_path)
            if url:
                urls[f"input_{filename}"] = url
        
        # Upload melody files
        melody_files = glob.glob(os.path.join(job_melody_dir, "*"))
        for melody_file in melody_files:
            filename = os.path.basename(melody_file)
            gcp_path = f"job_{job_id}/melody/{filename}"
            url = upload_file(melody_file, gcp_path)
            if url:
                urls[f"melody_{filename}"] = url
        
        # Upload vocal files
        vocal_files = glob.glob(os.path.join(job_vocal_dir, "*"))
        for vocal_file in vocal_files:
            filename = os.path.basename(vocal_file)
            gcp_path = f"job_{job_id}/vocal/{filename}"
            url = upload_file(vocal_file, gcp_path)
            if url:
                urls[f"vocal_{filename}"] = url
        
        logger.info(f"Uploaded {len(urls)} files for job {job_id}")
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading job files: {str(e)}")
        return urls  # Return whatever was successfully uploaded

def upload_job_results(job_id, input_file=None, melody_file=None, vocal_file=None, mixed_file=None):
    """
    Upload specific job result files to GCP.
    
    Args:
        job_id: The job ID
        input_file: Path to the input audio file
        melody_file: Path to the generated MIDI file
        vocal_file: Path to the vocal audio file
        mixed_file: Path to the mixed audio file
        
    Returns:
        Dictionary with file types and their public URLs
    """
    urls = {}
    
    try:
        # Upload input file if provided
        if input_file and os.path.exists(input_file):
            filename = os.path.basename(input_file)
            gcp_path = f"job_{job_id}/input/{filename}"
            url = upload_file(input_file, gcp_path)
            if url:
                urls["input"] = url
        
        # Upload melody file if provided
        if melody_file and os.path.exists(melody_file):
            filename = os.path.basename(melody_file)
            gcp_path = f"job_{job_id}/melody/{filename}"
            url = upload_file(melody_file, gcp_path)
            if url:
                urls["melody"] = url
        
        # Upload vocal file if provided
        if vocal_file and os.path.exists(vocal_file):
            filename = os.path.basename(vocal_file)
            gcp_path = f"job_{job_id}/vocal/{filename}"
            url = upload_file(vocal_file, gcp_path)
            if url:
                urls["vocal"] = url
        
        # Upload mixed file if provided
        if mixed_file and os.path.exists(mixed_file):
            filename = os.path.basename(mixed_file)
            gcp_path = f"job_{job_id}/vocal/{filename}"
            url = upload_file(mixed_file, gcp_path)
            if url:
                urls["mixed"] = url
        
        logger.info(f"Uploaded result files for job {job_id}")
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading job results: {str(e)}")
        return urls  

def upload_job_files_to_gcp(job_id, vocal_path=None, mixed_path=None, midi_path=None):
    """
    Compatibility function to match the existing code in job_manager.py
    
    Args:
        job_id: The job ID
        vocal_path: Path to the vocal file
        mixed_path: Path to the mixed audio file
        midi_path: Path to the MIDI file
        
    Returns:
        Dictionary with file types as keys and GCP URLs as values
    """
    # This is just a wrapper around upload_job_results
    return upload_job_results(job_id, 
                             input_file=None,  # We don't have input file here
                             melody_file=midi_path, 
                             vocal_file=vocal_path, 
                             mixed_file=mixed_path)