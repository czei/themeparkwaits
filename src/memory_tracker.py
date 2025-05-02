"""
Memory Tracker for CircuitPython applications.
Monitors memory usage and logs warnings when memory drops below 50% of initial free memory.
"""
import gc
import time
from src.ErrorHandler import ErrorHandler

class MemoryTracker:
    """
    Tracks memory usage in a CircuitPython application.
    
    Features:
    - Records initial free memory at startup
    - Monitors memory after garbage collection runs
    - Logs a warning when free memory drops below 50% of initial value
    - Only logs one warning to avoid filling error log
    """
    def __init__(self, error_log_filename="error_log"):
        """
        Initialize the memory tracker.
        
        Args:
            error_log_filename: The filename for the error log
        """
        # Force garbage collection before starting
        gc.collect()
        
        # Record initial free memory
        self.initial_free_memory = gc.mem_free()
        self.warning_threshold = self.initial_free_memory * 0.5
        self.warning_logged = False
        
        # Set up error logging
        self.error_handler = ErrorHandler(error_log_filename)
        self.error_handler.debug(f"MemoryTracker initialized. Initial free memory: {self.initial_free_memory} bytes")
        
        # Enable garbage collection
        gc.enable()
        
    def collect_and_check(self):
        """
        Manually trigger garbage collection and check memory status.
        
        Returns:
            dict: Memory statistics including free memory, percent used, warning status
        """
        # Run garbage collection
        start_time = time.monotonic()
        gc.collect()
        end_time = time.monotonic()
        
        # Get current memory usage
        current_free = gc.mem_free()
        percent_free = (current_free / self.initial_free_memory) * 100
        
        # Log if GC took too long
        elapsed_time = end_time - start_time
        if elapsed_time > 1.0:
            self.error_handler.debug(f"Garbage collection took {elapsed_time:.2f} seconds")
        
        # Check if we're below the warning threshold and haven't logged a warning yet
        if current_free < self.warning_threshold and not self.warning_logged:
            self.warning_logged = True
            warning_msg = f"MEMORY WARNING: Free memory at {percent_free:.1f}% of initial ({current_free} bytes / {self.initial_free_memory} bytes)"
            self.error_handler.error(Exception("Low memory condition"), warning_msg)
            
        # Return memory stats
        return {
            "initial_free": self.initial_free_memory,
            "current_free": current_free,
            "percent_free": percent_free,
            "warning_logged": self.warning_logged
        }
    
    def get_memory_status(self):
        """
        Get current memory status without running garbage collection.
        
        Returns:
            dict: Memory statistics including free memory and percent used
        """
        current_free = gc.mem_free()
        percent_free = (current_free / self.initial_free_memory) * 100
        
        return {
            "initial_free": self.initial_free_memory,
            "current_free": current_free,
            "percent_free": percent_free,
            "warning_logged": self.warning_logged
        }