"""
Error handling utility for logging errors and debug information.
Copyright 2024 3DUPFitters LLC
"""
import os
import traceback

try:
    import storage
    STORAGE_AVAILABLE = True
except (ImportError, AttributeError):
    STORAGE_AVAILABLE = False

class ErrorHandler:
    """
    Centralized error handling and logging facility.
    Handles writing to log files with fallback to console output.
    """
    
    # Class-level registry to track instances by filename
    _instances = {}

    def __init__(self, file_name):
        """
        Initialize the error handler with read-only filesystem detection

        Args:
            file_name: The name of the log file
        """
        # Return existing instance if already initialized for this file
        if file_name in ErrorHandler._instances:
            # Copy properties from existing instance
            existing = ErrorHandler._instances[file_name]
            self.fileName = existing.fileName
            self.is_readonly = existing.is_readonly
            return

        # Continue with normal initialization for new instance
        self.fileName = file_name
        # Start with the assumption that the filesystem is read-only
        # We'll only set it to writable if we can successfully write to it
        self.is_readonly = True

        # First check if we can directly detect read-only status via storage module
        if STORAGE_AVAILABLE:
            try:
                # Get mount location
                mount_path = '/'
                try:
                    # Try to get the mount path for the file's directory
                    dir_path = os.path.dirname(file_name)
                    if dir_path and os.path.exists(dir_path):
                        mount_path = dir_path
                except OSError:
                    pass
                    
                # Check if storage shows readonly
                self.is_readonly = storage.getmount(mount_path).readonly
                print(f"Filesystem read-only status from storage: {self.is_readonly}")
                
                # If storage says it's read-only, trust that and skip the write test
                if self.is_readonly:
                    print("Filesystem is read-only according to storage module")
                    print("ErrorHandler initialized - read-only filesystem")  # Exact match for test
                    # Register this instance before returning
                    ErrorHandler._instances[file_name] = self
                    return
            except (AttributeError, OSError):
                # Continue with write test if storage check fails
                print("Storage module check failed, will try write test")

        # Try to delete the error log file at startup (only if it exists and is writable)
        try:
            if self.file_exists(file_name):
                print(f"Deleting existing log file: {file_name}")
                os.remove(file_name)
        except OSError:
            # Can't delete, assume readonly
            self.is_readonly = True
            print(f"Failed to delete existing log file: {file_name}")

        # Regardless of storage module results, always verify by attempting to write
        # This is the most reliable test
        try:
            # Try to create the file
            with open(self.fileName, 'w') as file:
                file.write('')  # Try to create an empty file
            self.is_readonly = False
        except OSError as e:
            # If any error occurs during write/create, filesystem is read-only
            self.is_readonly = True
            print(f"Write test failed: {str(e)}")

        # Log system state at initialization based on final determination
        if self.is_readonly:
            print("ErrorHandler initialized - read-only filesystem")
        else:
            print("ErrorHandler initialized - writable filesystem")

        # Register this instance
        ErrorHandler._instances[file_name] = self

    @staticmethod
    def filter_non_ascii(text):
        """
        Filter out non-ASCII characters from a string
        
        Args:
            text: The text to filter
            
        Returns:
            A string with only ASCII characters
        """
        if text is None:
            return ""
        return "".join(c for c in str(text) if ord(c) < 128)

    @staticmethod
    def file_exists(file_name):
        """
        Check if a file exists
        
        Args:
            file_name: The name of the file to check
            
        Returns:
            True if the file exists, False otherwise
        """
        file_exists = True
        try:
            status = os.stat(file_name)
        except OSError:
            file_exists = False
        return file_exists

    def error(self, e, str_description):
        """
        Log an error with a description and stack trace

        Args:
            e: The exception that occurred
            str_description: A description of the error
        """
        # Handle the case where e is None (no exception but error message)
        if e is None:
            except_str = str_description
            st_str = ""
        else:
            except_str = str_description + ":" + str(e)
            try:
                st = traceback.format_exception(e)
                st_str = "stack trace:"
                for line in st:
                    st_str = st_str + line
            except Exception:
                # Fallback for cases where traceback.format_exception fails
                st_str = "stack trace unavailable"

        # Filter out non-ASCII characters to prevent UnicodeEncodeError
        filtered_except_str = self.filter_non_ascii(except_str)
        filtered_st_str = self.filter_non_ascii(st_str)

        # Always print errors to console for visibility
        print(filtered_except_str)
        if st_str:
            print(filtered_st_str)

        # Only attempt to write to file if filesystem is writable
        if not self.is_readonly:
            try:
                with open(self.fileName, 'a') as file:
                    file.write(filtered_except_str + "\n")
                    if st_str:
                        file.write(filtered_st_str + "\n")
            except OSError:
                # If write fails unexpectedly, update readonly state
                self.is_readonly = True
                # Only print this message once when we first detect a failure
                print("Filesystem detected as read-only, logs will be displayed on console only")

    def debug(self, message):
        """
        Log a debug message
        
        Args:
            message: The debug message to log
        """
        print(message)
        self.write_to_file(message)

    def write_to_file(self, message):
        """
        Write a message to the log file
        
        Args:
            message: The message to write
        """
        # Only attempt to write if filesystem is writable
        if self.is_readonly:
            # In read-only mode, we'll just print to console without error messages
            # We don't print "Error writing to log file" as that confuses users
            return
            
        try:
            # Filter out non-ASCII characters to prevent UnicodeEncodeError
            filtered_message = self.filter_non_ascii(message)
            
            with open(self.fileName, 'a') as file:
                file.write(filtered_message + "\n")
        except OSError:
            # If write fails unexpectedly, update readonly state
            self.is_readonly = True
            # Only print this message once when we first detect a failure
            print("Filesystem detected as read-only, logs will be displayed on console only")

    def info(self, message):
        """
        Log an informational message
        
        Args:
            message: The informational message to log
        """
        print(message)
        self.write_to_file(message)