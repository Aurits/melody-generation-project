#!/bin/bash

# Log file inside the project
LOG_FILE="./gpu-container-startup.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Create or truncate log file
> "$LOG_FILE"

log_message "Starting melody generation services..."

# Remove shared_data directory if it exists
if [ -d "./shared_data" ]; then
    log_message "Removing shared_data directory..."
    sudo rm -rf "./shared_data"
    log_message "shared_data directory removed successfully."
else
    log_message "No shared_data directory found to remove."
fi

log_message "Checking for GPU availability..."

# Wait until nvidia-smi works
while ! nvidia-smi &>/dev/null; do
    log_message "Waiting for NVIDIA drivers to initialize... (retrying in 5 seconds)"
    sleep 5
done

# Get GPU details once available
GPU_INFO=$(nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu --format=csv,noheader)
log_message "GPU is now available: $GPU_INFO"

# Stop any existing containers
log_message "Stopping any running containers..."
docker compose down

# Start containers
log_message "Starting Docker containers..."
docker compose up -d

# Verify containers started properly
sleep 10
RUNNING_CONTAINERS=$(docker ps --format '{{.Names}}' | grep -E 'melody-generation|vocal-mix|integrated-app|postgres-database')
log_message "Running containers: $RUNNING_CONTAINERS"

# Check if melody-generation container has GPU access
log_message "Verifying GPU availability in melody-generation container..."
GPU_CHECK=$(docker exec melody-generation nvidia-smi 2>&1 || echo "Failed to access GPU")
log_message "GPU check result: $GPU_CHECK"

echo "Services started. Check $LOG_FILE for details."