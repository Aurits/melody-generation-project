# Changelog

All notable changes to the Melody Generation Project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GCP bucket integration for storing generated files
- Job-specific directories for better organization of outputs
- Improved file naming with job IDs and unique identifiers
- Job duration tracking and display in the UI

### Fixed
- Fixed ZeroDivisionError by adding `--one_shot_generation` flag
- Fixed BPM handling when start time is zero
- Fixed issue with missing files by checking multiple MIDI file locations
- Added `--use_handinputed_bpm` flag to fix IndexError

### Changed
- Updated Docker configuration with restart policies
- Improved UI with better job status display
- Enhanced error handling and logging

## [1.0.0] - 2024-04-11

### Added
- Initial release of the Melody Generator application
- Gradio web interface for uploading backing tracks
- Docker containerization for melody generation and vocal mixing
- Job queue system for background processing
- Basic parameter controls (start time, BPM, seed)
- Results preview with audio playback
- MIDI file generation and download