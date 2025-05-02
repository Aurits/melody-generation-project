#!/bin/bash
set -e

echo "Waiting for the database to be available..."
# Increase sleep time if needed (e.g., 10 seconds)
sleep 10

echo "Running Alembic migrations..."
alembic upgrade head

# Try to install the melody generation and vocal mixing packages
echo "Attempting to install melody generation and vocal mixing packages..."
pip install --extra-index-url https://download.pytorch.org/whl/cu124 git+https://github.com/satoshi-suehiro/tmik_melody_generation.git@prod || echo "Failed to install melody generation package, will use Docker containers instead"
pip install git+https://github.com/satoshi-suehiro/tmik_vocalmix.git@prod || echo "Failed to install vocal mixing package, will use Docker containers instead"

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

# Try to download and set up configuration and checkpoint files
echo "Attempting to download configuration and checkpoint files..."
if [ ! -d "/app/configs" ] || [ ! -d "/app/checkpoints" ]; then
    # Download the configuration and checkpoint files
    echo "Downloading configuration and checkpoint files..."
    mkdir -p /tmp
    gdown --id 16g5ED0sLY12q73a5JRVigRcOJsXirV9I -O /tmp/config_checkpoint.zip || echo "Failed to download configuration and checkpoint files"
    
    # Extract the files if download was successful
    if [ -f "/tmp/config_checkpoint.zip" ]; then
        echo "Extracting configuration and checkpoint files..."
        mkdir -p /app/configs
        mkdir -p /app/checkpoints
        unzip -q /tmp/config_checkpoint.zip -d /tmp/config_checkpoint
        
        # Move files to appropriate directories
        if [ -d "/tmp/config_checkpoint/configs" ]; then
            cp -r /tmp/config_checkpoint/configs/* /app/configs/
        fi
        
        if [ -d "/tmp/config_checkpoint/checkpoints" ]; then
            cp -r /tmp/config_checkpoint/checkpoints/* /app/checkpoints/
        fi
        
        # Clean up
        rm -rf /tmp/config_checkpoint
        rm /tmp/config_checkpoint.zip
    fi
fi

# Verify the installation
echo "Checking installation..."
if [ -d "/app/dreamtonics_sdk" ]; then
    echo "Dreamtonics SDK is installed"
else
    echo "Dreamtonics SDK is not installed, will use Docker containers instead"
fi

if [ -d "/app/configs" ] && [ -d "/app/checkpoints" ]; then
    echo "Configuration and checkpoint files are installed"
else
    echo "Configuration and checkpoint files are not installed, will use Docker containers instead"
fi

echo "Starting the application..."
exec python app.py