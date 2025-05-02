import os
import argparse
import gdown
import re

def extract_file_id(drive_link):
    """Extract the file ID from various Google Drive link formats."""
    # Pattern for links like: https://drive.google.com/file/d/{FILE_ID}/view
    file_pattern = r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)'
    
    # Pattern for links like: https://drive.google.com/open?id={FILE_ID}
    open_pattern = r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)'
    
    # Pattern for links like: https://docs.google.com/document/d/{FILE_ID}/edit
    docs_pattern = r'docs\.google\.com/\w+/d/([a-zA-Z0-9_-]+)'
    
    # Pattern for direct file IDs
    direct_id_pattern = r'^([a-zA-Z0-9_-]{25,})(\/.*)?$'
    
    # Try to match each pattern
    for pattern in [file_pattern, open_pattern, docs_pattern, direct_id_pattern]:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    
    return None

def download_file(drive_link, output_path=None, quiet=False):
    """
    Download a file from Google Drive.
    
    Args:
        drive_link (str): Google Drive link or file ID
        output_path (str, optional): Path to save the file. If None, saves to current directory.
        quiet (bool, optional): If True, suppresses progress bar. Defaults to False.
    
    Returns:
        str: Path to the downloaded file or None if download failed
    """
    try:
        # Check if the link is a direct file ID or a URL
        if '/' in drive_link and 'drive.google.com' in drive_link:
            file_id = extract_file_id(drive_link)
            if not file_id:
                print(f"Error: Could not extract file ID from {drive_link}")
                return None
        else:
            # Assume it's already a file ID
            file_id = drive_link
        
        # Create the direct download URL
        url = f"https://drive.google.com/uc?id={file_id}"
        
        # Download the file
        output = gdown.download(url, output=output_path, quiet=quiet)
        
        if output:
            print(f"Successfully downloaded file to: {output}")
            return output
        else:
            print("Download failed. The file might be too large or require authentication.")
            return None
            
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Download files from Google Drive")
    parser.add_argument("link", help="Google Drive link or file ID")
    parser.add_argument("-o", "--output", help="Output file path (optional)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress bar")
    
    args = parser.parse_args()
    
    download_file(args.link, args.output, args.quiet)

if __name__ == "__main__":
    main()

# Example usage:
# python drive_downloader.py "https://drive.google.com/file/d/1a2b3c4d5e6f7g8h9i0j/view?usp=sharing" -o "downloaded_file.pdf"
# python drive_downloader.py "1a2b3c4d5e6f7g8h9i0j" -o "downloaded_file.pdf"