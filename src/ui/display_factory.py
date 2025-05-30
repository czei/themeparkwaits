"""
Factory for creating the appropriate display implementation.
Detects the platform and returns the correct display object.
Copyright 2024 3DUPFitters LLC
"""
import sys
import os

# Check if running on CircuitPython
is_circuitpython = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'

# Only import platform if not running on CircuitPython
if not is_circuitpython:
    import platform
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


def is_circuitpython():
    """
    Check if running on CircuitPython
    
    Returns:
        True if running on CircuitPython, False otherwise
    """
    return hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'


def is_dev_mode():
    """
    Check if running in development mode
    
    Returns:
        True if --dev flag is present in command line args
    """
    return '--dev' in sys.argv


def create_display(config=None):
    """
    Factory function to create the appropriate display
    
    Args:
        config: Optional configuration dictionary
    
    Returns:
        Display implementation appropriate for the current platform
    """
    # Force simulator if --dev flag is present
    if is_dev_mode():
        logger.info("Development mode detected, using simulated display")
        from src.ui.simulator_display import SimulatedLEDMatrix
        return SimulatedLEDMatrix(config)
    
    # Check if running on CircuitPython
    if is_circuitpython():
        logger.info("CircuitPython detected, using hardware display")
        # Import the real hardware display
        try:
            # Import the MatrixDisplay from hardware_display.py instead of Display from display_impl.py
            from src.ui.hardware_display import MatrixDisplay
            return MatrixDisplay(config)
        except ImportError as e:
            logger.error(e, "Error importing hardware display")
            # On CircuitPython, don't try to fall back to simulator 
            # since pygame is not available
            # Instead, provide a minimal display implementation that logs messages
            from src.ui.display_base import Display
            return Display(config)
    
    # Not on CircuitPython, use simulator
    if not is_circuitpython and 'platform' in sys.modules:
        logger.info(f"Desktop platform detected ({platform.system()}), using simulated display")
    else:
        logger.info("Desktop platform detected, using simulated display")
    from src.ui.simulator_display import SimulatedLEDMatrix
    return SimulatedLEDMatrix(config)