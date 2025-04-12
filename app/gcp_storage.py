# gcp_storage.py
# Enhanced module for uploading melody generation files to Google Cloud Storage with timestamps

import os
import json
import logging
from google.cloud import storage
import glob
import datetime

# Set up logging
logger = logging.getLogger(__name__)

# Path to the service account key file
SERVICE_ACCOUNT_FILE = "access.json"

# GCP bucket name
BUCKET_NAME = "melody_generation_api_bucket"

def initialize_gcp_credentials():
    """
    Initialize GCP credentials and validate access to the bucket.
    Returns True if successful, False otherwise.
    """
    try:
        client = get_storage_client()
        if not client:
            logger.error("Failed to create storage client")
            return False
            
        # Test if we can access the bucket
        bucket = client.bucket(BUCKET_NAME)
        if bucket.exists():
            logger.info(f"Successfully connected to bucket: {BUCKET_NAME}")
            return True
        else:
            logger.error(f"Bucket {BUCKET_NAME} does not exist")
            return False
    except Exception as e:
        logger.error(f"Error initializing GCP credentials: {str(e)}")
        return False

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
    Upload a single file to GCP Storage and generate a signed URL.
    
    Args:
        local_file_path: Path to the local file
        gcp_path: Destination path in GCP bucket
        
    Returns:
        Signed URL of the uploaded file if successful, None otherwise
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
        
        # Generate a signed URL with expiration time
        import datetime
        
        # Generate a signed URL that expires in 7 days
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(days=7),
            method="GET"
        )
        
        logger.info(f"Uploaded {local_file_path} to gs://{BUCKET_NAME}/{gcp_path}")
        logger.info(f"Created signed URL with 7-day expiration")
        return signed_url
        
    except Exception as e:
        logger.error(f"Error uploading {local_file_path}: {str(e)}")
        return None

def upload_job_files(job_id, shared_dir):
    """
    Upload all files for a specific job to GCP with timestamp in folder name.
    
    Args:
        job_id: The job ID
        shared_dir: Base shared directory containing job files
        
    Returns:
        Dictionary with file types and their public URLs
    """
    urls = {}
    
    try:
        # Generate timestamp for folder names
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_folder = f"job_{job_id}_{timestamp}"
        
        # Define job-specific directories
        job_input_dir = os.path.join(shared_dir, "input", f"job_{job_id}")
        job_melody_dir = os.path.join(shared_dir, "melody_results", f"job_{job_id}")
        job_vocal_dir = os.path.join(shared_dir, "vocal_results", f"job_{job_id}")
        
        # Upload input files
        input_files = glob.glob(os.path.join(job_input_dir, "*"))
        for input_file in input_files:
            filename = os.path.basename(input_file)
            gcp_path = f"{timestamp_folder}/input/{filename}"
            url = upload_file(input_file, gcp_path)
            if url:
                urls[f"input_{filename}"] = url
        
        # Upload melody files - including all files in the directory
        melody_files = glob.glob(os.path.join(job_melody_dir, "*"))
        for melody_file in melody_files:
            filename = os.path.basename(melody_file)
            gcp_path = f"{timestamp_folder}/melody/{filename}"
            url = upload_file(melody_file, gcp_path)
            if url:
                urls[f"melody_{filename}"] = url
                
        # Also check for melody files that might be in the base melody_results directory
        base_melody_files = glob.glob(os.path.join(shared_dir, "melody_results", "*"))
        for melody_file in base_melody_files:
            # Only upload files, not directories
            if os.path.isfile(melody_file):
                filename = os.path.basename(melody_file)
                gcp_path = f"{timestamp_folder}/melody/base_{filename}"
                url = upload_file(melody_file, gcp_path)
                if url:
                    urls[f"melody_base_{filename}"] = url
        
        # Upload vocal files - including all files in the directory
        vocal_files = glob.glob(os.path.join(job_vocal_dir, "*"))
        for vocal_file in vocal_files:
            filename = os.path.basename(vocal_file)
            gcp_path = f"{timestamp_folder}/vocal/{filename}"
            url = upload_file(vocal_file, gcp_path)
            if url:
                urls[f"vocal_{filename}"] = url
                
        # Also check for vocal files that might be in the base vocal_results directory
        base_vocal_files = glob.glob(os.path.join(shared_dir, "vocal_results", "*"))
        for vocal_file in base_vocal_files:
            # Only upload files, not directories
            if os.path.isfile(vocal_file):
                filename = os.path.basename(vocal_file)
                gcp_path = f"{timestamp_folder}/vocal/base_{filename}"
                url = upload_file(vocal_file, gcp_path)
                if url:
                    urls[f"vocal_base_{filename}"] = url
        
        logger.info(f"Uploaded {len(urls)} files for job {job_id} with timestamp {timestamp}")
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading job files: {str(e)}")
        return urls  # Return whatever was successfully uploaded

def upload_job_results(job_id, input_file=None, melody_file=None, vocal_file=None, mixed_file=None):
    """
    Upload specific job result files to GCP with timestamp in folder name.
    
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
        # Generate timestamp for folder names
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_folder = f"job_{job_id}_{timestamp}"
        
        # Upload input file if provided
        if input_file and os.path.exists(input_file):
            filename = os.path.basename(input_file)
            gcp_path = f"{timestamp_folder}/input/{filename}"
            url = upload_file(input_file, gcp_path)
            if url:
                urls["input"] = url
        
        # Check for other files in the melody directory
        if melody_file and os.path.exists(melody_file):
            # Get the directory containing the melody file
            melody_dir = os.path.dirname(melody_file)
            
            # Upload all files in the melody directory
            for file in glob.glob(os.path.join(melody_dir, "*")):
                filename = os.path.basename(file)
                gcp_path = f"{timestamp_folder}/melody/{filename}"
                url = upload_file(file, gcp_path)
                if url:
                    if file == melody_file:
                        urls["melody"] = url
                    else:
                        urls[f"melody_{filename}"] = url
        
        # Check for other files in the vocal directory
        vocal_dir = None
        if vocal_file and os.path.exists(vocal_file):
            vocal_dir = os.path.dirname(vocal_file)
            
            # Upload all files in the vocal directory
            for file in glob.glob(os.path.join(vocal_dir, "*")):
                filename = os.path.basename(file)
                gcp_path = f"{timestamp_folder}/vocal/{filename}"
                url = upload_file(file, gcp_path)
                if url:
                    if file == vocal_file:
                        urls["vocal"] = url
                    elif file == mixed_file:
                        urls["mixed"] = url
                    else:
                        urls[f"vocal_{filename}"] = url
        
        # If mixed_file is in a different directory than vocal_file
        if mixed_file and os.path.exists(mixed_file) and (not vocal_dir or os.path.dirname(mixed_file) != vocal_dir):
            mixed_dir = os.path.dirname(mixed_file)
            
            # Upload all files in the mixed directory
            for file in glob.glob(os.path.join(mixed_dir, "*")):
                filename = os.path.basename(file)
                gcp_path = f"{timestamp_folder}/vocal/{filename}"
                url = upload_file(file, gcp_path)
                if url:
                    if file == mixed_file:
                        urls["mixed"] = url
                    else:
                        urls[f"mixed_{filename}"] = url
        
        logger.info(f"Uploaded result files for job {job_id} with timestamp {timestamp}")
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
    # This is now a wrapper around upload_job_results with enhanced directory scanning
    return upload_job_results(job_id, 
                             input_file=None,  # We don't have input file here
                             melody_file=midi_path, 
                             vocal_file=vocal_path, 
                             mixed_file=mixed_path)