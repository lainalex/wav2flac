#!/usr/bin/env python3
"""
OPTIMIZED WAV to FLAC Converter with Direct FFmpeg and Smart Threading
Leverages FFmpeg's native multithreading for maximum performance
Recursively converts all WAV files in a directory and subdirectories to FLAC format
Maintains the original folder structure in the output directory
Supports optional local caching for network locations and slow drives for improved performance
"""

import os
import sys
import logging
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
from typing import List, Tuple, Optional

# Configuration constants
FFMPEG_TIMEOUT_SECONDS = 300  # 5 minutes per file
PREREQUISITE_CHECK_TIMEOUT = 10  # 10 seconds for FFmpeg version checks
CACHE_COPY_THREADS = 8  # Maximum threads for I/O-bound cache copying
PROGRESS_REPORT_INTERVAL = 10  # Report progress every N cached files
PROGRESS_REPORT_INTERVAL_SMALL = 5  # Report progress every N converted files for small batches
CONVERSION_PROGRESS_THRESHOLD = 20  # Show all progress for batches <= this size
DISK_SPACE_SAFETY_MARGIN = 1.2  # 20% extra space required for caching
DEFAULT_COMPRESSION_LEVEL = 12  # FLAC compression (0=fast, 12=best)

def check_prerequisites() -> List[str]:
    """Check if all required software is installed"""
    print("Checking prerequisites...")
    issues: List[str] = []
    
    # Check Python version
    if sys.version_info < (3, 6):
        issues.append("Python 3.6 or higher is required")
    else:
        print("✓ Python version: OK")
    
    # Check FFmpeg with detailed capability testing
    try:
        result = subprocess.run(['ffmpeg', '-version'],
                              capture_output=True,
                              text=True,
                              timeout=PREREQUISITE_CHECK_TIMEOUT)
        if result.returncode == 0:
            # Extract FFmpeg version from output
            version_line = result.stdout.split('\n')[0]
            print(f"✓ FFmpeg: OK ({version_line.split()[2]})")
            
            # Test FLAC encoding capability
            flac_test = subprocess.run(['ffmpeg', '-encoders'],
                                     capture_output=True,
                                     text=True,
                                     timeout=PREREQUISITE_CHECK_TIMEOUT)
            if 'flac' in flac_test.stdout.lower():
                print("✓ FFmpeg FLAC encoder: OK")
            else:
                issues.append("FFmpeg doesn't support FLAC encoding")
                print("✗ FFmpeg FLAC encoder: NOT AVAILABLE")
        else:
            issues.append("FFmpeg is installed but not responding correctly")
            print("✗ FFmpeg: ERROR")
    except subprocess.TimeoutExpired:
        issues.append("FFmpeg check timed out")
        print("✗ FFmpeg: TIMEOUT")
    except FileNotFoundError:
        issues.append("FFmpeg is not installed or not in PATH")
        print("✗ FFmpeg: NOT FOUND")
    except Exception as e:
        issues.append(f"FFmpeg check failed: {str(e)}")
        print(f"✗ FFmpeg: ERROR - {str(e)}")
    
    return issues

def convert_wav_to_flac_ffmpeg(
    wav_path: Path,
    input_dir: Path,
    output_dir: Path,
    ffmpeg_threads: int,
    compression_level: int,
    logger: logging.Logger,
    original_input_dir: Optional[Path] = None
) -> Tuple[bool, str, str, int, int, float]:
    """
    Convert a single WAV file to FLAC format using direct FFmpeg, maintaining directory structure

    Args:
        wav_path: Path to the input WAV file (may be in cache)
        input_dir: Root input directory (cache dir if caching, original if not)
        output_dir: Root output directory
        ffmpeg_threads: Number of threads for FFmpeg to use
        compression_level: FLAC compression level (0-12)
        logger: Logger instance
        original_input_dir: Original input directory (for relative path calculation when caching)

    Returns:
        tuple: (success: bool, relative_path: str, message: str, input_size: int, output_size: int, duration: float)
    """
    start_time = time.time()
    input_size = 0
    output_size = 0
    
    try:
        # Calculate relative path from the input directory
        # When using cache, the cache preserves the original directory structure
        relative_path = wav_path.relative_to(input_dir)
        
        # Create output path maintaining directory structure
        output_filename = wav_path.stem + ".flac"
        output_file_path = output_dir / relative_path.parent / output_filename
        
        # Create subdirectories if they don't exist
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Get input file size
        input_size = wav_path.stat().st_size
        
        # Build FFmpeg command with optimization flags
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(wav_path),           # Input file (may be cached)
            '-threads', str(ffmpeg_threads), # Thread count
            '-c:a', 'flac',                # Audio codec: FLAC
            '-compression_level', str(compression_level),  # FLAC compression (0=fast, 12=best)
            '-y',                          # Overwrite output files
            '-v', 'error',                 # Only show errors (reduces overhead)
            '-nostdin',                    # Don't wait for stdin input
            str(output_file_path)          # Output file
        ]
        
        # Run FFmpeg conversion
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS
        )
        
        duration = time.time() - start_time
        
        if result.returncode == 0:
            # Get output file size
            if output_file_path.exists():
                output_size = output_file_path.stat().st_size
                compression_ratio = (1 - output_size / input_size) * 100 if input_size > 0 else 0
                
                message = f"Converted to {output_filename} ({compression_ratio:.1f}% smaller, {duration:.2f}s)"
                logger.info(f"✓ {relative_path}: {message}")
                return True, str(relative_path), message, input_size, output_size, duration
            else:
                error_msg = "FFmpeg completed but output file not found"
                logger.error(f"✗ {relative_path}: {error_msg}")
                return False, str(relative_path), error_msg, input_size, 0, duration
        else:
            error_msg = f"FFmpeg error (code {result.returncode}): {result.stderr.strip()}"
            logger.error(f"✗ {relative_path}: {error_msg}")
            return False, str(relative_path), error_msg, input_size, 0, duration
            
    except subprocess.TimeoutExpired:
        try:
            relative_path = wav_path.relative_to(input_dir)
        except ValueError:
            relative_path = wav_path.name
        error_msg = "Conversion timed out (>5 minutes)"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time
    except subprocess.CalledProcessError as e:
        try:
            relative_path = wav_path.relative_to(input_dir)
        except ValueError:
            relative_path = wav_path.name
        error_msg = f"FFmpeg process error: {str(e)}"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time
    except (OSError, IOError) as e:
        try:
            relative_path = wav_path.relative_to(input_dir)
        except ValueError:
            relative_path = wav_path.name
        error_msg = f"File I/O error: {str(e)}"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time
    except Exception as e:
        try:
            relative_path = wav_path.relative_to(input_dir)
        except ValueError:
            relative_path = wav_path.name
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time

def get_thread_count() -> int:
    """Prompt user for number of parallel conversions to run"""
    max_cores = os.cpu_count() or 1  # Default to 1 if cpu_count returns None

    while True:
        try:
            print(f"\nYour system has {max_cores} CPU cores available.")
            cores = input(f"How many parallel conversions would you like to run? (1-{max_cores}, default={max_cores}): ").strip()

            if not cores:
                return max_cores  # Default to maximum available cores

            cores = int(cores)

            if 1 <= cores <= max_cores:
                return cores
            else:
                print(f"Please enter a number between 1 and {max_cores}")

        except ValueError:
            print("Please enter a valid number")

def calculate_ffmpeg_threads(parallel_conversions: int) -> int:
    """
    Calculate optimal FFmpeg threads per process to avoid CPU oversubscription

    Args:
        parallel_conversions: Number of parallel file conversions

    Returns:
        Number of threads each FFmpeg process should use
    """
    max_cores = os.cpu_count() or 1

    # Each FFmpeg process should use a fraction of available cores
    # to avoid oversubscription when multiple conversions run in parallel
    ffmpeg_threads = max(1, max_cores // parallel_conversions)

    return ffmpeg_threads

def get_compression_level() -> int:
    """Prompt user for FLAC compression level"""
    while True:
        try:
            level = input(f"Choose compression level 0-12 (default={DEFAULT_COMPRESSION_LEVEL}): ").strip()

            if not level:
                return DEFAULT_COMPRESSION_LEVEL
            
            level = int(level)
            
            if 0 <= level <= 12:
                return level
            else:
                print("Please enter a number between 0 and 12")
                
        except ValueError:
            print("Please enter a valid number")

def validate_path(path_str: str) -> bool:
    """
    Validate that a path string is safe and doesn't contain suspicious patterns

    Args:
        path_str: The path string to validate

    Returns:
        True if path appears safe, False otherwise
    """
    # Check for null bytes (can cause security issues)
    if '\0' in path_str:
        return False

    # Normalize the path to resolve any '..' or symbolic links
    try:
        normalized = Path(path_str).resolve()
        # Basic check passed
        return True
    except (OSError, RuntimeError):
        # Path resolution failed
        return False

def get_input_directory() -> Path:
    """Prompt user for input directory and validate it exists"""
    while True:
        dir_path = input("\nEnter the directory path containing WAV files: ").strip()

        # Handle quotes around path
        if dir_path.startswith('"') and dir_path.endswith('"'):
            dir_path = dir_path[1:-1]

        # Validate path safety
        if not validate_path(dir_path):
            print(f"Error: Path '{dir_path}' contains invalid or unsafe characters.")
            print("Please try again.")
            continue

        path = Path(dir_path)

        if path.exists() and path.is_dir():
            return path
        else:
            print(f"Error: Directory '{dir_path}' does not exist or is not a directory.")
            print("Please try again.")

def ask_user_about_caching() -> bool:
    """Ask user if they want to use caching for network locations"""
    print("\n" + "="*50)
    print("NETWORK LOCATION DETECTION")
    print("="*50)
    
    while True:
        choice = input("Is this a network share? (ie: R:\\research) (y/N): ").strip().lower()
        if choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no', '']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")

def get_cache_directory() -> Path:
    """
    Prompt user for cache directory location and create a unique subdirectory.

    Returns:
        Path to the unique cache subdirectory (safe to delete entirely)
    """
    while True:
        print("\nFiles will be cached locally during conversion for better performance.")
        print("A unique temporary subdirectory will be created inside your chosen location.")
        cache_path = input("Enter parent directory for cache (will be created if needed): ").strip()

        # Handle quotes around path
        if cache_path.startswith('"') and cache_path.endswith('"'):
            cache_path = cache_path[1:-1]

        if not cache_path:
            print("Please enter a valid path.")
            continue

        # Validate path safety
        if not validate_path(cache_path):
            print(f"Error: Path '{cache_path}' contains invalid or unsafe characters.")
            print("Please try another location.")
            continue

        parent_dir = Path(cache_path)

        try:
            # Try to create the parent directory
            parent_dir.mkdir(parents=True, exist_ok=True)

            # Create a unique subdirectory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_cache_dir = parent_dir / f"wav2flac_cache_{timestamp}"

            # Create the unique cache directory
            unique_cache_dir.mkdir(parents=False, exist_ok=False)

            # Test write permissions
            test_file = unique_cache_dir / "test_write.tmp"
            test_file.write_text("test")
            test_file.unlink()

            print(f"✓ Cache subdirectory created: {unique_cache_dir.name}")
            return unique_cache_dir

        except FileExistsError:
            # Extremely unlikely, but retry with a different timestamp
            print("Cache directory already exists (rare). Retrying...")
            continue
        except PermissionError:
            print(f"Error: No write permission to '{cache_path}'. Please try another location.")
        except Exception as e:
            print(f"Error: Cannot create/access directory '{cache_path}': {e}")
            print("Please try another location.")

def copy_single_file_to_cache(
    wav_file: Path,
    input_dir: Path,
    cache_dir: Path,
    file_index: int,
    total_files: int
) -> Tuple[bool, Optional[Path], Path, int, float, int, int] | Tuple[bool, None, Path, int, float, int, int, str]:
    """Copy a single WAV file to local cache"""
    try:
        relative_path = wav_file.relative_to(input_dir)
        cached_file = cache_dir / relative_path
        
        # Create subdirectories in cache
        cached_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        file_size = wav_file.stat().st_size
        start_time = time.time()
        
        shutil.copy2(wav_file, cached_file)
        
        copy_time = time.time() - start_time
        copy_speed = file_size / copy_time / (1024 * 1024) if copy_time > 0 else 0
        
        return True, cached_file, relative_path, file_size, copy_speed, file_index, total_files

    except (OSError, IOError, PermissionError) as e:
        try:
            relative_path = wav_file.relative_to(input_dir)
        except ValueError:
            relative_path = Path(wav_file.name)
        return False, None, relative_path, 0, 0, file_index, total_files, f"File operation error: {str(e)}"
    except Exception as e:
        try:
            relative_path = wav_file.relative_to(input_dir)
        except ValueError:
            relative_path = Path(wav_file.name)
        return False, None, relative_path, 0, 0, file_index, total_files, f"Unexpected error: {str(e)}"

def check_cache_disk_space(wav_files: List[Path], cache_dir: Path, logger: logging.Logger) -> bool:
    """Check if cache directory has enough space for all WAV files"""
    # Calculate total size of all WAV files
    total_size_bytes = sum(f.stat().st_size for f in wav_files)
    total_size_gb = total_size_bytes / (1024 ** 3)
    
    try:
        # Get disk space information for cache directory
        total_space, used_space, free_space = shutil.disk_usage(cache_dir)
        free_space_gb = free_space / (1024 ** 3)
        
        # Add safety margin
        required_space_bytes = total_size_bytes * DISK_SPACE_SAFETY_MARGIN
        required_space_gb = required_space_bytes / (1024 ** 3)
        
        margin_percent = int((DISK_SPACE_SAFETY_MARGIN - 1) * 100)
        print(f"\nDisk space check:")
        print(f"WAV files to cache: {total_size_gb:.2f} GB")
        print(f"Required (with {margin_percent}% margin): {required_space_gb:.2f} GB")
        print(f"Available space: {free_space_gb:.2f} GB")
        
        if free_space < required_space_bytes:
            shortage_gb = (required_space_bytes - free_space) / (1024 ** 3)
            error_msg = f"Insufficient disk space! Need {shortage_gb:.2f} GB more."
            print(f"❌ {error_msg}")
            return False
        else:
            remaining_gb = (free_space - required_space_bytes) / (1024 ** 3)
            success_msg = f"✅ Sufficient space available ({remaining_gb:.2f} GB will remain free)"
            print(success_msg)
            return True
            
    except (OSError, PermissionError) as e:
        error_msg = f"Could not check disk space: {e}"
        print(f"⚠️  Warning: {error_msg}")
        
        # Ask user if they want to proceed anyway
        while True:
            choice = input("Proceed without disk space verification? (y/N): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no', '']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")

def copy_files_to_cache(
    wav_files: List[Path],
    input_dir: Path,
    cache_dir: Path,
    logger: logging.Logger
) -> Tuple[List[Path], List[Tuple[Path, str]]]:
    """Copy WAV files to local cache using optimized concurrent threads"""
    print("📁 Copying files to local cache...")
    
    cached_files = []
    failed_copies = []
    total_size = 0
    completed_count = 0
    start_time = time.time()
    
    # Use more threads for I/O operations (copying is I/O bound, not CPU bound)
    copy_threads = min(CACHE_COPY_THREADS, len(wav_files))
    
    # Use ThreadPoolExecutor for file copying
    with ThreadPoolExecutor(max_workers=copy_threads) as executor:
        # Submit all copy tasks
        future_to_file = {
            executor.submit(copy_single_file_to_cache, wav_file, input_dir, cache_dir, i+1, len(wav_files)): wav_file 
            for i, wav_file in enumerate(wav_files)
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_file):
            result = future.result()
            
            if result[0]:  # Success
                success, cached_file, relative_path, file_size, copy_speed, file_index, total_files = result
                cached_files.append(cached_file)
                total_size += file_size
                completed_count += 1
                
                # Show progress every N files or for small batches
                if completed_count % PROGRESS_REPORT_INTERVAL == 0 or len(wav_files) <= CONVERSION_PROGRESS_THRESHOLD:
                    print(f"✓ Cached {completed_count}/{total_files} files...")
                    sys.stdout.flush()  # Force output to appear immediately
                
            else:  # Failed
                success, cached_file, relative_path, file_size, copy_speed, file_index, total_files, error_msg = result
                failed_copies.append((future_to_file[future], error_msg))
                completed_count += 1

                logger.error(f"✗ Cache failed: {relative_path} - {error_msg}")
                print(f"✗ Cache failed: {relative_path}")
                sys.stdout.flush()
    
    # Final summary
    print(f"✅ Caching completed: {len(cached_files)} files ready for conversion")
    if failed_copies:
        print(f"⚠️  {len(failed_copies)} files failed to cache and will be skipped")
    
    return cached_files, failed_copies

def cleanup_cache(cache_dir: Path, logger: Optional[logging.Logger]) -> None:
    """
    Clean up the temporary cache directory created by get_cache_directory().

    This function safely deletes the unique cache subdirectory (e.g., wav2flac_cache_20250113_143022)
    that was created specifically for this conversion session.

    Args:
        cache_dir: Path to the unique cache subdirectory to delete
        logger: Optional logger instance for recording cleanup actions
    """
    try:
        if not cache_dir.exists():
            # Cache directory doesn't exist, no cleanup needed
            return

        # Safety check: verify this looks like our cache directory
        if not cache_dir.name.startswith("wav2flac_cache_"):
            print(f"⚠️  Warning: Cache directory name doesn't match expected pattern.")
            print(f"   Expected: wav2flac_cache_YYYYMMDD_HHMMSS")
            print(f"   Got: {cache_dir.name}")
            print(f"   Skipping cleanup for safety. You may need to manually delete: {cache_dir}")
            if logger:
                logger.warning(f"Skipped cleanup for unexpected cache dir name: {cache_dir}")
            return

        print(f"Cleaning up cache directory: {cache_dir.name}...")

        # Count files before deletion for logging
        file_count = sum(1 for _ in cache_dir.rglob('*') if _.is_file())

        # Delete the entire unique cache subdirectory
        shutil.rmtree(cache_dir)

        print(f"✓ Cache cleanup completed. Removed {file_count} cached files.")
        if logger:
            logger.info(f"Cache cleanup: deleted {file_count} files from {cache_dir}")

    except (OSError, PermissionError) as e:
        error_msg = f"Error during cache cleanup: {e}"
        print(f"⚠️  Warning: {error_msg}")
        print(f"   You may need to manually delete: {cache_dir}")
        if logger:
            logger.error(f"Cache cleanup failed: {e}", exc_info=True)

def setup_logging(output_dir: Path) -> Tuple[logging.Logger, Path]:
    """Set up logging to file only (not console)"""
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"wav_to_flac_conversion_{timestamp}.log"
    log_path = output_dir / log_filename
    
    # Get the root logger and clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Configure logging to file only (no console handler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8')
        ],
        force=True  # Force reconfiguration
    )
    
    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info("OPTIMIZED WAV to FLAC Conversion Log Started")
    logger.info("="*80)
    
    return logger, log_path

def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to a human-readable string

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "2m 30s" or "45s"
    """
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)

    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{remaining_seconds}s"

def find_wav_files(directory: Path) -> List[Path]:
    """Find all WAV files in the given directory and all subdirectories"""
    wav_files: List[Path] = []

    # Recursively look for files with .wav extension (case insensitive)
    wav_files.extend(directory.rglob('*.wav'))
    wav_files.extend(directory.rglob('*.WAV'))

    return sorted(set(wav_files))  # Remove duplicates and sort

def create_output_directory(input_dir: Path) -> Path:
    """Create output directory with '_converted' suffix"""
    output_dir_name = input_dir.name + "_converted"
    output_dir = input_dir.parent / output_dir_name
    
    # Create directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)
    
    return output_dir

def main() -> None:
    print("=" * 70)
    print("OPTIMIZED WAV to FLAC Converter with Direct FFmpeg")
    print("Maximum performance through FFmpeg's native multithreading")
    print("=" * 70)
    
    # Check prerequisites first
    issues = check_prerequisites()
    
    if issues:
        print(f"\n❌ Found {len(issues)} issue(s) that must be resolved:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        
        print(f"\n❌ Cannot proceed until all prerequisites are installed.")
        print("Please install FFmpeg and run the script again.")
        print("\nFFmpeg installation guides:")
        print("• Windows: https://www.wikihow.com/Install-FFmpeg-on-Windows")
        print("• macOS: brew install ffmpeg")
        print("• Linux: sudo apt install ffmpeg (or equivalent for your distribution)")
        
        sys.exit(1)
    
    print("\n✅ All prerequisites are installed and working!")
    print("-" * 40)
    
    # Get input directory
    input_dir = get_input_directory()
    print(f"Input directory: {input_dir}")
    
    # Ask user if they want to use caching
    use_cache = ask_user_about_caching()
    cache_dir = None
    original_input_dir = input_dir  # Keep reference to original
    
    if use_cache:
        cache_dir = get_cache_directory()
        print(f"✓ Temporary cache created: {cache_dir}")
    else:
        print("Proceeding without caching.")
    
    # Get compression level
    compression_level = get_compression_level()
    print(f"FLAC compression level: {compression_level}")
    
    # Get number of parallel conversions to run
    thread_count = get_thread_count()
    print(f"Using {thread_count} parallel conversions")

    # Calculate FFmpeg threads to avoid CPU oversubscription
    ffmpeg_threads = calculate_ffmpeg_threads(thread_count)
    print(f"Each FFmpeg process will use {ffmpeg_threads} thread(s)")

    # Create output directory first so we can set up logging
    output_dir = create_output_directory(original_input_dir)
    print(f"Output directory: {output_dir}")

    # Set up logging
    logger, log_path = setup_logging(output_dir)
    logger.info(f"Log file created: {log_path}")
    logger.info("Prerequisites check completed successfully")
    logger.info(f"Input directory: {original_input_dir}")
    logger.info(f"Parallel conversions: {thread_count}")
    logger.info(f"FFmpeg threads per process: {ffmpeg_threads}")
    logger.info(f"FLAC compression level: {compression_level}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"System: {os.name}, CPU cores: {os.cpu_count()}")
    
    try:
        # Find WAV files
        logger.info("Scanning for WAV files...")
        wav_files = find_wav_files(input_dir)
        
        if not wav_files:
            message = f"No WAV files found in '{input_dir}' or its subdirectories"
            print(f"\n{message}")
            logger.warning(message)
            print("Please make sure the directory contains WAV files and try again.")
            return
        
        logger.info(f"Found {len(wav_files)} WAV file(s) to convert")
        print(f"Found {len(wav_files)} WAV file(s) to convert")
        
        # Log each file found (but don't print to console)
        for wav_file in wav_files:
            relative_path = wav_file.relative_to(input_dir)
            logger.debug(f"Found: {relative_path} ({wav_file.stat().st_size:,} bytes)")
        
        # Check caching requirements if enabled (but don't copy files yet)
        if use_cache:
            # Check if cache directory has enough space
            if not check_cache_disk_space(wav_files, cache_dir, logger):
                print("\n❌ Cannot proceed due to insufficient disk space for caching.")
                return
            print("✅ Cache disk space check passed.")
        
        # Confirm before proceeding (before any file copying)
        files_to_convert = len(wav_files)
        total_size_mb = sum(f.stat().st_size for f in wav_files) / (1024 * 1024)

        print(f"\nReady to convert {files_to_convert} files ({total_size_mb:.1f} MB) using:")
        print(f"• {thread_count} parallel conversions")
        print(f"• {ffmpeg_threads} thread(s) per FFmpeg process")
        print(f"• FLAC compression level {compression_level}")
        
        if use_cache:
            print(f"• Local caching enabled")
            print(f"  - Temporary cache location: {cache_dir}")
            print(f"  - Cache will be automatically deleted after conversion")
        else:
            print(f"• Direct conversion (no caching)")
        
        confirm = input("\nProceed? (y/N): ").strip().lower()
        
        if confirm not in ['y', 'yes']:
            message = "Conversion cancelled by user"
            print(message)
            logger.info(message)
            return
        
        # Now handle caching after user confirmation
        cached_wav_files = wav_files
        original_input_for_conversion = input_dir  # Keep reference for relative path calculations
        
        if use_cache:
            print(f"\n📁 Copying {len(wav_files)} files to local cache...")
            print("This may take a few minutes depending on file sizes and network speed.")
            cached_wav_files, failed_copies = copy_files_to_cache(wav_files, input_dir, cache_dir, logger)
            
            if not cached_wav_files:
                print("❌ No files could be cached. Cannot proceed.")
                return
            
            # Update to use cached files for conversion
            wav_files = cached_wav_files
            input_dir = cache_dir  # This is where we'll read from
        
        # Start conversion
        print(f"\n🎵 Starting optimized conversion...")
        print("-" * 50)
        logger.info("Starting optimized conversion process...")
        
        start_time = time.time()
        successful_conversions = 0
        failed_conversions = 0
        converted_files = []  # Track successfully converted files
        failed_files = []     # Track failed files
        total_input_size = 0
        total_output_size = 0
        
        # Calculate total size for progress tracking
        total_input_size_initial = sum(f.stat().st_size for f in wav_files)
        logger.info(f"Total input size: {total_input_size_initial:,} bytes ({total_input_size_initial/1024/1024:.1f} MB)")
        
        # Use ThreadPoolExecutor with user-specified thread count
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            logger.info(f"Thread pool created with {thread_count} workers")
            
            # Submit all conversion tasks
            future_to_file = {
                executor.submit(convert_wav_to_flac_ffmpeg, wav_file, input_dir, output_dir,
                              ffmpeg_threads, compression_level, logger,
                              original_input_for_conversion if use_cache else None): wav_file
                for wav_file in wav_files
            }
            logger.info(f"Submitted {len(future_to_file)} conversion tasks")
            
            # Process completed tasks
            conversion_start_time = time.time()
            for i, future in enumerate(as_completed(future_to_file), 1):
                success, relative_path, message, input_size, output_size, duration = future.result()
                
                if success:
                    successful_conversions += 1
                    converted_files.append(relative_path)
                    total_input_size += input_size
                    total_output_size += output_size
                    
                    # Show progress every N files or for small batches, or always show failures
                    if i % PROGRESS_REPORT_INTERVAL_SMALL == 0 or len(wav_files) <= CONVERSION_PROGRESS_THRESHOLD:
                        print(f"✓ Converted {i}/{len(wav_files)} files...")
                        sys.stdout.flush()
                else:
                    failed_conversions += 1
                    failed_files.append((relative_path, message))
                    print(f"✗ ({i}/{len(wav_files)}) {relative_path}: {message}")
                    sys.stdout.flush()
        
        # Summary
        end_time = time.time()
        total_time = end_time - start_time
        
        print("-" * 50)
        print(f"✅ Conversion completed in {format_duration(total_time)}")
        print(f"Successful conversions: {successful_conversions}")
        if failed_conversions > 0:
            print(f"Failed conversions: {failed_conversions}")
        
        if successful_conversions > 0:
            avg_time = total_time / successful_conversions
            total_compression = ((total_input_size - total_output_size) / total_input_size * 100) if total_input_size > 0 else 0
            throughput_mbps = (total_input_size / total_time / (1024 * 1024)) if total_time > 0 else 0
            
            print(f"Average time per file: {avg_time:.2f} seconds")
            print(f"Overall compression: {total_compression:.1f}%")
            print(f"Throughput: {throughput_mbps:.1f} MB/s")
        
        print(f"Output directory: {output_dir}")
        print(f"Log file: {log_path}")
        
        if failed_conversions > 0:
            print(f"\n⚠️  {failed_conversions} file(s) failed to convert - check log for details")
        
        # Log detailed summary to file (not console)
        logger.info("="*50)
        logger.info("CONVERSION SUMMARY")
        logger.info("="*50)
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Files processed: {len(wav_files)}")
        logger.info(f"Successful: {successful_conversions}")
        logger.info(f"Failed: {failed_conversions}")
        logger.info(f"Success rate: {(successful_conversions/len(wav_files)*100):.1f}%")
        
        if successful_conversions > 0:
            avg_time_per_file = total_time / successful_conversions
            total_compression = ((total_input_size - total_output_size) / total_input_size * 100) if total_input_size > 0 else 0
            throughput_mbps = (total_input_size / total_time / (1024 * 1024)) if total_time > 0 else 0
            
            logger.info(f"Average time per file: {avg_time_per_file:.2f} seconds")
            logger.info(f"Total input size: {total_input_size:,} bytes")
            logger.info(f"Total output size: {total_output_size:,} bytes")
            logger.info(f"Overall compression: {total_compression:.1f}%")
            logger.info(f"Throughput: {throughput_mbps:.1f} MB/s")
        
        logger.info("="*80)
        logger.info("OPTIMIZED WAV to FLAC Conversion Log Completed")
        logger.info("="*80)
        
    finally:
        # Clean up cache if it was used
        if cache_dir and cache_dir.exists():
            cleanup_cache(cache_dir, logger if 'logger' in locals() else None)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nConversion interrupted by user.")
        # Try to log the interruption if logger exists
        try:
            logger = logging.getLogger(__name__)
            if logger.hasHandlers():
                logger.warning("Conversion interrupted by user (Ctrl+C)")
        except Exception:
            pass
        sys.exit(130)  # Standard exit code for SIGINT
    except (OSError, IOError) as e:
        print(f"\nFile I/O error: {e}")
        try:
            logger = logging.getLogger(__name__)
            if logger.hasHandlers():
                logger.error(f"File I/O error: {e}", exc_info=True)
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        # Try to log the error if logger exists
        try:
            logger = logging.getLogger(__name__)
            if logger.hasHandlers():
                logger.error(f"Unexpected error: {e}", exc_info=True)
        except Exception:
            pass
        sys.exit(1)