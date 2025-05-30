"""
ThemeParkAPI - Bridge module for release1.9 compatibility
This module allows the fixed code.py from release1.9 to run the current codebase
Copyright 2024 3DUPFitters LLC
"""
import sys

# Check if running on CircuitPython
is_circuitpython = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'

# Add src/lib to Python path if running on CircuitPython
if is_circuitpython:
    # For MatrixPortal S3, libraries are in src/lib
    if '/src/lib' not in sys.path:
        sys.path.append('/src/lib')
    if '/lib' not in sys.path:
        sys.path.append('/lib')  # Fallback

# Import asyncio (required for the main app)
try:
    import asyncio
except ImportError as e:
    print(f"Error importing asyncio: {e}")
    print("Path:", sys.path)
    print("Running on CircuitPython:", is_circuitpython)
    # Try to continue anyway, as it might be imported elsewhere

# Import and run the main application
# We need to go up one level to import from the root
if '..' not in sys.path:
    sys.path.append('..')

try:
    # Import the main function from theme_park_main
    from theme_park_main import main
    
    # Run the main function
    print("Starting Theme Park Waits application...")
    asyncio.run(main())
    
except ImportError as e:
    print(f"Error importing theme_park_main: {e}")
    print("Current path:", sys.path)
    print("Attempting alternative import...")
    
    # Try alternative import if the first fails
    try:
        # Add the parent directory to path
        import os
        current_dir = os.getcwd()
        print(f"Current directory: {current_dir}")
        
        # Try direct import
        import theme_park_main
        asyncio.run(theme_park_main.main())
        
    except Exception as e2:
        print(f"Failed to import theme_park_main: {e2}")
        print("Please ensure theme_park_main.py is in the root directory")
        
except KeyboardInterrupt:
    print("Application interrupted by user")
except Exception as e:
    print(f"Error running main application: {e}")
    # The error will be logged in the main module if ErrorHandler is available