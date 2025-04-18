# Changelog

All notable changes to the Melody Generation Project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GCP credentials initialization and update to job manager
- GCP storage module for file uploads and job results
- JSON import for enhanced data handling in services and job manager
- CODEOWNERS file to define repository ownership
- Job-specific seed parameters support
- One-shot generation flag to melody generation command
- Timestamps in folder names for GCP uploads
- Signed URLs instead of public access for uploaded files

### Changed
- Refactored job parameter handling to use dedicated JSON column for GCP URLs
- Refactored GCP upload functionality with new upload methods
- Refactored job processing to improve parameter handling
- Enhanced job processing to include beat mix file handling and store GCP URLs as JSON
- Enhanced job display with improved file listing styling and toggle switch functionality
- Simplified file handling in job display
- Improved toggle button implementation
- Updated the upload_file function to generate signed URLs
- Refactored recent jobs display to use HTML table format
- Enhanced file scanning for GCP uploads
- Enhanced Melody Generator with job-specific directory creation
- Updated melody and vocal results with new data and files
- Improved file labeling in job display

### Fixed
- Increased max attempts for job status polling to improve reliability
- Updated .gitignore to include shared data and ensure services in docker-compose restart automatically
- Updated .gitignore to include specific directories for melody generation
- Excluded specific directories in .gitignore and added job list functionality
- Removed mkdocs documentation

### Initial Setup
- First commit (April 9, 2025)
- Created README.md
- Updated the readme

### Merged Pull Requests
- Merge pull request #7 from Aurits/dev
- Merge pull request #6 from Aurits/dev
- Merge pull request #5 from Aurits/dev

## [1.0.0] - 2024-04-11

### Added
- Initial release of the Melody Generator application
- Gradio web interface for uploading backing tracks
- Docker containerization for melody generation and vocal mixing
- Job queue system for background processing
- Basic parameter controls (start time, BPM, seed)
- Results preview with audio playback
- MIDI file generation and download