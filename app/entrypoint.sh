#!/bin/bash
set -e

echo "Waiting for the database to be available..."
# Increase sleep time if needed (e.g., 10 seconds)
sleep 10

echo "Running Alembic migrations..."
alembic upgrade head

# Initialize package installation status flags
MELODY_GEN_INSTALLED=false
VOCALMIX_INSTALLED=false
SDK_INSTALLED=false
CHECKPOINT_FILES_INSTALLED=false
CONFIG_FILES_INSTALLED=false

# Load GitHub PAT from .env file if it exists
if [ -f "/app/.env" ]; then
    echo "Loading GitHub PAT from .env file..."
    # Extract the PAT from the .env file
    GITHUB_PAT=$(grep -o "PAT=.*" /app/.env | cut -d'=' -f2)
    
    if [ -n "$GITHUB_PAT" ]; then
        echo "GitHub PAT found in .env file, attempting to install packages using token authentication..."
        
        # Install melody_generation package
        echo "Installing melody_generation package..."
        # First make sure madmom is properly installed
        pip install --no-cache-dir git+https://github.com/CPJKU/madmom.git
        if [ $? -eq 0 ]; then
            echo "Successfully installed madmom dependency"
            
            # Now install the melody_generation package
            pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu124 git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git@prod
            if [ $? -eq 0 ]; then
                echo "Successfully installed melody_generation package"
                MELODY_GEN_INSTALLED=true
            else
                echo "Failed to install melody_generation package"
            fi
        else
            echo "Failed to install madmom dependency"
        fi
        
        # Install vocalmix package
        echo "Installing vocalmix package..."
        pip install --no-cache-dir git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_vocalmix.git@prod
        if [ $? -eq 0 ]; then
            echo "Successfully installed vocalmix package"
            VOCALMIX_INSTALLED=true
        else
            echo "Failed to install vocalmix package"
        fi
        
        # Verify installations by trying to import the modules
        echo "Verifying package installations..."
        python -c "import melody_generation; print('melody_generation package is importable')" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "melody_generation package is properly installed and importable"
            MELODY_GEN_INSTALLED=true
        else
            echo "melody_generation package is not importable"
            MELODY_GEN_INSTALLED=false
        fi
        
        python -c "import vocalmix; print('vocalmix package is importable')" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "vocalmix package is properly installed and importable"
            VOCALMIX_INSTALLED=true
        else
            echo "vocalmix package is not importable"
            VOCALMIX_INSTALLED=false
        fi
    else
        echo "No GitHub PAT found in .env file, skipping package installation"
        echo "Will use Docker containers for model set 1"
    fi
else
    echo "No .env file found, skipping package installation"
    echo "Will use Docker containers for model set 1"
fi

# Install gdown if not already installed
pip install --no-cache-dir gdown

# Setup Dreamtonics SDK
echo "Attempting to download and set up Dreamtonics SDK..."
if [ ! -d "/app/dreamtonics_sdk" ]; then
    # Download the SDK
    echo "Downloading Dreamtonics SDK..."
    mkdir -p /tmp
    gdown --id 1jo0Vwsoud1IUHWO08xsUrMnvOdOX3EXj -O /tmp/dreamtonics_sdk.zip
    if [ $? -eq 0 ]; then
        echo "Successfully downloaded Dreamtonics SDK"
        
        # Extract the SDK if download was successful
        if [ -f "/tmp/dreamtonics_sdk.zip" ]; then
            echo "Extracting Dreamtonics SDK..."
            mkdir -p /app
            unzip -q /tmp/dreamtonics_sdk.zip -d /app
            if [ $? -eq 0 ]; then
                echo "Successfully extracted Dreamtonics SDK"
                SDK_INSTALLED=true
                
                # Set proper permissions for all executables in the SDK
                echo "Setting permissions for Dreamtonics SDK executables..."
                find /app/dreamtonics_sdk -type f -name "*.so" -exec chmod +x {} \;
                find /app/dreamtonics_sdk -type f -name "example" -exec chmod +x {} \;
                find /app/dreamtonics_sdk -type d -name "build" -exec chmod -R 755 {} \;
            else
                echo "Failed to extract Dreamtonics SDK"
            fi
            rm /tmp/dreamtonics_sdk.zip
        fi
    else
        echo "Failed to download Dreamtonics SDK"
    fi
else
    echo "Dreamtonics SDK directory already exists"
    SDK_INSTALLED=true
    
    # Set proper permissions for all executables in the SDK
    echo "Setting permissions for Dreamtonics SDK executables..."
    find /app/dreamtonics_sdk -type f -name "*.so" -exec chmod +x {} \;
    find /app/dreamtonics_sdk -type f -name "example" -exec chmod +x {} \;
    find /app/dreamtonics_sdk -type d -name "build" -exec chmod -R 755 {} \;
fi

# Create directories for checkpoints and configs
mkdir -p /app/checkpoints
mkdir -p /app/configs

# Setup checkpoint and config files
echo "Setting up checkpoint and configuration files..."
if [ -d "/app/model_files/checkpoints" ]; then
    echo "Copying checkpoint files from local directory..."
    cp -r /app/model_files/checkpoints/* /app/checkpoints/
    if [ $? -eq 0 ]; then
        echo "Successfully copied checkpoint files"
        CHECKPOINT_FILES_INSTALLED=true
    fi
    
    # Copy config files if they exist
    if [ -d "/app/model_files/configs" ]; then
        cp -r /app/model_files/configs/* /app/configs/
        if [ $? -eq 0 ]; then
            echo "Successfully copied config files"
            CONFIG_FILES_INSTALLED=true
        fi
    fi
else
    echo "Local checkpoint files not found, attempting to download..."
    # Try to download and set up configuration and checkpoint files
    gdown --id 1CkBxeUm08jISvC0H3vdZkBLHhEBmop71 -O /tmp/config_checkpoint.zip
    if [ $? -eq 0 ]; then
        echo "Successfully downloaded configuration and checkpoint files"
        
        # Extract the files if download was successful
        if [ -f "/tmp/config_checkpoint.zip" ]; then
            echo "Extracting configuration and checkpoint files..."
            mkdir -p /tmp/config_checkpoint
            unzip -q /tmp/config_checkpoint.zip -d /tmp/config_checkpoint
            
            # Copy checkpoint files
            if [ -d "/tmp/config_checkpoint/checkpoints" ]; then
                cp -r /tmp/config_checkpoint/checkpoints/* /app/checkpoints/
                CHECKPOINT_FILES_INSTALLED=true
            elif [ -d "/tmp/config_checkpoint/checkpoint" ]; then
                cp -r /tmp/config_checkpoint/checkpoint/* /app/checkpoints/
                CHECKPOINT_FILES_INSTALLED=true
            fi
            
            # Copy config files
            if [ -d "/tmp/config_checkpoint/configs" ]; then
                cp -r /tmp/config_checkpoint/configs/* /app/configs/
                CONFIG_FILES_INSTALLED=true
            elif [ -d "/tmp/config_checkpoint/config" ]; then
                cp -r /tmp/config_checkpoint/config/* /app/configs/
                CONFIG_FILES_INSTALLED=true
            fi
            
            # Clean up
            rm -rf /tmp/config_checkpoint
            rm /tmp/config_checkpoint.zip
        fi
    fi
fi

# Default paths for checkpoint and config
CHECKPOINT_PATH="/app/checkpoints/test2300_cqt_realTP_continuous_270000"
CONFIG_PATH="/app/configs/default.yaml"

# Find alternative paths if defaults don't exist
if [ ! -d "$CHECKPOINT_PATH" ]; then
    FIRST_CHECKPOINT_DIR=$(find /app/checkpoints -type d -mindepth 1 -maxdepth 1 | head -n 1)
    if [ -n "$FIRST_CHECKPOINT_DIR" ]; then
        CHECKPOINT_PATH="$FIRST_CHECKPOINT_DIR"
        CHECKPOINT_FILES_INSTALLED=true
    fi
fi

if [ ! -f "$CONFIG_PATH" ]; then
    FIRST_CONFIG_FILE=$(find /app/configs -name "*.yaml" | head -n 1)
    if [ -n "$FIRST_CONFIG_FILE" ]; then
        CONFIG_PATH="$FIRST_CONFIG_FILE"
        CONFIG_FILES_INSTALLED=true
    fi
fi

# Export environment variables
export MODEL_CHECKPOINT_PATH="$CHECKPOINT_PATH"
export MODEL_CONFIG_PATH="$CONFIG_PATH"
export MELODY_GEN_INSTALLED
export VOCALMIX_INSTALLED
export SDK_INSTALLED
export CHECKPOINT_FILES_INSTALLED
export CONFIG_FILES_INSTALLED

# Create runtime environment file
echo "MODEL_CHECKPOINT_PATH=$CHECKPOINT_PATH" > /app/.env.runtime
echo "MODEL_CONFIG_PATH=$CONFIG_PATH" >> /app/.env.runtime
echo "MELODY_GEN_INSTALLED=$MELODY_GEN_INSTALLED" >> /app/.env.runtime
echo "VOCALMIX_INSTALLED=$VOCALMIX_INSTALLED" >> /app/.env.runtime
echo "SDK_INSTALLED=$SDK_INSTALLED" >> /app/.env.runtime
chmod 644 /app/.env.runtime

# Summary of installation status
echo "============================================"
echo "INSTALLATION STATUS SUMMARY"
echo "============================================"
echo "melody_generation package: $(if [ "$MELODY_GEN_INSTALLED" = true ]; then echo "INSTALLED"; else echo "NOT INSTALLED"; fi)"
echo "vocalmix package: $(if [ "$VOCALMIX_INSTALLED" = true ]; then echo "INSTALLED"; else echo "NOT INSTALLED"; fi)"
echo "Dreamtonics SDK: $(if [ "$SDK_INSTALLED" = true ]; then echo "INSTALLED"; else echo "NOT INSTALLED"; fi)"
echo "Checkpoint files: $(if [ "$CHECKPOINT_FILES_INSTALLED" = true ]; then echo "INSTALLED"; else echo "NOT INSTALLED"; fi)"
echo "Config files: $(if [ "$CONFIG_FILES_INSTALLED" = true ]; then echo "INSTALLED"; else echo "NOT INSTALLED"; fi)"
echo "============================================"

# Start the application
echo "Starting the application..."
exec python app.py