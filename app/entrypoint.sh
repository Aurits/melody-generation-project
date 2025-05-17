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
        
        # Check if gcc is installed, if not try to install it
        if ! command -v gcc &> /dev/null; then
            echo "gcc not found, attempting to install build tools..."
            apt-get update && apt-get install -y build-essential
            if [ $? -eq 0 ]; then
                echo "Successfully installed build tools"
            else
                echo "Failed to install build tools, melody_generation package may not install correctly"
            fi
        else
            echo "gcc is already installed"
        fi
        
        # Install melody_generation package with detailed error handling
        echo "Installing melody_generation package..."
        pip install --extra-index-url https://download.pytorch.org/whl/cu124 git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git@prod
        if [ $? -eq 0 ]; then
            echo "Successfully installed melody_generation package"
            MELODY_GEN_INSTALLED=true
        else
            echo "Failed to install melody_generation package with the first method, trying alternative method..."
            # Try alternative installation method - install madmom separately first
            echo "Attempting to install madmom dependency separately..."
            pip install git+https://github.com/CPJKU/madmom.git
            
            # Now try installing melody_generation again
            pip install --extra-index-url https://download.pytorch.org/whl/cu124 git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git@prod
            if [ $? -eq 0 ]; then
                echo "Successfully installed melody_generation package with alternative method"
                MELODY_GEN_INSTALLED=true
            else
                echo "Failed to install melody_generation package with alternative method"
            fi
        fi
        
        # Install vocalmix package with detailed error handling
        echo "Installing vocalmix package..."
        pip install git+https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_vocalmix.git@prod
        if [ $? -eq 0 ]; then
            echo "Successfully installed vocalmix package"
            VOCALMIX_INSTALLED=true
        else
            echo "Failed to install vocalmix package with the first method, trying alternative method..."
            # Try alternative installation method
            pip install git+https://${GITHUB_PAT}:${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_vocalmix.git@prod
            if [ $? -eq 0 ]; then
                echo "Successfully installed vocalmix package with alternative method"
                VOCALMIX_INSTALLED=true
            else
                echo "Failed to install vocalmix package with alternative method"
            fi
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
        
        # Diagnostic information for melody_generation package if it failed
        if [ "$MELODY_GEN_INSTALLED" = false ]; then
            echo "Checking for potential issues with melody_generation package..."
            # Check if the repository exists and is accessible
            echo "Checking repository access..."
            git ls-remote https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git prod > /dev/null
            if [ $? -eq 0 ]; then
                echo "Repository is accessible with the provided PAT"
            else
                echo "Cannot access repository. Check if the PAT has access to this repository."
            fi
            
            # Check Python and pip versions
            echo "Python version:"
            python --version
            echo "Pip version:"
            pip --version
            
            # List installed packages that might conflict
            echo "Checking for potential conflicting packages:"
            pip list | grep -E "torch|numpy|scipy|librosa"
            
            # Try cloning the repository directly to see if that works
            echo "Attempting to clone repository directly..."
            mkdir -p /tmp/melody_gen_test
            git clone -b prod https://${GITHUB_PAT}@github.com/satoshi-suehiro/tmik_melody_generation.git /tmp/melody_gen_test
            if [ $? -eq 0 ]; then
                echo "Repository cloned successfully. Issue might be with pip installation."
                # Try installing from the cloned repository
                echo "Attempting to install from cloned repository..."
                pip install -e /tmp/melody_gen_test
                if [ $? -eq 0 ]; then
                    echo "Successfully installed melody_generation from cloned repository"
                    MELODY_GEN_INSTALLED=true
                else
                    echo "Failed to install from cloned repository"
                fi
            else
                echo "Failed to clone repository. Issue might be with repository access."
            fi
            rm -rf /tmp/melody_gen_test
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
pip install gdown

# Try to download and set up the Dreamtonics SDK
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
    
    # Also set permissions for any build directories that might be created by vocalmix
    mkdir -p /app/build
    chmod -R 755 /app/build
fi

# Create directories for checkpoints and configs
mkdir -p /app/checkpoints
mkdir -p /app/configs

# Define GitHub URL for the specific checkpoint
GITHUB_CHECKPOINT_URL="https://github.com/satoshi-suehiro/tmik_melody_generation/releases/download/v0.1.0/20250507_test2300_270000.zip"
GITHUB_CHECKPOINT_FILE="/tmp/github_checkpoint.zip"

# First, try to download the specific checkpoint from GitHub
echo "Attempting to download checkpoint from GitHub release..."
# Install curl if needed
if ! command -v curl &> /dev/null; then
    echo "curl not found, installing..."
    apt-get update && apt-get install -y curl
fi

curl -L -o "$GITHUB_CHECKPOINT_FILE" "$GITHUB_CHECKPOINT_URL"
if [ $? -eq 0 ] && [ -f "$GITHUB_CHECKPOINT_FILE" ]; then
    echo "Successfully downloaded checkpoint from GitHub release"
    
    # Extract the files
    echo "Extracting checkpoint files from GitHub release..."
    mkdir -p /tmp/github_checkpoint
    unzip -q "$GITHUB_CHECKPOINT_FILE" -d /tmp/github_checkpoint
    
    # List the contents to debug
    echo "Contents of extracted GitHub archive:"
    find /tmp/github_checkpoint -type f | sort
    
    # Based on the file structure from the images:
    # 1. The YAML config file is at the top level
    # 2. The model files are in a subdirectory with the same name as the zip
    
    # Copy the YAML file to configs directory
    YAML_FILES=$(find /tmp/github_checkpoint -maxdepth 1 -name "*.yaml" -o -name "*.yml")
    if [ -n "$YAML_FILES" ]; then
        echo "Found YAML file at top level of archive"
        cp $YAML_FILES /app/configs/
        # Rename to default.yaml if needed
        for file in $YAML_FILES; do
            basename=$(basename "$file")
            cp "$file" "/app/configs/default.yaml"
            echo "Copied $basename to /app/configs/default.yaml"
        done
        CONFIG_FILES_INSTALLED=true
    fi
    
    # Look for the model files directory
    MODEL_DIR=$(find /tmp/github_checkpoint -type d -name "20250507_test2300_270000")
    if [ -n "$MODEL_DIR" ]; then
        echo "Found model directory: $MODEL_DIR"
        # Create the target directory
        mkdir -p /app/checkpoints/test2300_cqt_realTP_continuous_270000
        
        # Copy all model files (.pt, .pth, .json, etc.)
        find "$MODEL_DIR" -type f \( -name "*.pt" -o -name "*.pth" -o -name "*.json" -o -name "*.bin" -o -name "*.safetensors" \) | while read file; do
            echo "Copying model file: $(basename "$file")"
            cp "$file" /app/checkpoints/test2300_cqt_realTP_continuous_270000/
        done
        CHECKPOINT_FILES_INSTALLED=true
    else
        echo "Model directory not found, looking for model files directly"
        # Look for model files directly
        MODEL_FILES=$(find /tmp/github_checkpoint -type f \( -name "*.pt" -o -name "*.pth" -o -name "*.json" -o -name "*.bin" -o -name "*.safetensors" \))
        if [ -n "$MODEL_FILES" ]; then
            mkdir -p /app/checkpoints/test2300_cqt_realTP_continuous_270000
            for file in $MODEL_FILES; do
                echo "Copying model file: $(basename "$file")"
                cp "$file" /app/checkpoints/test2300_cqt_realTP_continuous_270000/
            done
            CHECKPOINT_FILES_INSTALLED=true
        fi
    fi
    
    # Clean up
    rm -rf /tmp/github_checkpoint
    rm "$GITHUB_CHECKPOINT_FILE"
else
    echo "Failed to download checkpoint from GitHub release, trying alternative methods..."
fi

# Try the local directory if GitHub download failed and files aren't installed yet
if [ "$CHECKPOINT_FILES_INSTALLED" = false ] || [ "$CONFIG_FILES_INSTALLED" = false ]; then
    # Copy the checkpoint files from the local directory if they exist
    echo "Trying to set up checkpoint and configuration files from local directory..."
    if [ -d "/app/model_files/checkpoints" ]; then
        echo "Copying checkpoint files from local directory..."
        cp -r /app/model_files/checkpoints/* /app/checkpoints/
        if [ $? -eq 0 ]; then
            echo "Successfully copied checkpoint files from local directory"
            CHECKPOINT_FILES_INSTALLED=true
        else
            echo "Failed to copy checkpoint files from local directory"
        fi
        
        # Copy config files if they exist
        if [ -d "/app/model_files/configs" ]; then
            cp -r /app/model_files/configs/* /app/configs/
            if [ $? -eq 0 ]; then
                echo "Successfully copied config files from local directory"
                CONFIG_FILES_INSTALLED=true
            else
                echo "Failed to copy config files from local directory"
            fi
        fi
    else
        echo "Local checkpoint files not found, attempting to download from Google Drive..."
        # Try to download and set up configuration and checkpoint files from Google Drive
        gdown --id 1CkBxeUm08jISvC0H3vdZkBLHhEBmop71 -O /tmp/config_checkpoint.zip
        if [ $? -eq 0 ]; then
            echo "Successfully downloaded configuration and checkpoint files from Google Drive"
            
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
                    CHECKPOINT_FILES_INSTALLED=true
                elif [ -d "/tmp/config_checkpoint/checkpoint" ]; then
                    echo "Found /tmp/config_checkpoint/checkpoint directory"
                    cp -r /tmp/config_checkpoint/checkpoint/* /app/checkpoints/
                    CHECKPOINT_FILES_INSTALLED=true
                else
                    # Try to find directories that might contain checkpoint files
                    echo "Searching for checkpoint directories..."
                    find /tmp/config_checkpoint -name "*.pth" -o -name "*.pt" -o -name "*.json" -o -name "*.yaml" | while read file; do
                        dir=$(dirname "$file")
                        if [ -d "$dir" ] && [[ "$dir" == *"checkpoint"* || "$dir" == *"model"* ]]; then
                            echo "Found potential checkpoint directory: $dir"
                            cp -r "$dir"/* /app/checkpoints/
                            CHECKPOINT_FILES_INSTALLED=true
                        fi
                    done
                fi
                
                if [ -d "/tmp/config_checkpoint/configs" ]; then
                    echo "Found /tmp/config_checkpoint/configs directory"
                    cp -r /tmp/config_checkpoint/configs/* /app/configs/
                    CONFIG_FILES_INSTALLED=true
                elif [ -d "/tmp/config_checkpoint/config" ]; then
                    echo "Found /tmp/config_checkpoint/config directory"
                    cp -r /tmp/config_checkpoint/config/* /app/configs/
                    CONFIG_FILES_INSTALLED=true
                else
                    # Try to find YAML files that might be config files
                    echo "Searching for config files..."
                    find /tmp/config_checkpoint -name "*.yaml" | while read file; do
                        echo "Found potential config file: $file"
                        cp "$file" /app/configs/
                        CONFIG_FILES_INSTALLED=true
                    done
                fi
                
                # Clean up
                rm -rf /tmp/config_checkpoint
                rm /tmp/config_checkpoint.zip
            fi
        else
            echo "Failed to download configuration and checkpoint files from Google Drive"
        fi
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
        CHECKPOINT_FILES_INSTALLED=true
    fi
else
    CHECKPOINT_FILES_INSTALLED=true
fi

# If the specific config file doesn't exist, try to find any YAML file
if [ ! -f "$CONFIG_PATH" ]; then
    echo "Specific config file not found, searching for alternatives..."
    # Find the first YAML file in /app/configs
    FIRST_CONFIG_FILE=$(find /app/configs -name "*.yaml" | head -n 1)
    if [ -n "$FIRST_CONFIG_FILE" ]; then
        echo "Found alternative config file: $FIRST_CONFIG_FILE"
        CONFIG_PATH="$FIRST_CONFIG_FILE"
        CONFIG_FILES_INSTALLED=true
    fi
else
    CONFIG_FILES_INSTALLED=true
fi

# Verify the installation
echo "Checking installation..."
if [ -d "/app/dreamtonics_sdk" ]; then
    echo "Dreamtonics SDK is installed"
    SDK_INSTALLED=true
else
    echo "Dreamtonics SDK is not installed, will use Docker containers instead"
    SDK_INSTALLED=false
fi

if [ -d "$CHECKPOINT_PATH" ] && [ -f "$CONFIG_PATH" ]; then
    echo "Configuration and checkpoint files are installed"
    echo "Checkpoint path: $CHECKPOINT_PATH"
    echo "Config path: $CONFIG_PATH"
    
    # Export environment variables for use in the application
    export MODEL_CHECKPOINT_PATH="$CHECKPOINT_PATH"
    export MODEL_CONFIG_PATH="$CONFIG_PATH"
    
    # Create a .env.runtime file that will be sourced by the application
    echo "MODEL_CHECKPOINT_PATH=$CHECKPOINT_PATH" > /app/.env.runtime
    echo "MODEL_CONFIG_PATH=$CONFIG_PATH" >> /app/.env.runtime
    
    # Add package installation status to the runtime environment
    echo "MELODY_GEN_INSTALLED=$MELODY_GEN_INSTALLED" >> /app/.env.runtime
    echo "VOCALMIX_INSTALLED=$VOCALMIX_INSTALLED" >> /app/.env.runtime
    echo "SDK_INSTALLED=$SDK_INSTALLED" >> /app/.env.runtime
    
    # Make sure the file is readable
    chmod 644 /app/.env.runtime
else
    echo "Configuration and checkpoint files are not installed or incomplete, will use Docker containers instead"
    # List what we have to debug
    echo "Available checkpoint directories:"
    find /app/checkpoints -type d | sort
    echo "Available config files:"
    find /app/configs -type f | sort
fi

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

# Export variables for the application to use
export MELODY_GEN_INSTALLED
export VOCALMIX_INSTALLED
export SDK_INSTALLED
export CHECKPOINT_FILES_INSTALLED
export CONFIG_FILES_INSTALLED

echo "Starting the application..."
exec python app.py