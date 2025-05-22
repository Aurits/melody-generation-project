# services.py
import subprocess
import os
import logging
import time
import json
import pathlib
import importlib.util
import shutil
import sys


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

def generate_melody_with_package(input_bgm, checkpoint, gen_seed, output_dir, start_time=0, bpm=0, batch_size=1):
    """
    Generates melody using the melody_generation Python package (for model set 2).
    
    Args:
        input_bgm: Path to the original background music file
        checkpoint: Path to the checkpoint file
        gen_seed: The seed for generation (used only when batch_size=1)
        output_dir: The output directory for melody files
        start_time: Song start time in seconds
        bpm: Beats per minute
        batch_size: Number of melodies to generate in parallel (default: 1)
        
    Returns:
        List of paths to the generated melody MIDI files
    """
    try:
        # Check if the package is installed
        if importlib.util.find_spec("melody_generation") is None:
            raise ImportError("melody_generation package is not installed")
        
        # Import the required modules
        from melody_generation.infer import create_model
        import melody_generation.beat_estimation.downbeat_estimation as dbe
        import random
        
        logger.info(f"Generating {batch_size} melodies using Python package for {input_bgm}")
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
            config_path=pathlib.Path("configs/20250507_test2300_270000.yaml") 
        )
        
        # Handle beat estimation
        dbe_model = dbe.create_model()
        if start_time > 0 or bpm > 0:
            # Manual beat estimation
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
            dbe_res = dbe_model.estimate(audio_filepath=input_bgm_path)
            
        # Generate beat mix for visualization
        beat_mix_path = os.path.join(output_dir, "beat_mixed_synth_mix.wav")
        try:
            dbe.make_clicked_audio_by_beat_times_and_countings(
                audio_filepath=input_bgm_path,
                beat_times_and_countings=dbe_res,
                save_path=pathlib.Path(beat_mix_path)
            )
            logger.info(f"Created beat mix visualization at: {beat_mix_path}")
        except Exception as e:
            logger.warning(f"Failed to create beat mix visualization: {str(e)}")
        
        # Generate seeds if batch_size > 1
        if batch_size > 1:
            seeds = [random.randint(1, 10000) for _ in range(batch_size)]
            logger.info(f"Generated random seeds for batch processing: {seeds}")
            save_synth_demo = False  # Disable synth demo for batch processing
        else:
            seeds = [gen_seed] if gen_seed != 0 else None
            save_synth_demo = True
        
        # Generate melody using the API as documented
        paths = gen_model.infer(
            accompaniment_audio_filepath=input_bgm_path,
            beat_times_and_countings_filepath=dbe_res,
            seeds=seeds,
            batch_size=batch_size,
            save_dir=output_dir_path,
            save_synth_demo=save_synth_demo
        )
        
        logger.info(f"Generated {len(paths) if isinstance(paths, list) else 1} melody files")
        
        # Handle the return value - could be a list or single path
        melody_files = paths if isinstance(paths, list) else [paths]
        
        # For each melody file, create a uniquely named copy
        named_melody_files = []
        for i, melody_file in enumerate(melody_files):
            seed_val = seeds[i] if seeds and i < len(seeds) else "random"
            new_filename = f"melody_variant_{i+1}_seed_{seed_val}.mid"
            new_path = os.path.join(output_dir, new_filename)
            shutil.copy2(melody_file, new_path)
            named_melody_files.append(new_path)
            logger.info(f"Created uniquely named melody file: {new_path}")
        
        return named_melody_files
        
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

def process_song(shared_dir, input_bgm, checkpoint, gen_seed, job_id=None, start_time=0, bpm=0, model_set="set1", sex="female", batch_size=1):
    """
    Orchestrates the complete workflow:
      1. Runs melody generation.
      2. Runs vocal mixing.
      3. Returns the final mix paths and beat mix path.
      
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
        batch_size: Number of melodies to generate in parallel (default: 1)
        
    Returns:
        If batch_size=1: (final_mix_path, beat_mix_file_path)
        If batch_size>1: (list_of_final_mix_paths, beat_mix_file_path)
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
            # Check requirements - same as before
            melody_gen_installed = importlib.util.find_spec("melody_generation") is not None
            vocalmix_installed = importlib.util.find_spec("vocalmix") is not None
            sdk_exists = os.path.exists("/app/dreamtonics_sdk")
            model_checkpoint_path = os.environ.get("MODEL_CHECKPOINT_PATH", "/app/checkpoints")
            model_config_path = os.environ.get("MODEL_CONFIG_PATH", "/app/configs")
            checkpoint_exists = os.path.exists(model_checkpoint_path)
            config_exists = os.path.exists(model_config_path)
            
            # Log requirements status
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
                logger.info(f"Parameters: start_time={start_time}, bpm={bpm}, seed={gen_seed}, sex={sex}, batch_size={batch_size}")
                
                # Use the checkpoint path from environment variable
                checkpoint_to_use = model_checkpoint_path
                
                # Generate melody (or melodies) using the Python package
                try:
                    melody_files = generate_melody_with_package(
                        input_bgm=input_bgm,
                        checkpoint=checkpoint_to_use,
                        gen_seed=gen_seed,
                        output_dir=melody_output_dir,
                        start_time=start_time,
                        bpm=bpm,
                        batch_size=batch_size
                    )
                except Exception as e:
                    logger.error(f"Failed to generate melodies with package: {str(e)}")
                    raise
                
                # Ensure melody_files is a list even if only one file is returned
                if not isinstance(melody_files, list):
                    melody_files = [melody_files]
                
                logger.info(f"Generated {len(melody_files)} melody files successfully")
                
                # Check for beat_mixed_synth_mix.wav file
                beat_mix_file = os.path.join(melody_output_dir, "beat_mixed_synth_mix.wav")
                if os.path.exists(beat_mix_file):
                    logger.info(f"Found beat mix file at: {beat_mix_file}")
                else:
                    logger.warning(f"Beat mix file not found at: {beat_mix_file}")
                    beat_mix_file = None
                
                # Process each melody file separately
                final_mixes = []
                
                for i, melody_file in enumerate(melody_files):
                    # Create a variant-specific output directory for each melody
                    variant_dir = os.path.join(vocal_output_dir, f"variant_{i+1}")
                    os.makedirs(variant_dir, exist_ok=True)
                    logger.info(f"Processing melody variant {i+1}: {melody_file}")
                    
                    try:
                        # Generate "la" syllables for vocals according to the documentation
                        from vocalmix.fuwari.core import get_notes_num, make_all_same_char_fuwarare
                        
                        # Get the number of notes in the melody
                        notes_num = get_notes_num(midi_filepath=pathlib.Path(melody_file))
                        
                        # Create a fuwarare file with all "ら" characters
                        path_to_fuwarare = make_all_same_char_fuwarare(notes_num=notes_num, char="ら")
                        
                        # Generate vocals using vocalmix
                        from vocalmix.core import vocalmix
                        
                        paths = vocalmix(
                            bgm_filepath=pathlib.Path(input_bgm),
                            melody_filepath=pathlib.Path(melody_file),
                            fuwarare_filepath=path_to_fuwarare,
                            dreamtonics_sdk_path=pathlib.Path("/app/dreamtonics_sdk"),
                            sex=sex,
                            write_dirpath=pathlib.Path(variant_dir)
                        )
                        
                        # Paths should be a tuple of (vocal_path, mix_path)
                        vocal_path, mix_path = paths
                        
                        logger.info(f"Variant {i+1} mix generated successfully at: {mix_path}")
                        final_mixes.append(str(mix_path))
                    except Exception as e:
                        logger.error(f"Error in vocal mixing for variant {i+1}: {str(e)}")
                        try:
                            # Fall back to model set 1 for this variant
                            logger.info(f"Falling back to model set 1 for vocal mixing variant {i+1}")
                            vocal_container = "vocal-mix-set1"
                            final_mix = mix_vocals(
                                original_bgm=input_bgm,
                                melody_file=melody_file,
                                output_dir=variant_dir,
                                container_name=vocal_container,
                                sex=sex
                            )
                            logger.info(f"Variant {i+1} mix generated successfully using fallback method at: {final_mix}")
                            final_mixes.append(final_mix)
                        except Exception as nested_e:
                            logger.error(f"Fallback also failed for variant {i+1}: {str(nested_e)}")
                            final_mixes.append(None)  # Add None to maintain ordering
                
                # If batch_size is 1, return the single result as before
                if batch_size == 1 and len(final_mixes) > 0:
                    return final_mixes[0], beat_mix_file
                else:
                    # Otherwise return the list of all final mixes
                    return final_mixes, beat_mix_file
                    
            else:
                # Some requirements are not met, fall back to model set 1
                # (Fallback code same as before)
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
        # This code doesn't support batch processing, so batch_size is ignored
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
        
        # For compatibility with batch mode, wrap the single result in a list if batch_size > 1
        if batch_size > 1:
            return [final_mix], beat_mix_file
        else:
            return final_mix, beat_mix_file
        
    except Exception as e:
        logger.error(f"Error in process_song: {str(e)}", exc_info=True)
        # Return default values for Gradio interface to avoid the "not enough output values" error
        if batch_size > 1:
            return [], None
        else:
            return None, None