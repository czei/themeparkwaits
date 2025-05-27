"""
Abstract display interface for LED matrix displays.
This interface allows for different implementations (hardware or simulated).
Copyright 2024 3DUPFitters LLC
"""
# CircuitPython doesn't have the abc module, so we'll use a regular class
# with NotImplementedError exceptions instead


class DisplayInterface:
    """Abstract base class for display implementations"""
    
    def initialize(self):
        """Initialize the display hardware or simulator"""
        pass
        
    def set_text(self, text, color=None):
        """
        Set the text to be displayed
        
        Args:
            text: The text to display
            color: The color to use for the text (RGB tuple or hex)
        """
        pass
    
    def scroll(self, frame_delay=0.04):
        """
        Scroll the text across the display
        
        Args:
            frame_delay: Time delay between scroll frames in seconds
        """
        pass
    
    def clear(self):
        """Clear the display"""
        pass
    
    def update(self):
        """Update the display to show latest changes"""
        pass
    
    def show_image(self, image, x=0, y=0):
        """
        Show an image on the display
        
        Args:
            image: The image to display
            x: X position
            y: Y position
        """
        pass
    
    def set_brightness(self, brightness):
        """
        Set the brightness of the display
        
        Args:
            brightness: Brightness value between 0.0 and 1.0
        """
        pass
    
    def set_rotation(self, rotation):
        """
        Set the rotation of the display
        
        Args:
            rotation: Rotation in degrees (0, 90, 180, 270)
        """
        pass