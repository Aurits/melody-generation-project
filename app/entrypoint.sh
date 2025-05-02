#!/bin/bash
set -e

echo "Waiting for the database to be available..."
# Increase sleep time if needed (e.g., 10 seconds)
sleep 10

echo "Running Alembic migrations..."
alembic upgrade head

# Load GitHub PAT from .env file if it exists
if [ -f "/app/.env" ]; then
    echo "Loading GitHub PAT from .env file..."
    # Extract the PAT from the .env file
    GITHUB_PAT=$(grep -o "PAT=.*" /app/.env | cut -d'=' -f2)
    
    if [ -n "$GITHUB_PAT" ]; then
        echo "GitHub PAT found in .env file, attempting to install packages using token authentication..."
        # Use the PAT in the URL for authentication
        pip install --extra-index-url https://download.pytorch.org/whl/cu124 git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git@prod || echo "Failed to install melody generation package, will use Docker containers instead"
        pip install git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_vocalmix.git@prod || echo "Failed to install vocal mixing package, will use Docker containers instead"
    else
        echo "No GitHub PAT found in .env file, skipping package installation"
        echo "Will use Docker containers for model set 1"
    fi
else
    echo "No .env file found, skipping package installation"
    echo "Will use Docker containers for model set 1"
fi

# Install gdown if not already installed
pip install gdown

# Try to download and set up the Dreamtonics SDK
echo "Attempting to download and set up Dreamtonics SDK..."
if [ ! -d "/app/dreamtonics_sdk" ]; then
    # Download the SDK
    echo "Downloading Dreamtonics SDK..."
    mkdir -p /tmp
    gdown --id 1jo0Vwsoud1IUHWO08xsUrMnvOdOX3EXj -O /tmp/dreamtonics_sdk.zip || echo "Failed to download Dreamtonics SDK"
    
    # Extract the SDK if download was successful
    if [ -f "/tmp/dreamtonics_sdk.zip" ]; then
        echo "Extracting Dreamtonics SDK..."
        mkdir -p /app
        unzip -q /tmp/dreamtonics_sdk.zip -d /app || echo "Failed to extract Dreamtonics SDK"
        rm /tmp/dreamtonics_sdk.zip
    fi
fi

# Create directories for checkpoints and configs
mkdir -p /app/checkpoints
mkdir -p /app/configs

# Copy the checkpoint files from the local directory if they exist
echo "Setting up checkpoint and configuration files..."
if [ -d "/app/model_files/checkpoints" ]; then
    echo "Copying checkpoint files from local directory..."
    cp -r /app/model_files/checkpoints/* /app/checkpoints/
    
    # Copy config files if they exist
    if [ -d "/app/model_files/configs" ]; then
        cp -r /app/model_files/configs/* /app/configs/
    fi
else
    echo "Local checkpoint files not found, attempting to download..."
    # Try to download and set up configuration and checkpoint files
    gdown --id 16g5ED0sLY12q73a5JRVigRcOJsXirV9I -O /tmp/config_checkpoint.zip || echo "Failed to download configuration and checkpoint files"
    
    # Extract the files if download was successful
    if [ -f "/tmp/config_checkpoint.zip" ]; then
        echo "Extracting configuration and checkpoint files..."
        mkdir -p /tmp/config_checkpoint
        unzip -q /tmp/config_checkpoint.zip -d /tmp/config_checkpoint
        
        # List the contents to debug
        echo "Contents of extracted archive:"
        find /tmp/config_checkpoint -type f | sort
        
        # Try different possible directory structures
        if [ -d "/tmp/config_checkpoint/checkpoints" ]; then
            echo "Found /tmp/config_checkpoint/checkpoints directory"
            cp -r /tmp/config_checkpoint/checkpoints/* /app/checkpoints/
        elif [ -d "/tmp/config_checkpoint/checkpoint" ]; then
            echo "Found /tmp/config_checkpoint/checkpoint directory"
            cp -r /tmp/config_checkpoint/checkpoint/* /app/checkpoints/
        else
            # Try to find directories that might contain checkpoint files
            echo "Searching for checkpoint directories..."
            find /tmp/config_checkpoint -name "*.pth" -o -name "*.pt" -o -name "*.json" -o -name "*.yaml" | while read file; do
                dir=$(dirname "$file")
                if [ -d "$dir" ] && [[ "$dir" == *"checkpoint"* || "$dir" == *"model"* ]]; then
                    echo "Found potential checkpoint directory: $dir"
                    cp -r "$dir"/* /app/checkpoints/
                fi
            done
        fi
        
        if [ -d "/tmp/config_checkpoint/configs" ]; then
            echo "Found /tmp/config_checkpoint/configs directory"
            cp -r /tmp/config_checkpoint/configs/* /app/configs/
        elif [ -d "/tmp/config_checkpoint/config" ]; then
            echo "Found /tmp/config_checkpoint/config directory"
            cp -r /tmp/config_checkpoint/config/* /app/configs/
        else
            # Try to find YAML files that might be config files
            echo "Searching for config files..."
            find /tmp/config_checkpoint -name "*.yaml" | while read file; do
                echo "Found potential config file: $file"
                cp "$file" /app/configs/
            done
        fi
        
        # Clean up
        rm -rf /tmp/config_checkpoint
        rm /tmp/config_checkpoint.zip
    fi
fi

# Define the checkpoint path based on the directory structure we saw in the image
CHECKPOINT_PATH="/app/checkpoints/test2300_cqt_realTP_continuous_270000"
CONFIG_PATH="/app/configs/default.yaml"

# If the specific checkpoint directory doesn't exist, try to find any checkpoint directory
if [ ! -d "$CHECKPOINT_PATH" ]; then
    echo "Specific checkpoint directory not found, searching for alternatives..."
    # Find the first directory in /app/checkpoints
    FIRST_CHECKPOINT_DIR=$(find /app/checkpoints -type d -mindepth 1 -maxdepth 1 | head -n 1)
    if [ -n "$FIRST_CHECKPOINT_DIR" ]; then
        echo "Found alternative checkpoint directory: $FIRST_CHECKPOINT_DIR"
        CHECKPOINT_PATH="$FIRST_CHECKPOINT_DIR"
    fi
fi

# If the specific config file doesn't exist, try to find any YAML file
if [ ! -f "$CONFIG_PATH" ]; then
    echo "Specific config file not found, searching for alternatives..."
    # Find the first YAML file in /app/configs
    FIRST_CONFIG_FILE=$(find /app/configs -name "*.yaml" | head -n 1)
    if [ -n "$FIRST_CONFIG_FILE" ]; then
        echo "Found alternative config file: $FIRST_CONFIG_FILE"
        CONFIG_PATH="$FIRST_CONFIG_FILE"
    fi
fi

# Verify the installation
echo "Checking installation..."
if [ -d "/app/dreamtonics_sdk" ]; then
    echo "Dreamtonics SDK is installed"
else
    echo "Dreamtonics SDK is not installed, will use Docker containers instead"
fi

if [ -d "$CHECKPOINT_PATH" ] && [ -f "$CONFIG_PATH" ]; then
    echo "Configuration and checkpoint files are installed"
    echo "Checkpoint path: $CHECKPOINT_PATH"
    echo "Config path: $CONFIG_PATH"
    
    # Export environment variables for use in the application
    export MODEL_CHECKPOINT_PATH="$CHECKPOINT_PATH"
    export MODEL_CONFIG_PATH="$CONFIG_PATH"
else
    echo "Configuration and checkpoint files are not installed or incomplete, will use Docker containers instead"
    # List what we have to debug
    echo "Available checkpoint directories:"
    find /app/checkpoints -type d | sort
    echo "Available config files:"
    find /app/configs -type f | sort
fi

echo "Starting the application..."
exec python app.py