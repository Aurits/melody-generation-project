# gcp_storage.py
# Module for uploading files to Google Cloud Platform storage buckets

import os
import json
import logging
from google.cloud import storage
from google.oauth2 import service_account
import tempfile

# Set up logging
logger = logging.getLogger(__name__)

# Path to the service account key file
SERVICE_ACCOUNT_KEY = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", None)

# GCP bucket name
BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "melody_generation_api_bucket")

def get_storage_client():
    """
    Create and return a Google Cloud Storage client using service account credentials.
    Returns None if credentials are not available or invalid.
    """
    try:
        # If SERVICE_ACCOUNT_KEY is provided as an environment variable with the JSON content
        if SERVICE_ACCOUNT_KEY and SERVICE_ACCOUNT_KEY.startswith('{'):
            # Parse the JSON string
            credentials_info = json.loads(SERVICE_ACCOUNT_KEY)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            return storage.Client(credentials=credentials)
        
        # If SERVICE_ACCOUNT_KEY is a path to a file
        elif SERVICE_ACCOUNT_KEY and os.path.exists(SERVICE_ACCOUNT_KEY):
            return storage.Client.from_service_account_json(SERVICE_ACCOUNT_KEY)
        
        # If credentials are not explicitly provided, try default credentials
        else:
            logger.warning("No explicit GCP credentials provided, trying default credentials")
            return storage.Client()
            
    except Exception as e:
        logger.error(f"Failed to create GCP storage client: {str(e)}", exc_info=True)
        return None

def upload_file_to_gcp(local_file_path, destination_blob_name=None, bucket_name=None):
    """
    Upload a file to Google Cloud Storage bucket.
    
    Args:
        local_file_path: Path to the local file to upload
        destination_blob_name: Name to give the file in GCP (defaults to filename)
        bucket_name: Name of the GCP bucket (defaults to BUCKET_NAME env var)
        
    Returns:
        Public URL of the uploaded file if successful, None otherwise
    """
    if not os.path.exists(local_file_path):
        logger.error(f"File not found: {local_file_path}")
        return None
        
    # Use default bucket name if not specified
    if not bucket_name:
        bucket_name = BUCKET_NAME
        
    # Use filename as destination blob name if not specified
    if not destination_blob_name:
        destination_blob_name = os.path.basename(local_file_path)
        
    try:
        # Get storage client
        client = get_storage_client()
        if not client:
            logger.error("Could not create GCP storage client")
            return None
            
        # Get bucket
        bucket = client.bucket(bucket_name)
        
        # Create blob and upload
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_file_path)
        
        # Make the blob publicly accessible
        blob.make_public()
        
        # Get the public URL
        public_url = blob.public_url
        
        logger.info(f"File {local_file_path} uploaded to {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error uploading file to GCP: {str(e)}", exc_info=True)
        return None

def upload_job_files_to_gcp(job_id, vocal_path=None, mixed_path=None, midi_path=None):
    """
    Upload job output files to GCP bucket and return URLs.
    
    Args:
        job_id: The job ID
        vocal_path: Path to the vocal file
        mixed_path: Path to the mixed audio file
        midi_path: Path to the MIDI file
        
    Returns:
        Dictionary with file types as keys and GCP URLs as values
    """
    urls = {}
    
    try:
        # Create a folder structure in GCP based on job ID
        folder_prefix = f"job_{job_id}/"
        
        # Upload vocal file if provided
        if vocal_path and os.path.exists(vocal_path):
            vocal_blob_name = folder_prefix + os.path.basename(vocal_path)
            vocal_url = upload_file_to_gcp(vocal_path, vocal_blob_name)
            if vocal_url:
                urls['vocal'] = vocal_url
                
        # Upload mixed file if provided
        if mixed_path and os.path.exists(mixed_path):
            mixed_blob_name = folder_prefix + os.path.basename(mixed_path)
            mixed_url = upload_file_to_gcp(mixed_path, mixed_blob_name)
            if mixed_url:
                urls['mixed'] = mixed_url
                
        # Upload MIDI file if provided
        if midi_path and os.path.exists(midi_path):
            midi_blob_name = folder_prefix + os.path.basename(midi_path)
            midi_url = upload_file_to_gcp(midi_path, midi_blob_name)
            if midi_url:
                urls['midi'] = midi_url
                
        return urls
        
    except Exception as e:
        logger.error(f"Error uploading job files to GCP: {str(e)}", exc_info=True)
        return urls  # Return whatever URLs were successfully generated

def save_service_account_key(key_json):
    """
    Save the service account key JSON to a temporary file and return the path.
    This is useful when the key is provided as an environment variable.
    
    Args:
        key_json: Service account key JSON string or dictionary
        
    Returns:
        Path to the temporary file containing the key
    """
    try:
        # Create a temporary file
        fd, path = tempfile.mkstemp(suffix='.json')
        
        # Convert dict to JSON string if needed
        if isinstance(key_json, dict):
            key_json = json.dumps(key_json)
            
        # Write the key to the file
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(key_json)
            
        return path
        
    except Exception as e:
        logger.error(f"Error saving service account key: {str(e)}", exc_info=True)
        return None

def initialize_gcp_credentials(service_account_json=None):
    """
    Initialize GCP credentials from the provided service account JSON.
    This function can be called at application startup.
    
    Args:
        service_account_json: Service account JSON string or dictionary
        
    Returns:
        True if initialization was successful, False otherwise
    """
    global SERVICE_ACCOUNT_KEY
    
    try:
        if service_account_json:
            # Save the service account key to a temporary file
            key_path = save_service_account_key(service_account_json)
            if key_path:
                SERVICE_ACCOUNT_KEY = key_path
                logger.info("GCP credentials initialized successfully")
                return True
                
        logger.warning("No service account JSON provided for GCP initialization")
        return False
        
    except Exception as e:
        logger.error(f"Error initializing GCP credentials: {str(e)}", exc_info=True)
        return False