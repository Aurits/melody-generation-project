# This script contains functions to run commands in Docker containers for melody generation and vocal mixing.
import subprocess
import os
import logging
import time
import json
import pathlib
import importlib.util

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

def generate_melody(input_bgm, checkpoint, gen_seed, output_dir, start_time=0, bpm=0, container_name="melody-generation-set1"):
    """
    Triggers the melody generation model.
    - input_bgm: Path to the original background music file (in the shared volume)
    - checkpoint: Path to the GETMusic checkpoint (inside the melody container)
    - gen_seed: The seed for generation
    - output_dir: The output directory for melody files
    - start_time: Song start time in seconds
    - bpm: Beats per minute
    - container_name: Name of the container to use (default: "melody-generation-set1")
    Returns the path to the generated melody MIDI file.
    """
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

def mix_vocals(original_bgm, melody_file, output_dir, container_name="vocal-mix-set1", sex="female"):
    """
    Triggers the vocal mix model.
    - original_bgm: Path to the original BGM file (in the shared volume)
    - melody_file: Path to the generated melody MIDI file
    - output_dir: The output directory for vocal files
    - container_name: Name of the container to use (default: "vocal-mix-set1")
    - sex: Voice type to use ("female" or "male")
    Returns the path to the final mixed track.
    """
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
        "--sex", sex,
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

def generate_melody_with_package(input_bgm, checkpoint, gen_seed, output_dir, start_time=0, bpm=0):
    """
    Generates melody using the melody_generation Python package (for model set 2).
    
    Args:
        input_bgm: Path to the original background music file
        checkpoint: Path to the checkpoint file
        gen_seed: The seed for generation
        output_dir: The output directory for melody files
        start_time: Song start time in seconds
        bpm: Beats per minute
        
    Returns:
        Path to the generated melody MIDI file
    """
    try:
        # Check if the package is installed
        if importlib.util.find_spec("melody_generation") is None:
            raise ImportError("melody_generation package is not installed")
        
        # Import the required modules
        from melody_generation.infer import create_model
        import melody_generation.beat_estimation.downbeat_estimation as dbe
        
        logger.info(f"Generating melody using Python package for {input_bgm} with seed {gen_seed}")
        logger.info(f"Using start_time={start_time}, bpm={bpm}")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert paths to pathlib.Path objects
        input_bgm_path = pathlib.Path(input_bgm)
        checkpoint_path = pathlib.Path(checkpoint)
        output_dir_path = pathlib.Path(output_dir)
        
        # Create the model
        gen_model = create_model(
            checkpoint_path=checkpoint_path,
            config_path=pathlib.Path("configs/test2300_cqt_realTP_continuous_270000.yaml") 
        )
        
        # Handle beat estimation
        if start_time > 0 or bpm > 0:
            # Manual beat estimation
            dbe_model = dbe.create_model()
            if start_time > 0 and bpm > 0:
                dbe_res = dbe_model.estimate(
                    audio_filepath=input_bgm_path,
                    start_time=start_time,
                    bpm=bpm,
                    auto_estimate=False
                )
            else:
                # Only BPM is specified
                dbe_res = dbe_model.estimate(
                    audio_filepath=input_bgm_path,
                    start_time=0,
                    bpm=bpm,
                    auto_estimate=False
                )
        else:
            # Automatic beat estimation
            dbe_model = dbe.create_model()
            dbe_res = dbe_model.estimate(audio_filepath=input_bgm_path)
        
        # Generate melody
        seeds = [gen_seed] if gen_seed != 0 else None
        paths = gen_model.infer(
            accompaniment_audio_filepath=input_bgm_path,
            beat_times_and_countings_filepath=dbe_res,
            seeds=seeds,
            batch_size=1,
            save_dir=output_dir_path,
            save_synth_demo=True
        )
        
        # The function returns a list of paths, we take the first one
        melody_file = paths[0] if isinstance(paths, list) else paths
        
        logger.info(f"Melody file generated at: {melody_file}")
        
        # Copy the melody file to the expected location if it's not already there
        expected_melody_file = os.path.join(output_dir, "melody.mid")
        if str(melody_file) != expected_melody_file:
            import shutil
            shutil.copy2(melody_file, expected_melody_file)
            logger.info(f"Copied melody file to: {expected_melody_file}")
            melody_file = expected_melody_file
        
        return melody_file
        
    except Exception as e:
        logger.error(f"Error generating melody with package: {str(e)}", exc_info=True)
        raise

def mix_vocals_with_package(original_bgm, melody_file, output_dir, sex="female"):
    """
    Mixes vocals using the vocalmix Python package (for model set 2).
    
    Args:
        original_bgm: Path to the original BGM file
        melody_file: Path to the generated melody MIDI file
        output_dir: The output directory for vocal files
        sex: Voice type to use ("female" or "male")
        
    Returns:
        Path to the final mixed track
    """
    try:
        # Check if the package is installed
        if importlib.util.find_spec("vocalmix") is None:
            raise ImportError("vocalmix package is not installed")
        
        # Import the required modules
        from vocalmix.fuwari.core import get_notes_num, make_all_same_char_fuwarare
        from vocalmix.core import vocalmix
        
        logger.info(f"Mixing vocals using Python package for {original_bgm} with melody {melody_file}")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert paths to pathlib.Path objects
        original_bgm_path = pathlib.Path(original_bgm)
        melody_file_path = pathlib.Path(melody_file)
        output_dir_path = pathlib.Path(output_dir)
        
        # Get the number of notes in the melody
        notes_num = get_notes_num(midi_filepath=melody_file_path)
        
        # Create a fuwarare file with all "ら" characters
        path_to_fuwarare = make_all_same_char_fuwarare(notes_num=notes_num, char="ら")
        
        # Generate the vocal mix
        paths = vocalmix(
            bgm_filepath=original_bgm_path,
            melody_filepath=melody_file_path,
            fuwarare_filepath=path_to_fuwarare,
            dreamtonics_sdk_path=pathlib.Path("/app/dreamtonics_sdk"),  # Assuming SDK is in this location
            sex=sex,
            write_dirpath=output_dir_path
        )
        
        # The function returns a tuple of (vocal_path, mix_path)
        vocal_path, mix_path = paths
        
        logger.info(f"Vocal file generated at: {vocal_path}")
        logger.info(f"Mix file generated at: {mix_path}")
        
        # Copy the mix file to the expected location if it's not already there
        expected_mix_file = os.path.join(output_dir, "mix.wav")
        if str(mix_path) != expected_mix_file:
            import shutil
            shutil.copy2(mix_path, expected_mix_file)
            logger.info(f"Copied mix file to: {expected_mix_file}")
            mix_path = expected_mix_file
        
        # Also copy the vocal file to the expected location
        expected_vocal_file = os.path.join(output_dir, "vocal.wav")
        if str(vocal_path) != expected_vocal_file:
            import shutil
            shutil.copy2(vocal_path, expected_vocal_file)
            logger.info(f"Copied vocal file to: {expected_vocal_file}")
        
        return mix_path
        
    except Exception as e:
        logger.error(f"Error mixing vocals with package: {str(e)}", exc_info=True)
        raise

def process_song(shared_dir, input_bgm, checkpoint, gen_seed, job_id=None, start_time=0, bpm=0, model_set="set1", sex="female"):
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
        model_set: Which model set to use ('set1' or 'set2', defaults to 'set1')
        sex: Voice type to use ("female" or "male")
    """
    try:
        # Create job-specific output directories if job_id is provided
        if job_id:
            melody_output_dir = os.path.join(shared_dir, f"melody_results_{model_set}", f"job_{job_id}")
            vocal_output_dir = os.path.join(shared_dir, f"vocal_results_{model_set}", f"job_{job_id}")
        else:
            melody_output_dir = os.path.join(shared_dir, f"melody_results_{model_set}")
            vocal_output_dir = os.path.join(shared_dir, f"vocal_results_{model_set}")
            
        # Create directories if they don't exist
        os.makedirs(melody_output_dir, exist_ok=True)
        os.makedirs(vocal_output_dir, exist_ok=True)
        
        # Determine which approach to use based on model_set
        if model_set == 'set2':
            # Check if required packages are installed
            melody_gen_installed = importlib.util.find_spec("melody_generation") is not None
            vocalmix_installed = importlib.util.find_spec("vocalmix") is not None
            
            # Check if required files exist
            sdk_exists = os.path.exists("/app/dreamtonics_sdk")
            
            # Get the checkpoint path from environment variable if available
            model_checkpoint_path = os.environ.get("MODEL_CHECKPOINT_PATH", "/app/checkpoints")
            model_config_path = os.environ.get("MODEL_CONFIG_PATH", "/app/configs")
            
            checkpoint_exists = os.path.exists(model_checkpoint_path)
            config_exists = os.path.exists(model_config_path)
            
            # Log the status of all requirements
            logger.info(f"Model set 2 requirements check:")
            logger.info(f"  - melody_generation package: {'installed' if melody_gen_installed else 'NOT INSTALLED'}")
            logger.info(f"  - vocalmix package: {'installed' if vocalmix_installed else 'NOT INSTALLED'}")
            logger.info(f"  - Dreamtonics SDK: {'exists' if sdk_exists else 'NOT FOUND'}")
            logger.info(f"  - Model checkpoint: {'exists' if checkpoint_exists else 'NOT FOUND'} at {model_checkpoint_path}")
            logger.info(f"  - Model config: {'exists' if config_exists else 'NOT FOUND'} at {model_config_path}")
            
            # Check if all requirements are met
            if melody_gen_installed and vocalmix_installed and sdk_exists and checkpoint_exists and config_exists:
                # Use Python packages for model set 2
                logger.info(f"All requirements for model_set='set2' are met. Using Python packages.")
                logger.info(f"Processing song: {input_bgm} for job {job_id} using model set {model_set} (Python packages)")
                logger.info(f"Parameters: start_time={start_time}, bpm={bpm}, seed={gen_seed}, sex={sex}")
                
                # Use the checkpoint path from environment variable
                checkpoint_to_use = model_checkpoint_path
                
                # Generate melody using the Python package
                melody_file = generate_melody_with_package(
                    input_bgm=input_bgm,
                    checkpoint=checkpoint_to_use,
                    gen_seed=gen_seed,
                    output_dir=melody_output_dir,
                    start_time=start_time,
                    bpm=bpm
                )
                logger.info(f"Melody file generated successfully at: {melody_file}")
                
                # Check for beat_mixed_synth_mix.wav file
                beat_mix_file = os.path.join(melody_output_dir, "beat_mixed_synth_mix.wav")
                if os.path.exists(beat_mix_file):
                    logger.info(f"Beat mix file found at: {beat_mix_file}")
                else:
                    logger.warning(f"Beat mix file not found at: {beat_mix_file}")
                    beat_mix_file = None
                
                # Mix vocals using the Python package
                try:
                    final_mix = mix_vocals_with_package(
                        original_bgm=input_bgm,
                        melody_file=melody_file,
                        output_dir=vocal_output_dir,
                        sex=sex
                    )
                    logger.info(f"Final mix generated successfully at: {final_mix}")
                except Exception as e:
                    logger.error(f"Error in vocal mixing: {str(e)}")
                    logger.info("Falling back to model set 1 for vocal mixing")
                    
                    # Fall back to model set 1 for vocal mixing only
                    vocal_container = "vocal-mix-set1"
                    final_mix = mix_vocals(
                        original_bgm=input_bgm,
                        melody_file=melody_file,
                        output_dir=vocal_output_dir,
                        container_name=vocal_container,
                        sex=sex
                    )
                    logger.info(f"Final mix generated successfully using fallback method at: {final_mix}")
                
                return final_mix, beat_mix_file
            else:
                # Some requirements are not met, fall back to model set 1
                missing_requirements = []
                if not melody_gen_installed:
                    missing_requirements.append("melody_generation package")
                if not vocalmix_installed:
                    missing_requirements.append("vocalmix package")
                if not sdk_exists:
                    missing_requirements.append("Dreamtonics SDK")
                if not checkpoint_exists:
                    missing_requirements.append("model checkpoint")
                if not config_exists:
                    missing_requirements.append("model config")
                
                logger.warning(f"Some requirements for model_set='set2' are not met: {', '.join(missing_requirements)}. "
                              f"Falling back to model_set='set1'.")
                model_set = 'set1'
                
                # Update output directories to use set1
                if job_id:
                    melody_output_dir = os.path.join(shared_dir, "melody_results_set1", f"job_{job_id}")
                    vocal_output_dir = os.path.join(shared_dir, "vocal_results_set1", f"job_{job_id}")
                else:
                    melody_output_dir = os.path.join(shared_dir, "melody_results_set1")
                    vocal_output_dir = os.path.join(shared_dir, "vocal_results_set1")
                
                # Create directories if they don't exist after changing model_set
                os.makedirs(melody_output_dir, exist_ok=True)
                os.makedirs(vocal_output_dir, exist_ok=True)
        
        # If model_set is 'set1' or we've fallen back to it
        melody_container = "melody-generation-set1"
        vocal_container = "vocal-mix-set1"
        
        logger.info(f"Processing song: {input_bgm} for job {job_id} using model set {model_set} (Docker containers)")
        logger.info(f"Parameters: start_time={start_time}, bpm={bpm}, seed={gen_seed}, sex={sex}")
        logger.info(f"Using containers: {melody_container} and {vocal_container}")
        
        # Generate melody using the selected container
        melody_file = generate_melody(
            input_bgm=input_bgm,
            checkpoint=checkpoint,
            gen_seed=gen_seed,
            output_dir=melody_output_dir,
            start_time=start_time,
            bpm=bpm,
            container_name=melody_container
        )
        logger.info(f"Melody file generated successfully at: {melody_file}")
        
        # Check for beat_mixed_synth_mix.wav file
        beat_mix_file = os.path.join(melody_output_dir, "beat_mixed_synth_mix.wav")
        if os.path.exists(beat_mix_file):
            logger.info(f"Beat mix file found at: {beat_mix_file}")
        else:
            logger.warning(f"Beat mix file not found at: {beat_mix_file}")
            beat_mix_file = None
        
        # Mix vocals using the selected container
        final_mix = mix_vocals(
            original_bgm=input_bgm,
            melody_file=melody_file,
            output_dir=vocal_output_dir,
            container_name=vocal_container,
            sex=sex
        )
        logger.info(f"Final mix generated successfully at: {final_mix}")
        
        # Return both the final mix and beat mix file paths
        return final_mix, beat_mix_file
        
    except Exception as e:
        logger.error(f"Error in process_song: {str(e)}", exc_info=True)
        # Return default values for Gradio interface to avoid the "not enough output values" error
        return None, None