# gcp_storage.py
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
    Handles model-specific directories (set1, set2) and variant subdirectories.
    
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
        
        # Get model set from job parameters in database
        model_set = "set1"  # Default
        batch_size = 1      # Default
        try:
            from models import SessionLocal, Job
            session = SessionLocal()
            job = session.query(Job).filter(Job.id == job_id).first()
            if job and job.parameters:
                params = dict(param.split('=') for param in job.parameters.split(',') if '=' in param)
                if 'model_set' in params:
                    model_set = params.get('model_set', 'set1')
                    logger.info(f"Found model_set={model_set} in job parameters")
                if 'batch_size' in params:
                    batch_size = int(params.get('batch_size', 1))
                    logger.info(f"Found batch_size={batch_size} in job parameters")
            session.close()
        except Exception as e:
            logger.error(f"Error getting parameters from database: {str(e)}")
        
        # Define model suffix based on model_set
        model_suffix = f"_{model_set}" if model_set != "" else ""
        
        # Define job-specific directories
        job_input_dir = os.path.join(shared_dir, "input", f"job_{job_id}")
        job_melody_dir = os.path.join(shared_dir, f"melody_results{model_suffix}", f"job_{job_id}")
        job_vocal_dir = os.path.join(shared_dir, f"vocal_results{model_suffix}", f"job_{job_id}")
        
        logger.info(f"Uploading files for job {job_id} with model_set={model_set}, batch_size={batch_size}")
        logger.info(f"Looking in directories: {job_input_dir}, {job_melody_dir}, {job_vocal_dir}")
        
        # Upload input files
        input_files = glob.glob(os.path.join(job_input_dir, "*"))
        for input_file in input_files:
            if os.path.isfile(input_file):  # Only upload files, not directories
                filename = os.path.basename(input_file)
                gcp_path = f"{timestamp_folder}/input/{filename}"
                url = upload_file(input_file, gcp_path)
                if url:
                    urls[f"input_{filename}"] = url
        
        # Upload melody files - including all files in the directory
        melody_files = glob.glob(os.path.join(job_melody_dir, "*"))
        for melody_file in melody_files:
            if os.path.isfile(melody_file):  # Only upload files, not directories
                filename = os.path.basename(melody_file)
                gcp_path = f"{timestamp_folder}/melody/{filename}"
                url = upload_file(melody_file, gcp_path)
                if url:
                    urls[f"melody_{filename}"] = url
        
        # Handle vocal files differently based on batch_size
        if batch_size > 1:
            # For batch mode, check for variant subdirectories
            for i in range(1, batch_size + 1):
                variant_dir = os.path.join(job_vocal_dir, f"variant_{i}")
                if os.path.exists(variant_dir) and os.path.isdir(variant_dir):
                    # Upload all files in this variant directory
                    variant_urls = upload_directory_recursively(
                        variant_dir, 
                        f"vocal/variant_{i}", 
                        timestamp_folder
                    )
                    # Add variant URLs to the main URLs dictionary
                    for key, url in variant_urls.items():
                        urls[f"variant_{i}_{key}"] = url
        else:
            # For single track mode, upload all files in the vocal directory
            vocal_files = glob.glob(os.path.join(job_vocal_dir, "*"))
            for vocal_file in vocal_files:
                if os.path.isfile(vocal_file):  # Only upload files, not directories
                    filename = os.path.basename(vocal_file)
                    gcp_path = f"{timestamp_folder}/vocal/{filename}"
                    url = upload_file(vocal_file, gcp_path)
                    if url:
                        urls[f"vocal_{filename}"] = url
        
        logger.info(f"Uploaded {len(urls)} files for job {job_id} with timestamp {timestamp}")
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading job files: {str(e)}")
        return urls  # Return whatever was successfully uploaded

def upload_directory_recursively(base_dir, gcp_base_path, timestamp_folder):
    """
    Recursively upload all files in a directory and its subdirectories to GCP.
    
    Args:
        base_dir: Base directory to upload
        gcp_base_path: Base path in GCP bucket
        timestamp_folder: Timestamp folder name for organizing uploads
        
    Returns:
        Dictionary with file paths and their public URLs
    """
    urls = {}
    
    try:
        if not os.path.exists(base_dir):
            logger.warning(f"Directory not found: {base_dir}")
            return urls
            
        # Walk through all files in the directory and subdirectories
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                # Get the full path to the file
                file_path = os.path.join(root, file)
                
                # Create a relative path from the base directory
                rel_path = os.path.relpath(file_path, os.path.dirname(base_dir))
                
                # Create the GCP path
                gcp_path = f"{timestamp_folder}/{gcp_base_path}/{rel_path}"
                
                # Upload the file
                url = upload_file(file_path, gcp_path)
                if url:
                    # Use the relative path as the key
                    urls[rel_path] = url
        
        logger.info(f"Uploaded {len(urls)} files from directory {base_dir}")
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading directory {base_dir}: {str(e)}")
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
        
        # Get model set from job parameters in database
        model_set = "set1"  # Default
        try:
            from models import SessionLocal, Job
            session = SessionLocal()
            job = session.query(Job).filter(Job.id == job_id).first()
            if job and job.parameters:
                params = dict(param.split('=') for param in job.parameters.split(','))
                if 'model_set' in params:
                    model_set = params.get('model_set', 'set1')
                    logger.info(f"Found model_set={model_set} in job parameters")
            session.close()
        except Exception as e:
            logger.error(f"Error getting model_set from database: {str(e)}")
        
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