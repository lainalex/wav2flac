#!/usr/bin/env python3
"""
WAV to FLAC Converter - Windows GUI Application
Converts WAV files to FLAC format with a user-friendly interface
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
import threading
import queue
import zipfile
import urllib.request
import urllib.error
import platform
import ssl

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import tkinter.font as tkfont

class WAVtoFLACConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("WAV to FLAC Converter")
        self.root.geometry("700x700")
        self.root.minsize(600, 600)
        
        # Set application icon
        self.set_application_icon()
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('winnative')
        
        # Variables
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.use_cache = tk.BooleanVar()
        self.cache_dir = tk.StringVar()
        self.thread_count = tk.IntVar(value=os.cpu_count() or 1)
        self.compression_level = tk.IntVar(value=12)
        
        # Conversion state
        self.is_converting = False
        self.conversion_thread = None
        self.executor = None
        self.logger = None
        self.log_file_path = None
        
        # FFmpeg installation state
        self.is_installing_ffmpeg = False
        self.ffmpeg_install_thread = None
        
        # Progress tracking
        self.progress_queue = queue.Queue()
        self.log_queue = queue.Queue()
        
        # FFmpeg installation path
        self.ffmpeg_dir = Path.home() / ".wav_flac_converter" / "ffmpeg"
        
        # Create GUI
        self.create_widgets()
        self.check_prerequisites()
        
        # Start queue processing
        self.process_queues()
        
    def set_application_icon(self):
        """Set the application icon using multiple fallback methods"""
        try:
            # Method 1: Try to load icon file from same directory as script
            icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
                return
                
            # Method 2: Try PNG file with iconphoto
            png_icon_path = Path(__file__).parent / "icon.png"
            if png_icon_path.exists():
                icon_image = tk.PhotoImage(file=str(png_icon_path))
                self.root.iconphoto(True, icon_image)
                return
                
            # Method 3: Use embedded icon data (Base64 encoded)
            self.set_embedded_icon()
            
        except Exception as e:
            # If all else fails, just continue without icon
            print(f"Could not set application icon: {e}")
            
    def set_embedded_icon(self):
        """Set icon using embedded Base64 data (example - replace with your icon)"""
        try:
            # This is a simple 16x16 audio icon encoded as Base64
            # Replace this with your own branded icon data
            icon_data = """
            iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz
            AAAB2AAAAdgB+lymcgAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAE5SURB
            VDiNpZM9SwNBEIafgGBhI2qbVjYWFhY2traxsLGwsLCwsLGwsLGwsLCwsLGwsLCwsLGwsLCwsLGw
            sLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGw
            sLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCw
            sLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGwsLCwsLGw
            """
            
            # Create PhotoImage from Base64 data
            icon_image = tk.PhotoImage(data=icon_data)
            self.root.iconphoto(True, icon_image)
            
        except Exception:
            # Create a simple text-based icon as ultimate fallback
            self.create_simple_icon()
            
    def create_simple_icon(self):
        """Create a simple programmatic icon as fallback"""
        try:
            # Create a simple 16x16 icon programmatically
            icon_image = tk.PhotoImage(width=16, height=16)
            
            # Create a simple audio wave pattern
            # Fill with a basic pattern (blue background with white wave)
            for x in range(16):
                for y in range(16):
                    if y == 8 or (y == 7 and x % 4 == 0) or (y == 9 and x % 4 == 2):
                        icon_image.put("white", (x, y))
                    else:
                        icon_image.put("#0078d4", (x, y))
            
            self.root.iconphoto(True, icon_image)
            
        except Exception:
            pass  # Give up on icon if all methods fail
        
    def create_widgets(self):
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Title
        title_label = ttk.Label(main_frame, text="WAV to FLAC Converter", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # Input directory selection
        ttk.Label(main_frame, text="Input Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        input_entry = ttk.Entry(main_frame, textvariable=self.input_dir, width=40)
        input_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=5)
        input_entry.bind('<FocusOut>', self.on_input_dir_changed)  # Update output when input changes
        ttk.Button(main_frame, text="Browse", command=self.browse_input_dir).grid(row=row, column=2, pady=5)
        row += 1
        
        # Output directory display (auto-generated, read-only)
        ttk.Label(main_frame, text="Output Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        output_entry = ttk.Entry(main_frame, textvariable=self.output_dir, width=40, state='readonly')
        output_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=5)
        ttk.Label(main_frame, text="(Auto)", foreground='gray').grid(row=row, column=2, pady=5)
        row += 1
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Conversion Settings", padding="10")
        settings_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        settings_frame.columnconfigure(1, weight=1)
        row += 1
        
        # Thread count
        ttk.Label(settings_frame, text="CPU Cores:").grid(row=0, column=0, sticky=tk.W, pady=2)
        thread_frame = ttk.Frame(settings_frame)
        thread_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0), pady=2)
        ttk.Scale(thread_frame, from_=1, to=os.cpu_count() or 1, variable=self.thread_count, 
                 orient=tk.HORIZONTAL).grid(row=0, column=0, sticky=(tk.W, tk.E))
        thread_frame.columnconfigure(0, weight=1)
        ttk.Label(thread_frame, textvariable=self.thread_count).grid(row=0, column=1, padx=(5, 0))
        
        # Compression level
        ttk.Label(settings_frame, text="Compression Level:").grid(row=1, column=0, sticky=tk.W, pady=2)
        comp_frame = ttk.Frame(settings_frame)
        comp_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(5, 0), pady=2)
        ttk.Scale(comp_frame, from_=0, to=12, variable=self.compression_level, 
                 orient=tk.HORIZONTAL).grid(row=0, column=0, sticky=(tk.W, tk.E))
        comp_frame.columnconfigure(0, weight=1)
        ttk.Label(comp_frame, textvariable=self.compression_level).grid(row=0, column=1, padx=(5, 0))
        
        # Caching options
        cache_frame = ttk.LabelFrame(main_frame, text="Caching Options", padding="10")
        cache_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        cache_frame.columnconfigure(1, weight=1)
        row += 1
        
        ttk.Checkbutton(cache_frame, text="Use local caching (for network drives)", 
                       variable=self.use_cache, command=self.toggle_cache).grid(row=0, column=0, columnspan=3, sticky=tk.W)
        
        ttk.Label(cache_frame, text="Cache Directory:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.cache_entry = ttk.Entry(cache_frame, textvariable=self.cache_dir, width=40, state='disabled')
        self.cache_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=5)
        self.cache_browse_btn = ttk.Button(cache_frame, text="Browse", command=self.browse_cache_dir, state='disabled')
        self.cache_browse_btn.grid(row=1, column=2, pady=5)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        row += 1
        
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.progress_var).grid(row=0, column=0, sticky=tk.W)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # Status and file info
        self.status_var = tk.StringVar(value="")
        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=2, column=0, sticky=tk.W)
        
        # Log display
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(row, weight=1)
        row += 1
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=('Consolas', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Control buttons (moved below log)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=10)
        row += 1
        
        self.start_btn = ttk.Button(button_frame, text="Start Conversion", command=self.start_conversion)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="Stop", command=self.stop_conversion, state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=5)
        
        self.install_ffmpeg_btn = ttk.Button(button_frame, text="Install FFmpeg", command=self.show_ffmpeg_install_dialog)
        self.install_ffmpeg_btn.grid(row=0, column=2, padx=5)
        
    def toggle_cache(self):
        """Enable/disable cache directory selection"""
        if self.use_cache.get():
            self.cache_entry.config(state='normal')
            self.cache_browse_btn.config(state='normal')
        else:
            self.cache_entry.config(state='disabled')
            self.cache_browse_btn.config(state='disabled')
            
    def browse_input_dir(self):
        """Browse for input directory"""
        directory = filedialog.askdirectory(title="Select Input Directory with WAV files")
        if directory:
            self.input_dir.set(directory)
            # Auto-set output directory with '_converted' suffix (like original script)
            input_path = Path(directory)
            output_path = input_path.parent / (input_path.name + "_converted")
            self.output_dir.set(str(output_path))
            
    def on_input_dir_changed(self, event=None):
        """Update output directory when input directory is manually changed"""
        if self.input_dir.get():
            try:
                input_path = Path(self.input_dir.get())
                if input_path.exists() and input_path.is_dir():
                    output_path = input_path.parent / (input_path.name + "_converted")
                    self.output_dir.set(str(output_path))
            except Exception:
                pass  # Ignore invalid paths during typing
                
    def browse_cache_dir(self):
        """Browse for cache directory"""
        directory = filedialog.askdirectory(title="Select Cache Directory")
        if directory:
            self.cache_dir.set(directory)
            
    def check_prerequisites(self):
        """Check if FFmpeg is available"""
        self.log_message("Checking prerequisites...")
        
        # First check if FFmpeg is in PATH
        if self.check_ffmpeg_in_path():
            return True
            
        # Then check if we have a local installation
        if self.check_local_ffmpeg():
            return True
            
        # FFmpeg not found
        self.log_message("✗ FFmpeg not found")
        self.install_ffmpeg_btn.config(text="⚠ Install FFmpeg (Required)")
        return False
        
    def check_ffmpeg_in_path(self):
        """Check if FFmpeg is available in system PATH"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                self.log_message(f"✓ FFmpeg found in PATH: {version_line.split()[2]}")
                
                # Test FLAC encoding
                if self.check_flac_support('ffmpeg'):
                    self.install_ffmpeg_btn.config(text="Reinstall FFmpeg")
                    return True
                    
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False
        
    def check_local_ffmpeg(self):
        """Check if we have a local FFmpeg installation"""
        local_ffmpeg = self.ffmpeg_dir / "bin" / "ffmpeg.exe"
        if local_ffmpeg.exists():
            try:
                result = subprocess.run([str(local_ffmpeg), '-version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    self.log_message(f"✓ Local FFmpeg found: {version_line.split()[2]}")
                    
                    if self.check_flac_support(str(local_ffmpeg)):
                        self.install_ffmpeg_btn.config(text="Reinstall FFmpeg")
                        return True
                        
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return False
        
    def check_flac_support(self, ffmpeg_path):
        """Check if FFmpeg supports FLAC encoding"""
        try:
            flac_test = subprocess.run([ffmpeg_path, '-encoders'], 
                                     capture_output=True, text=True, timeout=10)
            if 'flac' in flac_test.stdout.lower():
                self.log_message("✓ FLAC encoding supported")
                return True
            else:
                self.log_message("✗ FLAC encoding not supported")
                return False
        except Exception:
            return False
            
    def get_ffmpeg_path(self):
        """Get the path to FFmpeg executable"""
        # Try local installation first
        local_ffmpeg = self.ffmpeg_dir / "bin" / "ffmpeg.exe"
        if local_ffmpeg.exists():
            return str(local_ffmpeg)
        # Fall back to system PATH
        return "ffmpeg"
            
    def log_message(self, message):
        """Add message to log display and file"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        # Add to queue for thread-safe GUI updates
        self.log_queue.put(formatted_message)
        
        # Also log to file if logger is set up
        if self.logger:
            # Remove timestamp from message since logging adds its own
            clean_message = message
            if message.startswith('✓'):
                self.logger.info(clean_message)
            elif message.startswith('✗'):
                self.logger.error(clean_message)
            elif message.startswith('⚠'):
                self.logger.warning(clean_message)
            else:
                self.logger.info(clean_message)
                
    def setup_file_logging(self, output_dir):
        """Set up logging to file (like original script)"""
        try:
            # Create log filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"wav_to_flac_conversion_{timestamp}.log"
            self.log_file_path = Path(output_dir) / log_filename
            
            # Get the root logger and clear any existing handlers (like original)
            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            
            # Configure logging to file only (no console handler)
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.log_file_path, encoding='utf-8')
                ],
                force=True  # Force reconfiguration
            )
            
            self.logger = logging.getLogger(__name__)
            self.logger.info("="*80)
            self.logger.info("OPTIMIZED WAV to FLAC Conversion Log Started")
            self.logger.info("="*80)
            
            return self.logger, self.log_file_path
            
        except Exception as e:
            self.log_message(f"Warning: Could not set up file logging: {e}")
            return None, None
        
    def update_progress(self, current, total, message=""):
        """Update progress bar and status"""
        progress_info = {
            'current': current,
            'total': total,
            'message': message
        }
        self.progress_queue.put(progress_info)
        
    def process_queues(self):
        """Process log and progress queues (called from main thread)"""
        # Process log messages
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message)
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
            
        # Process progress updates
        try:
            while True:
                progress_info = self.progress_queue.get_nowait()
                current = progress_info['current']
                total = progress_info['total']
                message = progress_info['message']
                
                if total > 0:
                    percentage = (current / total) * 100
                    self.progress_bar['value'] = percentage
                    self.progress_var.set(f"Progress: {current}/{total} ({percentage:.1f}%)")
                
                if message:
                    self.status_var.set(message)
                    
        except queue.Empty:
            pass
            
        # Schedule next update
        self.root.after(100, self.process_queues)
        
    def validate_inputs(self):
        """Validate user inputs before starting conversion"""
        if not self.input_dir.get():
            messagebox.showerror("Error", "Please select an input directory")
            return False
            
        input_path = Path(self.input_dir.get())
        if not input_path.exists() or not input_path.is_dir():
            messagebox.showerror("Error", "Input directory does not exist")
            return False
            
        if self.use_cache.get() and not self.cache_dir.get():
            messagebox.showerror("Error", "Please select a cache directory when caching is enabled")
            return False
            
        # Check if FFmpeg is available
        if not (self.check_ffmpeg_in_path() or self.check_local_ffmpeg()):
            result = messagebox.askyesno("FFmpeg Not Found", 
                                       "FFmpeg is required for conversion but was not found.\n\n"
                                       "Would you like to install FFmpeg now?")
            if result:
                self.show_ffmpeg_install_dialog()
            return False
            
        return True
        
    def find_wav_files(self, directory):
        """Find all WAV files in directory and subdirectories"""
        wav_files = []
        directory = Path(directory)
        
        # Find WAV files (case insensitive)
        wav_files.extend(directory.rglob('*.wav'))
        wav_files.extend(directory.rglob('*.WAV'))
        
        return sorted(set(wav_files))
        
    def convert_single_file(self, wav_path, input_dir, output_dir, original_input_dir=None):
        """Convert a single WAV file to FLAC (matching original script logic exactly)"""
        start_time = time.time()
        input_size = 0
        output_size = 0
        
        try:
            # Calculate relative path (matching original logic)
            if original_input_dir and original_input_dir != input_dir:
                # We're using cache - need to calculate relative path based on original structure
                relative_path = wav_path.relative_to(input_dir)
            else:
                # Direct conversion - calculate relative path normally
                relative_path = wav_path.relative_to(input_dir)
                
            # Create output path maintaining directory structure (like original)
            output_filename = wav_path.stem + ".flac"
            output_file_path = output_dir / relative_path.parent / output_filename
            
            # Create subdirectories if they don't exist (like original)
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get input file size (like original)
            input_size = wav_path.stat().st_size
            
            # Build FFmpeg command with optimization flags (like original)
            ffmpeg_path = self.get_ffmpeg_path()
            ffmpeg_cmd = [
                ffmpeg_path,
                '-i', str(wav_path),                    # Input file (may be cached)
                '-threads', str(self.thread_count.get()), # Thread count
                '-c:a', 'flac',                         # Audio codec: FLAC
                '-compression_level', str(self.compression_level.get()), # FLAC compression (0=fast, 12=best)
                '-y',                                   # Overwrite output files
                '-v', 'error',                          # Only show errors (reduces overhead)
                str(output_file_path)                   # Output file
            ]
            
            # Run FFmpeg conversion (with same timeout as original)
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per file
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                # Get output file size (like original)
                if output_file_path.exists():
                    output_size = output_file_path.stat().st_size
                    compression_ratio = (1 - output_size / input_size) * 100 if input_size > 0 else 0
                    
                    # Message format exactly like original script
                    message = f"Converted to {output_filename} ({compression_ratio:.1f}% smaller, {duration:.2f}s)"
                    return True, str(relative_path), message, input_size, output_size
                else:
                    error_msg = "FFmpeg completed but output file not found"
                    return False, str(relative_path), error_msg, input_size, 0
            else:
                # Error message format like original script
                error_msg = f"FFmpeg error (code {result.returncode}): {result.stderr.strip()}"
                return False, str(relative_path), error_msg, input_size, 0
                
        except subprocess.TimeoutExpired:
            error_msg = "Conversion timed out (>5 minutes)"
            return False, str(relative_path), error_msg, input_size, 0
        except Exception as e:
            relative_path = wav_path.relative_to(input_dir)
            error_msg = f"Unexpected error: {str(e)}"
            return False, str(relative_path), error_msg, input_size, 0
            
    def copy_files_to_cache(self, wav_files, input_dir, cache_dir):
        """Copy WAV files to cache directory (with logging like original script)"""
        self.log_message(f"Copying {len(wav_files)} files to local cache...")
        
        if self.logger:
            self.logger.info(f"Starting cache operation for {len(wav_files)} files")
            self.logger.info(f"Cache directory: {cache_dir}")
        
        cached_files = []
        failed_copies = []
        
        try:
            cache_path = Path(cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            
            for i, wav_file in enumerate(wav_files):
                if not self.is_converting:  # Check if stopped
                    break
                    
                try:
                    relative_path = wav_file.relative_to(input_dir)
                    cached_file = cache_path / relative_path
                    
                    # Create subdirectories in cache
                    cached_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file with timing (like original)
                    file_size = wav_file.stat().st_size
                    start_time = time.time()
                    
                    shutil.copy2(wav_file, cached_file)
                    
                    copy_time = time.time() - start_time
                    copy_speed = file_size / copy_time / (1024 * 1024) if copy_time > 0 else 0
                    
                    cached_files.append(cached_file)
                    
                    # Log like original script (every 10 files or for small batches)
                    if (i + 1) % 10 == 0 or len(wav_files) <= 20:
                        progress_msg = f"Cached {i + 1}/{len(wav_files)} files..."
                        self.log_message(f"✓ {progress_msg}")
                        if self.logger:
                            self.logger.info(f"Cached: {relative_path} ({copy_speed:.1f} MB/s)")
                    
                    self.update_progress(i + 1, len(wav_files), f"Caching: {relative_path.name}")
                    
                except Exception as e:
                    relative_path = wav_file.relative_to(input_dir)
                    failed_copies.append((wav_file, str(e)))
                    error_msg = f"Cache failed: {relative_path}"
                    self.log_message(f"✗ {error_msg}")
                    if self.logger:
                        self.logger.error(f"Cache failed for {relative_path}: {e}")
                
        except Exception as e:
            error_msg = f"Cache setup error: {e}"
            self.log_message(f"✗ {error_msg}")
            if self.logger:
                self.logger.error(error_msg)
                
        # Final summary (like original)
        summary_msg = f"Caching completed: {len(cached_files)} files ready for conversion"
        self.log_message(f"✅ {summary_msg}")
        if self.logger:
            self.logger.info(summary_msg)
            
        if failed_copies:
            failure_msg = f"{len(failed_copies)} files failed to cache and will be skipped"
            self.log_message(f"⚠️  {failure_msg}")
            if self.logger:
                self.logger.warning(failure_msg)
                
        return cached_files
        
    def cleanup_cache(self, cache_dir):
        """Clean up the cache directory (with logging like original script)"""
        try:
            if Path(cache_dir).exists():
                self.log_message("Cleaning up cache directory...")
                if self.logger:
                    self.logger.info("Starting cache cleanup")
                
                # Count files before deletion for logging (like original)
                file_count = sum(1 for _ in Path(cache_dir).rglob('*') if _.is_file())
                
                shutil.rmtree(cache_dir)
                
                cleanup_msg = f"Cache cleanup completed. Removed {file_count} cached files."
                self.log_message(f"✓ {cleanup_msg}")
                if self.logger:
                    self.logger.info(cleanup_msg)
            else:
                if self.logger:
                    self.logger.debug("Cache directory does not exist, no cleanup needed")
                    
        except Exception as e:
            error_msg = f"Error during cache cleanup: {e}"
            self.log_message(f"Warning: {error_msg}")
            self.log_message("You may need to manually delete the cache directory.")
            if self.logger:
                self.logger.error(error_msg)
            
    def conversion_worker(self):
        """Main conversion worker thread"""
        try:
            self.log_message("Starting conversion...")
            
            input_dir = Path(self.input_dir.get())
            output_dir = Path(self.output_dir.get())
            
            # Create output directory (like original script)
            output_dir.mkdir(parents=True, exist_ok=True)
            self.log_message(f"Created output directory: {output_dir}")
            
            # Set up file logging
            self.setup_file_logging(output_dir)
            
            # Enable log file button
            self.root.after(0, lambda: self.open_log_btn.config(state='normal'))
            
            # Find WAV files
            wav_files = self.find_wav_files(input_dir)
            if not wav_files:
                self.log_message("No WAV files found")
                return
                
            self.log_message(f"Found {len(wav_files)} WAV files")
            
            # Handle caching
            files_to_convert = wav_files
            conversion_input_dir = input_dir
            original_input_dir = input_dir
            cache_dir_path = None
            
            if self.use_cache.get():
                cache_dir_path = Path(self.cache_dir.get())
                cached_files = self.copy_files_to_cache(wav_files, input_dir, cache_dir_path)
                
                if not self.is_converting:  # Stopped during caching
                    return
                    
                files_to_convert = cached_files
                conversion_input_dir = cache_dir_path
                
            # Start conversion
            self.log_message("Starting file conversion...")
            successful = 0
            failed = 0
            total_input_size = 0
            total_output_size = 0
            
            start_time = time.time()
            
            # Use ThreadPoolExecutor for conversion
            with ThreadPoolExecutor(max_workers=self.thread_count.get()) as executor:
                # Submit all tasks
                futures = {
                    executor.submit(self.convert_single_file, wav_file, conversion_input_dir, 
                                  output_dir, original_input_dir): wav_file 
                    for wav_file in files_to_convert
                }
                
                # Process results
                for i, future in enumerate(as_completed(futures), 1):
                    if not self.is_converting:  # Check if stopped
                        break
                        
                    success, relative_path, message, input_size, output_size = future.result()
                    
                    if success:
                        successful += 1
                        total_input_size += input_size
                        total_output_size += output_size
                        self.log_message(f"✓ {relative_path}: {message}")
                    else:
                        failed += 1
                        self.log_message(f"✗ {relative_path}: {message}")
                        
                    self.update_progress(i, len(files_to_convert), f"Converted: {Path(relative_path).name}")
                    
            # Summary
            total_time = time.time() - start_time
            
            if successful > 0:
                compression_ratio = ((total_input_size - total_output_size) / total_input_size * 100) if total_input_size > 0 else 0
                self.log_message(f"Conversion completed in {total_time:.1f}s")
                self.log_message(f"Successful: {successful}, Failed: {failed}")
                self.log_message(f"Overall compression: {compression_ratio:.1f}%")
            
            self.update_progress(len(files_to_convert), len(files_to_convert), "Conversion completed!")
            
        except Exception as e:
            error_msg = f"Conversion error: {e}"
            self.log_message(f"✗ {error_msg}")
            if self.logger:
                self.logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            # Cleanup (like original script)
            if cache_dir_path:
                self.cleanup_cache(cache_dir_path)
                
            # Reset UI state
            self.root.after(0, self.conversion_finished)
            
    def conversion_finished(self):
        """Called when conversion is finished"""
        self.is_converting = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        
    def start_conversion(self):
        """Start the conversion process"""
        if not self.validate_inputs():
            return
            
        # Confirm start
        wav_files = self.find_wav_files(self.input_dir.get())
        if not wav_files:
            messagebox.showwarning("No Files", "No WAV files found in the selected directory")
            return
            
        total_size_mb = sum(f.stat().st_size for f in wav_files) / (1024 * 1024)
        
        message = (f"Found {len(wav_files)} WAV files ({total_size_mb:.1f} MB)\n\n"
                  f"Output: {self.output_dir.get()}\n\n"
                  f"Settings:\n"
                  f"• CPU Cores: {self.thread_count.get()}\n"
                  f"• Compression Level: {self.compression_level.get()}\n"
                  f"• Caching: {'Enabled' if self.use_cache.get() else 'Disabled'}\n\n"
                  f"A detailed log file will be saved in the output directory.\n\n"
                  f"Proceed with conversion?")
                  
        if not messagebox.askyesno("Confirm Conversion", message):
            return
            
        # Start conversion
        self.is_converting = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        
        # Clear previous progress
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting...")
        self.status_var.set("")
        
        # Start worker thread
        self.conversion_thread = threading.Thread(target=self.conversion_worker, daemon=True)
        self.conversion_thread.start()
        
    def stop_conversion(self):
        """Stop the conversion process"""
        if self.is_converting:
            self.is_converting = False
            self.log_message("Stopping conversion...")
            self.stop_btn.config(state='disabled')
            
    def show_ffmpeg_install_dialog(self):
        """Show FFmpeg installation dialog"""
        if self.is_installing_ffmpeg:
            messagebox.showinfo("Installation in Progress", "FFmpeg installation is already in progress.")
            return
            
        # Create installation dialog
        install_dialog = tk.Toplevel(self.root)
        install_dialog.title("Install FFmpeg")
        install_dialog.geometry("480x350")
        install_dialog.resizable(False, False)
        install_dialog.grab_set()  # Make dialog modal
        
        # Center the dialog
        install_dialog.transient(self.root)
        install_dialog.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))
        
        # Dialog content
        main_frame = ttk.Frame(install_dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title and description
        ttk.Label(main_frame, text="Install FFmpeg", font=('Arial', 14, 'bold')).pack(pady=(0, 10))
        
        description = ("FFmpeg is required for audio conversion.\n\n"
                      "This will download and install FFmpeg locally for this application.\n"
                      "The installation is about 100MB and will be saved to:\n"
                      f"{self.ffmpeg_dir}\n\n"
                      "No administrator privileges required.\n"
                      "Note: If SSL certificate issues occur, the installer will use\n"
                      "secure fallback methods to complete the download.")
        
        ttk.Label(main_frame, text=description, wraplength=420, justify=tk.LEFT).pack(pady=(0, 20))
        
        # Progress frame
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.install_progress_var = tk.StringVar(value="Ready to download...")
        ttk.Label(progress_frame, textvariable=self.install_progress_var).pack()
        
        self.install_progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.install_progress_bar.pack(fill=tk.X, pady=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        self.install_btn = ttk.Button(button_frame, text="Install FFmpeg", 
                                    command=lambda: self.start_ffmpeg_installation(install_dialog))
        self.install_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.cancel_install_btn = ttk.Button(button_frame, text="Cancel", 
                                           command=install_dialog.destroy)
        self.cancel_install_btn.pack(side=tk.LEFT)
        
        # Store dialog reference
        self.install_dialog = install_dialog
        
    def start_ffmpeg_installation(self, dialog):
        """Start FFmpeg installation in background thread"""
        if self.is_installing_ffmpeg:
            return
            
        self.is_installing_ffmpeg = True
        self.install_btn.config(state='disabled')
        self.cancel_install_btn.config(text='Close', command=dialog.destroy)
        
        # Start installation thread
        self.ffmpeg_install_thread = threading.Thread(
            target=self.install_ffmpeg_worker, 
            args=(dialog,), 
            daemon=True
        )
        self.ffmpeg_install_thread.start()
        
    def install_ffmpeg_worker(self, dialog):
        """Worker thread for FFmpeg installation"""
        try:
            # Detect system architecture
            arch = platform.machine().lower()
            is_64bit = arch in ['amd64', 'x86_64']
            
            # FFmpeg download URLs (using multiple reliable sources)
            if is_64bit:
                # Try multiple download sources for better reliability
                download_urls = [
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                ]
                self.update_install_progress("Downloading FFmpeg (64-bit)...", 0)
            else:
                download_urls = [
                    "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-4.4-essentials_build.zip",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip"
                ]
                self.update_install_progress("Downloading FFmpeg (32-bit)...", 0)
            
            # Create installation directory
            self.ffmpeg_dir.mkdir(parents=True, exist_ok=True)
            
            # Try downloading from multiple sources
            zip_path = self.ffmpeg_dir / "ffmpeg.zip"
            download_successful = False
            
            for i, url in enumerate(download_urls):
                try:
                    self.update_install_progress(f"Trying download source {i+1}/{len(download_urls)}...", 5)
                    self.download_file_with_progress(url, zip_path)
                    download_successful = True
                    break
                except Exception as e:
                    self.log_message(f"Download source {i+1} failed: {e}")
                    if i == len(download_urls) - 1:  # Last attempt
                        raise Exception(f"All download sources failed. Last error: {e}")
                    continue
            
            if not download_successful:
                raise Exception("Failed to download from any source")
                
            if not self.is_installing_ffmpeg:  # Check if cancelled
                return
                
            # Extract FFmpeg
            self.update_install_progress("Extracting FFmpeg...", 80)
            self.extract_ffmpeg(zip_path)
            
            # Cleanup
            if zip_path.exists():
                zip_path.unlink()
                
            # Verify installation
            self.update_install_progress("Verifying installation...", 95)
            if self.verify_ffmpeg_installation():
                self.update_install_progress("Installation completed successfully!", 100)
                self.log_message("✓ FFmpeg installed successfully")
                
                # Update UI on main thread
                self.root.after(0, self.ffmpeg_installation_completed)
            else:
                self.update_install_progress("Installation verification failed!", 0)
                self.log_message("✗ FFmpeg installation verification failed")
                
        except Exception as e:
            self.update_install_progress(f"Installation failed: {str(e)}", 0)
            self.log_message(f"✗ FFmpeg installation failed: {e}")
        finally:
            self.is_installing_ffmpeg = False
            
    def download_file_with_progress(self, url, filepath):
        """Download file with progress updates and SSL handling"""
        def progress_hook(block_num, block_size, total_size):
            if not self.is_installing_ffmpeg:
                raise urllib.error.URLError("Download cancelled")
                
            if total_size > 0:
                downloaded = block_num * block_size
                progress = min(int((downloaded / total_size) * 70), 70)  # Up to 70%
                size_mb = total_size / (1024 * 1024)
                downloaded_mb = downloaded / (1024 * 1024)
                
                status = f"Downloading: {downloaded_mb:.1f} / {size_mb:.1f} MB"
                self.update_install_progress(status, progress)
        
        # Try downloading with proper SSL first
        try:
            # Create SSL context that verifies certificates
            ssl_context = ssl.create_default_context()
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context))
            urllib.request.install_opener(opener)
            
            urllib.request.urlretrieve(url, filepath, progress_hook)
            return
            
        except urllib.error.URLError as e:
            if "SSL" in str(e) or "CERTIFICATE" in str(e).upper():
                self.log_message("SSL certificate issue detected, trying alternative method...")
                
                # Try with unverified SSL as fallback
                try:
                    # Create unverified SSL context (less secure but works)
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    
                    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context))
                    urllib.request.install_opener(opener)
                    
                    urllib.request.urlretrieve(url, filepath, progress_hook)
                    self.log_message("Download completed using fallback SSL method")
                    return
                    
                except Exception as fallback_error:
                    raise Exception(f"SSL fallback also failed: {fallback_error}")
            else:
                # Re-raise non-SSL errors
                if "cancelled" not in str(e):
                    raise Exception(f"Download failed: {e}")
                raise Exception("Download cancelled")
                
        except Exception as e:
            if "cancelled" not in str(e):
                raise Exception(f"Download failed: {e}")
            raise Exception("Download cancelled")
            
    def extract_ffmpeg(self, zip_path):
        """Extract FFmpeg from downloaded zip file"""
        extract_dir = self.ffmpeg_dir / "temp_extract"
        extract_dir.mkdir(exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find the extracted FFmpeg folder (usually has version in name)
            extracted_folders = [f for f in extract_dir.iterdir() if f.is_dir()]
            if not extracted_folders:
                raise Exception("No folders found in extracted archive")
                
            ffmpeg_source = extracted_folders[0]
            
            # Move bin folder to our installation directory
            source_bin = ffmpeg_source / "bin"
            target_bin = self.ffmpeg_dir / "bin"
            
            if source_bin.exists():
                if target_bin.exists():
                    shutil.rmtree(target_bin)
                shutil.move(str(source_bin), str(target_bin))
            else:
                raise Exception("FFmpeg bin folder not found in archive")
                
        finally:
            # Cleanup temp extraction directory
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
                
    def verify_ffmpeg_installation(self):
        """Verify that FFmpeg was installed correctly"""
        ffmpeg_exe = self.ffmpeg_dir / "bin" / "ffmpeg.exe"
        
        if not ffmpeg_exe.exists():
            return False
            
        try:
            result = subprocess.run([str(ffmpeg_exe), '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Check for FLAC support
                flac_test = subprocess.run([str(ffmpeg_exe), '-encoders'], 
                                         capture_output=True, text=True, timeout=10)
                return 'flac' in flac_test.stdout.lower()
        except Exception:
            pass
            
        return False
        
    def update_install_progress(self, message, progress):
        """Update installation progress (thread-safe)"""
        def update_ui():
            if hasattr(self, 'install_progress_var'):
                self.install_progress_var.set(message)
            if hasattr(self, 'install_progress_bar'):
                self.install_progress_bar['value'] = progress
                
        self.root.after(0, update_ui)
        
    def ffmpeg_installation_completed(self):
        """Called when FFmpeg installation is completed successfully"""
        self.install_ffmpeg_btn.config(text="Reinstall FFmpeg")
        
        # Re-check prerequisites
        self.check_prerequisites()
        
        if hasattr(self, 'install_dialog'):
            # Update dialog buttons
            self.install_btn.config(state='normal', text='Install Complete')
            self.cancel_install_btn.config(text='Close')
            
    def open_log_file(self):
        """Open the log file in the default text editor"""
        if self.log_file_path and self.log_file_path.exists():
            try:
                os.startfile(str(self.log_file_path))
            except Exception as e:
                messagebox.showerror("Error", f"Could not open log file: {e}")
        else:
            messagebox.showwarning("Log File Not Found", 
                                 "Log file not available. Start a conversion to create a log file.")
            
    def open_output_folder(self):
        """Open the output folder in Windows Explorer"""
        output_path = Path(self.output_dir.get()) if self.output_dir.get() else None
        
        if output_path and output_path.exists():
            os.startfile(str(output_path))
        elif self.input_dir.get():
            # If output doesn't exist yet but input is selected, show where it will be created
            input_path = Path(self.input_dir.get())
            auto_output = input_path.parent / (input_path.name + "_converted")
            if auto_output.exists():
                os.startfile(str(auto_output))
            else:
                messagebox.showinfo("Output Folder", 
                                  f"Output folder will be created at:\n{auto_output}\n\n"
                                  f"(Run conversion first to create the folder)")
        else:
            messagebox.showwarning("No Directory Selected", "Please select an input directory first")

def main():
    # Set up high DPI awareness for Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    try:
        root = tk.Tk()
        app = WAVtoFLACConverter(root)
        root.mainloop()
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user.")
        # Try to log the interruption if possible
        try:
            logger = logging.getLogger(__name__)
            logger.warning("Application interrupted by user (Ctrl+C)")
        except:
            pass
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        # Try to log the error if possible
        try:
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected application error: {e}", exc_info=True)
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()