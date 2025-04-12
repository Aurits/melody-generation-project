# service.py
# This script contains functions to run commands in Docker containers for melody generation and vocal mixing.
import subprocess
import os
import logging
import time

# Set up logging
logger = logging.getLogger(__name__)

def check_container_running(container_name):
    """
    Checks if a container is running.
    Returns True if running, False otherwise.
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Container {container_name} does not exist or cannot be inspected")
            if result.stderr:
                logger.error(f"Inspect error: {result.stderr}")
            return False
            
        is_running = result.stdout.strip().lower() == "true"
        if not is_running:
            logger.error(f"Container {container_name} exists but is not running")
        else:
            logger.info(f"Container {container_name} is running")
        
        return is_running
        
    except Exception as e:
        logger.error(f"Error checking container status: {str(e)}", exc_info=True)
        return False

def run_command_in_container(container_name, command_list):
    """
    Runs a command inside a specified container using `docker exec`
    and returns the command's stdout.
    """
    full_command = ["docker", "exec", container_name] + command_list
    logger.info(f"Running command: {' '.join(full_command)}")
    
    try:
        result = subprocess.run(
            full_command, 
            capture_output=True, 
            text=True, 
            check=False  # Don't raise an exception on non-zero exit
        )
        
        # Log the output regardless of success or failure
        if result.stdout:
            logger.info(f"Command stdout: {result.stdout}")
        
        # Check if the command failed
        if result.returncode != 0:
            logger.error(f"Command failed with exit code {result.returncode}")
            if result.stderr:
                logger.error(f"Command stderr: {result.stderr}")
            
            # Now raise the exception
            result.check_returncode()  # This will raise CalledProcessError
            
        return result.stdout
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Command execution failed: {str(e)}")
        if e.stdout:
            logger.info(f"Command stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Command stderr: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error running command: {str(e)}", exc_info=True)
        raise

def generate_melody(input_bgm, checkpoint, gen_seed, output_dir, start_time=0, bpm=0):
    """
    Triggers the melody generation model.
    - input_bgm: Path to the original background music file (in the shared volume)
    - checkpoint: Path to the GETMusic checkpoint (inside the melody container)
    - gen_seed: The seed for generation
    - output_dir: The output directory for melody files
    - start_time: Song start time in seconds
    - bpm: Beats per minute
    Returns the path to the generated melody MIDI file.
    """
    container_name = "melody-generation"
    
    # Check if container is running
    if not check_container_running(container_name):
        raise RuntimeError(f"Required container '{container_name}' is not running")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if input file exists
    if not os.path.exists(input_bgm):
        raise FileNotFoundError(f"Input file {input_bgm} does not exist")
    
    logger.info(f"Generating melody for {input_bgm} with seed {gen_seed} to {output_dir}")
    logger.info(f"Using start_time={start_time}, bpm={bpm}")
    
    # Build the command
    command = [
        "uv", "run", "melody_generation.py",
        "--load_path", checkpoint,
        "--bgm_filepath", input_bgm,
        "--gen_seed", str(gen_seed),
        "--output_dir", output_dir,
        "--one_shot_generation",
        "--output_beat_estimation_mix",  # Add flag for beat estimation mix
        "--output_synth_demo"            # Add flag for synth demo
    ]
    
    # Only add start_time and bpm if at least one is non-zero
    if start_time > 0 or bpm > 0:
        # According to the README, if start_time is specified, bpm must also be specified
        if start_time > 0:
            command.extend(["--start_time", str(start_time)])
            command.extend(["--bpm", str(bpm)])
        elif bpm > 0:
            # If only BPM is specified (start_time=0), still pass both parameters
            command.extend(["--start_time", "0"])
            command.extend(["--bpm", str(bpm)])
    
    run_command_in_container(container_name, command)
    
    # Check if melody file was created
    melody_file = os.path.join(output_dir, "melody.mid")
    wait_attempts = 10
    for attempt in range(wait_attempts):
        if os.path.exists(melody_file):
            logger.info(f"Melody file generated at: {melody_file}")
            return melody_file
        
        logger.warning(f"Melody file not found yet, waiting... (attempt {attempt+1}/{wait_attempts})")
        time.sleep(3)
    
    raise FileNotFoundError(f"Melody file {melody_file} was not created after waiting")

def mix_vocals(original_bgm, melody_file, output_dir):
    """
    Triggers the vocal mix model.
    - original_bgm: Path to the original BGM file (in the shared volume)
    - melody_file: Path to the generated melody MIDI file
    - output_dir: The output directory for vocal files
    Returns the path to the final mixed track.
    """
    container_name = "vocal-mix"
    
    # Check if container is running
    if not check_container_running(container_name):
        raise RuntimeError(f"Required container '{container_name}' is not running")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if input files exist
    if not os.path.exists(original_bgm):
        raise FileNotFoundError(f"Original BGM file {original_bgm} does not exist")
    
    if not os.path.exists(melody_file):
        raise FileNotFoundError(f"Melody file {melody_file} does not exist")
    
    logger.info(f"Mixing vocals for {original_bgm} with melody {melody_file} to {output_dir}")
    
    command = [
        "uv", "run", "make_vocalmix.py",
        "--bgm_filepath", original_bgm,
        "--melody_filepath", melody_file,
        "--all_la",
        "--sex", "female",
        "--write_dirpath", output_dir
    ]
    
    run_command_in_container(container_name, command)
    
    # Check if mix file was created
    mix_file = os.path.join(output_dir, "mix.wav")
    wait_attempts = 10
    for attempt in range(wait_attempts):
        if os.path.exists(mix_file):
            logger.info(f"Mix file generated at: {mix_file}")
            return mix_file
        
        logger.warning(f"Mix file not found yet, waiting... (attempt {attempt+1}/{wait_attempts})")
        time.sleep(3)
    
    raise FileNotFoundError(f"Mix file {mix_file} was not created after waiting")
   
def process_song(shared_dir, input_bgm, checkpoint, gen_seed, job_id=None, start_time=0, bpm=0):
    """
    Orchestrates the complete workflow:
      1. Runs melody generation.
      2. Runs vocal mixing.
      3. Returns the final mix path and beat mix path.
      
    Args:
        shared_dir: Base shared directory
        input_bgm: Path to input audio file
        checkpoint: Path to model checkpoint
        gen_seed: Generation seed
        job_id: Optional job ID for organizing outputs
        start_time: Song start time in seconds
        bpm: Beats per minute
    """
    try:
        logger.info(f"Processing song: {input_bgm} for job {job_id}")
        logger.info(f"Parameters: start_time={start_time}, bpm={bpm}, seed={gen_seed}")
        
        # Create job-specific output directories if job_id is provided
        if job_id:
            melody_output_dir = os.path.join(shared_dir, "melody_results", f"job_{job_id}")
            vocal_output_dir = os.path.join(shared_dir, "vocal_results", f"job_{job_id}")
        else:
            melody_output_dir = os.path.join(shared_dir, "melody_results")
            vocal_output_dir = os.path.join(shared_dir, "vocal_results")
            
        # Create directories if they don't exist
        os.makedirs(melody_output_dir, exist_ok=True)
        os.makedirs(vocal_output_dir, exist_ok=True)
        
        # Generate melody
        melody_file = generate_melody(input_bgm, checkpoint, gen_seed, melody_output_dir, start_time, bpm)
        logger.info(f"Melody file generated successfully at: {melody_file}")
        
        # Check for beat_mixed_synth_mix.wav file
        beat_mix_file = os.path.join(melody_output_dir, "beat_mixed_synth_mix.wav")
        if os.path.exists(beat_mix_file):
            logger.info(f"Beat mix file found at: {beat_mix_file}")
        else:
            logger.warning(f"Beat mix file not found at: {beat_mix_file}")
            beat_mix_file = None
        
        # Mix vocals
        final_mix = mix_vocals(input_bgm, melody_file, vocal_output_dir)
        logger.info(f"Final mix generated successfully at: {final_mix}")
        
        # Return both the final mix and beat mix file paths
        return final_mix, beat_mix_file
        
    except Exception as e:
        logger.error(f"Error in process_song: {str(e)}", exc_info=True)
        raise