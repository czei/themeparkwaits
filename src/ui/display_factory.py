"""
Factory for creating the appropriate display implementation.
Uses the unified display that works on both CircuitPython and PyLEDSimulator.
Copyright 2024 3DUPFitters LLC
"""
import sys
import os
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


def use_simple_simulator():
    """
    Check if simple simulator should be used instead of PyLEDSimulator
    
    Returns:
        True if --simple-sim flag is present
    """
    return '--simple-sim' in sys.argv


def create_display(config=None):
    """
    Factory function to create the appropriate display
    
    Args:
        config: Optional configuration dictionary
    
    Returns:
        Display implementation appropriate for the current platform
    """
    # Check for simple simulator override
    if is_dev_mode() and use_simple_simulator():
        logger.info("Development mode with --simple-sim flag detected, using simple simulator")
        try:
            from src.ui.simulator_display import SimulatedLEDMatrix
            return SimulatedLEDMatrix(config)
        except ImportError as e:
            logger.error(e, "Error importing simple simulator")
            # Fall through to unified display
    
    # Use unified display for both CircuitPython and PyLEDSimulator
    if is_circuitpython():
        logger.info("CircuitPython detected, using unified display with hardware backend")
    else:
        logger.info("Desktop platform detected, using unified display with PyLEDSimulator backend")
    
    try:
        from src.ui.unified_display import UnifiedDisplay
        return UnifiedDisplay(config)
    except ImportError as e:
        logger.error(e, "Error importing unified display")
        
        # Fallback to legacy displays as last resort
        if is_circuitpython():
            try:
                from src.ui.hardware_display import MatrixDisplay
                logger.info("Falling back to legacy hardware display")
                return MatrixDisplay(config)
            except ImportError:
                logger.error("Legacy hardware display also failed")
                # On CircuitPython, don't try simulator since pygame is not available
                from src.ui.display_base import Display
                return Display(config)
        else:
            try:
                from src.ui.pyledsimulator_display import PyLEDSimulatorDisplay
                logger.info("Falling back to legacy PyLEDSimulator display")
                return PyLEDSimulatorDisplay(config)
            except ImportError:
                logger.info("PyLEDSimulator not available, using simple simulator")
                from src.ui.simulator_display import SimulatedLEDMatrix
                return SimulatedLEDMatrix(config)