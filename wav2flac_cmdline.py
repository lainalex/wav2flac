#!/usr/bin/env python3
"""
OPTIMIZED WAV to FLAC Converter with Direct FFmpeg and Smart Threading
Leverages FFmpeg's native multithreading for maximum performance
Recursively converts all WAV files in a directory and subdirectories to FLAC format
Maintains the original folder structure in the output directory
Includes prerequisite checking and detailed installation help
Supports optional local caching for network locations and slow drives for improved performance
"""

import os
import sys
import logging
import subprocess
import shutil
import psutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime

def check_pip_available():
    """Check if pip is available and working"""
    pip_commands = [
        [sys.executable, '-m', 'pip', '--version'],
        ['pip3', '--version'],
        ['pip', '--version']
    ]
    
    for pip_cmd in pip_commands:
        try:
            result = subprocess.run(pip_cmd[:2] + ['--version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10)
            if result.returncode == 0:
                print(f"✓ Found working pip: {' '.join(pip_cmd[:2])}")
                return pip_cmd[:2]
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            continue
    
    return None

def install_python_package(package_name, import_name=None):
    """Install a Python package using pip"""
    if import_name is None:
        import_name = package_name
    
    print(f"\n📦 Installing {package_name}...")
    
    # Check if pip is available
    pip_base_cmd = check_pip_available()
    if not pip_base_cmd:
        print("❌ No working pip installation found!")
        print("Please install pip first: https://pip.pypa.io/en/stable/installation/")
        return False
    
    # Try to install the package
    install_cmd = pip_base_cmd + ['install', package_name]
    
    try:
        print(f"Running: {' '.join(install_cmd)}")
        result = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        if result.returncode == 0:
            print(f"✓ Successfully installed {package_name}")
            
            # Verify installation by trying to import
            try:
                __import__(import_name)
                print(f"✓ {package_name} import verification: OK")
                return True
            except ImportError as e:
                print(f"❌ {package_name} installed but import failed: {e}")
                print("This might indicate a virtual environment issue.")
                return False
        else:
            error_output = result.stderr.strip()
            print(f"❌ Installation failed: {error_output}")
            
            # Check for common issues and provide specific help
            if "permission denied" in error_output.lower():
                print("💡 Try: pip install --user psutil")
                print("   Or run with administrator/sudo privileges")
            elif "externally-managed-environment" in error_output.lower():
                print("💡 Your system uses externally managed Python packages.")
                print("   Try using a virtual environment:")
                print("   python -m venv myenv")
                print("   source myenv/bin/activate  # On Windows: myenv\\Scripts\\activate")
                print("   pip install psutil")
            
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ Installation timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during installation: {e}")
        return False

def auto_install_prerequisites():
    """Automatically install missing Python packages"""
    print("\n" + "="*60)
    print("AUTOMATIC PREREQUISITE INSTALLATION")
    print("="*60)
    
    # Ask for user permission
    print("This script can automatically install missing Python packages.")
    print("Required packages: psutil")
    print("\nNote: This will use pip to install packages to your Python environment.")
    print("If you're using a virtual environment, packages will be installed there.")
    
    while True:
        choice = input("\nAutomatically install missing packages? (y/N): ").strip().lower()
        if choice in ['y', 'yes']:
            break
        elif choice in ['n', 'no', '']:
            print("Skipping automatic installation.")
            print("💡 You can install manually using: pip install psutil")
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")
    
    print(f"\n🔍 Python environment info:")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    if in_venv:
        print("✓ Running in virtual environment")
    else:
        print("ℹ️  Running in system Python (not a virtual environment)")
    
    installation_success = True
    
    # Check and install psutil
    try:
        import psutil
        print("\n✓ psutil is already installed")
    except ImportError:
        print("\n📦 psutil not found, attempting installation...")
        if not install_python_package('psutil'):
            print("❌ Failed to install psutil automatically")
            installation_success = False
    
    if installation_success:
        print("\n✅ All Python packages are now installed!")
        print("Continuing with prerequisite check...")
        return True
    else:
        print("\n❌ Automatic installation failed.")
        print("Please install psutil manually and run the script again.")
        return False

def check_prerequisites():
    """Check if all required software is installed"""
    print("Checking prerequisites...")
    issues = []
    python_package_issues = []
    
    # Check Python version
    if sys.version_info < (3, 6):
        issues.append("Python 3.6 or higher is required")
    else:
        print("✓ Python version: OK")
    
    # Check psutil (for system info)
    try:
        import psutil
        print("✓ psutil library: OK")
    except ImportError:
        python_package_issues.append("psutil")
        print("✗ psutil library: NOT FOUND")
    
    # Check FFmpeg with detailed capability testing
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=10)
        if result.returncode == 0:
            # Extract FFmpeg version from output
            version_line = result.stdout.split('\n')[0]
            print(f"✓ FFmpeg: OK ({version_line.split()[2]})")
            
            # Test FLAC encoding capability
            flac_test = subprocess.run(['ffmpeg', '-encoders'], 
                                     capture_output=True, 
                                     text=True, 
                                     timeout=10)
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
    
    # If we have Python package issues, try to auto-install
    if python_package_issues:
        print(f"\n⚠️  Found {len(python_package_issues)} missing Python package(s)")
        
        if auto_install_prerequisites():
            # Re-check the packages after installation
            print("\nRe-checking installed packages...")
            remaining_issues = []
            
            # Re-check psutil
            try:
                import psutil
                print("✓ psutil library: OK (newly installed)")
            except ImportError:
                remaining_issues.append("psutil library is still not available after installation")
                print("✗ psutil library: STILL NOT FOUND")
            
            # Add any remaining Python package issues to main issues list
            issues.extend(remaining_issues)
        else:
            # Auto-installation failed or was declined
            issues.extend([f"{pkg} library is not installed (pip install {pkg})" for pkg in python_package_issues])
    
    return issues

def convert_wav_to_flac_ffmpeg(wav_path, input_dir, output_dir, ffmpeg_threads, compression_level, logger, original_input_dir=None):
    """
    Convert a single WAV file to FLAC format using direct FFmpeg, maintaining directory structure
    
    Args:
        wav_path (Path): Path to the input WAV file (may be in cache)
        input_dir (Path): Root input directory (cache dir if caching, original if not)
        output_dir (Path): Root output directory
        ffmpeg_threads (int): Number of threads for FFmpeg to use
        compression_level (int): FLAC compression level (0-12)
        logger: Logger instance
        original_input_dir (Path): Original input directory (for relative path calculation when caching)
    
    Returns:
        tuple: (success: bool, relative_path: str, message: str, input_size: int, output_size: int, duration: float)
    """
    start_time = time.time()
    input_size = 0
    output_size = 0
    
    try:
        # Calculate relative path from the appropriate base directory
        # If we're using cache, calculate relative path based on original structure
        if original_input_dir and original_input_dir != input_dir:
            # We're using cache - need to calculate relative path based on original structure
            # The cache preserves the original directory structure
            relative_path = wav_path.relative_to(input_dir)
        else:
            # Direct conversion - calculate relative path normally
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
            str(output_file_path)          # Output file
        ]
        
        # Run FFmpeg conversion
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per file
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
        error_msg = "Conversion timed out (>5 minutes)"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time
    except Exception as e:
        relative_path = wav_path.relative_to(input_dir)
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"✗ {relative_path}: {error_msg}")
        return False, str(relative_path), error_msg, input_size, 0, time.time() - start_time

def get_thread_count():
    """Prompt user for number of threads to use"""
    max_cores = psutil.cpu_count()
    
    while True:
        try:
            print(f"\nYour system has {max_cores} CPU cores available.")
            cores = input(f"How many cores would you like to use? (1-{max_cores}, default={max_cores}): ").strip()
            
            if not cores:
                return max_cores  # Default to maximum available cores
            
            cores = int(cores)
            
            if 1 <= cores <= max_cores:
                return cores
            else:
                print(f"Please enter a number between 1 and {max_cores}")
                
        except ValueError:
            print("Please enter a valid number")

def get_compression_level():
    """Prompt user for FLAC compression level"""
    while True:
        try:
            level = input("Choose compression level 0-12 (default=12): ").strip()
            
            if not level:
                return 12  # Default to maximum compression
            
            level = int(level)
            
            if 0 <= level <= 12:
                return level
            else:
                print("Please enter a number between 0 and 12")
                
        except ValueError:
            print("Please enter a valid number")

def get_input_directory():
    """Prompt user for input directory and validate it exists"""
    while True:
        dir_path = input("\nEnter the directory path containing WAV files: ").strip()
        
        # Handle quotes around path
        if dir_path.startswith('"') and dir_path.endswith('"'):
            dir_path = dir_path[1:-1]
        
        path = Path(dir_path)
        
        if path.exists() and path.is_dir():
            return path
        else:
            print(f"Error: Directory '{dir_path}' does not exist or is not a directory.")
            print("Please try again.")

def ask_user_about_caching():
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

def get_cache_directory():
    """Prompt user for cache directory location"""
    while True:
        print("\nFiles will be cached locally during conversion for better performance.")
        cache_path = input("Enter local cache directory path (will be created if needed): ").strip()
        
        # Handle quotes around path
        if cache_path.startswith('"') and cache_path.endswith('"'):
            cache_path = cache_path[1:-1]
        
        if not cache_path:
            print("Please enter a valid path.")
            continue
            
        cache_dir = Path(cache_path)
        
        try:
            # Try to create the directory
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions
            test_file = cache_dir / "test_write.tmp"
            test_file.write_text("test")
            test_file.unlink()
            
            return cache_dir
            
        except PermissionError:
            print(f"Error: No write permission to '{cache_path}'. Please try another location.")
        except Exception as e:
            print(f"Error: Cannot create/access directory '{cache_path}': {e}")
            print("Please try another location.")

def copy_single_file_to_cache(wav_file, input_dir, cache_dir, file_index, total_files):
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
        
    except Exception as e:
        relative_path = wav_file.relative_to(input_dir)
        return False, None, relative_path, 0, 0, file_index, total_files, str(e)

def check_cache_disk_space(wav_files, cache_dir, logger):
    """Check if cache directory has enough space for all WAV files"""
    # Calculate total size of all WAV files
    total_size_bytes = sum(f.stat().st_size for f in wav_files)
    total_size_gb = total_size_bytes / (1024 ** 3)
    
    try:
        # Get disk space information for cache directory
        total_space, used_space, free_space = shutil.disk_usage(cache_dir)
        free_space_gb = free_space / (1024 ** 3)
        
        # Add 20% safety margin
        required_space_bytes = total_size_bytes * 1.2
        required_space_gb = required_space_bytes / (1024 ** 3)
        
        print(f"\nDisk space check:")
        print(f"WAV files to cache: {total_size_gb:.2f} GB")
        print(f"Required (with 20% margin): {required_space_gb:.2f} GB")
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
            
    except Exception as e:
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

def copy_files_to_cache(wav_files, input_dir, cache_dir, logger):
    """Copy WAV files to local cache using optimized concurrent threads"""
    print("📁 Copying files to local cache...")
    
    cached_files = []
    failed_copies = []
    total_size = 0
    completed_count = 0
    start_time = time.time()
    
    # Use more threads for I/O operations (copying is I/O bound, not CPU bound)
    copy_threads = min(8, len(wav_files))
    
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
                
                # Show progress every 10 files or for small batches
                if completed_count % 10 == 0 or len(wav_files) <= 20:
                    print(f"✓ Cached {completed_count}/{total_files} files...")
                    sys.stdout.flush()  # Force output to appear immediately
                
            else:  # Failed
                success, cached_file, relative_path, file_size, copy_speed, file_index, total_files, error_msg = result
                failed_copies.append((future_to_file[future], error_msg))
                completed_count += 1
                
                print(f"✗ Cache failed: {relative_path}")
                sys.stdout.flush()
    
    # Final summary
    print(f"✅ Caching completed: {len(cached_files)} files ready for conversion")
    if failed_copies:
        print(f"⚠️  {len(failed_copies)} files failed to cache and will be skipped")
    
    return cached_files, failed_copies

def cleanup_cache(cache_dir, logger):
    """Clean up the cache directory"""
    try:
        if cache_dir.exists():
            print(f"Cleaning up cache directory...")
            
            # Count files before deletion for logging
            file_count = sum(1 for _ in cache_dir.rglob('*') if _.is_file())
            
            shutil.rmtree(cache_dir)
            
            print(f"✓ Cache cleanup completed. Removed {file_count} cached files.")
        else:
            pass  # Cache directory doesn't exist, no cleanup needed
            
    except Exception as e:
        error_msg = f"Error during cache cleanup: {e}"
        print(f"Warning: {error_msg}")
        print("You may need to manually delete the cache directory.")

def setup_logging(output_dir):
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

def find_wav_files(directory):
    """Find all WAV files in the given directory and all subdirectories"""
    wav_files = []
    
    # Recursively look for files with .wav extension (case insensitive)
    wav_files.extend(directory.rglob('*.wav'))
    wav_files.extend(directory.rglob('*.WAV'))
    
    return sorted(set(wav_files))  # Remove duplicates and sort

def create_output_directory(input_dir):
    """Create output directory with '_converted' suffix"""
    output_dir_name = input_dir.name + "_converted"
    output_dir = input_dir.parent / output_dir_name
    
    # Create directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)
    
    return output_dir

def main():
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
        
        # Check if only FFmpeg is missing (Python packages were auto-installed)
        ffmpeg_only = all('ffmpeg' in issue.lower() for issue in issues)
        
        if ffmpeg_only:
            print(f"\n⚠️  Only FFmpeg needs manual installation.")
            print("Python packages have been installed automatically.")
            print("Please install FFmpeg and run the script again.")
        else:
            print(f"\n❌ Cannot proceed until all prerequisites are installed.")
            print("Please install the missing components and try again.")
        
        sys.exit(1)
    
    print("\n✅ All prerequisites are installed and working!")
    
    # Import psutil here after ensuring it's installed
    try:
        import psutil
    except ImportError:
        print("❌ psutil import failed. Please restart the script.")
        sys.exit(1)
    
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
        print(f"Cache directory: {cache_dir}")
    else:
        print("Proceeding without caching.")
    
    # Get compression level
    compression_level = get_compression_level()
    print(f"FLAC compression level: {compression_level}")
    
    # Get number of threads to use
    thread_count = get_thread_count()
    print(f"Using {thread_count} CPU cores for conversion")
    
    # Create output directory first so we can set up logging
    output_dir = create_output_directory(original_input_dir)
    print(f"Output directory: {output_dir}")
    
    # Set up logging
    logger, log_path = setup_logging(output_dir)
    logger.info(f"Log file created: {log_path}")
    logger.info("Prerequisites check completed successfully")
    logger.info(f"Input directory: {original_input_dir}")
    logger.info(f"Thread count: {thread_count}")
    logger.info(f"FLAC compression level: {compression_level}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"System: {os.name}, CPU cores: {psutil.cpu_count()}")
    
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
        print(f"• {thread_count} CPU cores")
        print(f"• FLAC compression level {compression_level}")
        
        if use_cache:
            print(f"• Local caching enabled")
            print(f"  - Files will be copied to: {cache_dir}")
            print(f"  - Cache will be cleaned up automatically after conversion")
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
            
            if failed_copies:
                print(f"⚠️  {len(failed_copies)} files failed to cache and will be skipped.")
            
            # Update to use cached files for conversion, but keep original input_dir for relative paths
            wav_files = cached_wav_files
            input_dir = cache_dir  # This is where we'll read from
            
            print(f"✅ Caching completed. {len(cached_wav_files)} files ready for conversion.")
        
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
                              thread_count, compression_level, logger,
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
                    
                    # Show progress every 5 files or for small batches, or always show failures
                    if i % 5 == 0 or len(wav_files) <= 20:
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
        print(f"✅ Conversion completed in {total_time:.2f} seconds")
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
    cache_dir = None  # Initialize for cleanup
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nConversion interrupted by user.")
        # Try to log the interruption if logger exists
        try:
            logger = logging.getLogger(__name__)
            logger.warning("Conversion interrupted by user (Ctrl+C)")
        except:
            pass
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        # Try to log the error if logger exists
        try:
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error: {e}", exc_info=True)
        except:
            pass
        sys.exit(1)