"""
PyLEDSimulator display implementation for Theme Park Waits.
Uses the PyLEDSimulator library to provide a more accurate simulation
of the MatrixPortal S3 hardware.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time
import sys
import os

# Add PyLEDSimulator to path if needed
pyledsim_path = os.path.join(os.path.dirname(__file__), '..', '..', 'PyLEDSimulator')
if os.path.exists(pyledsim_path) and pyledsim_path not in sys.path:
    sys.path.insert(0, pyledsim_path)

from pyledsimulator.devices.matrixportal_s3 import MatrixPortalS3
from pyledsimulator import displayio
from pyledsimulator.adafruit_bitmap_font import bitmap_font
from pyledsimulator.adafruit_display_text.label import Label
from pyledsimulator.terminalio import FONT as terminalio_FONT

from src.ui.display_interface import DisplayInterface
from src.ui.reveal_animation import show_reveal_splash
from src.utils.color_utils import ColorUtils
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class PyLEDSimulatorDisplay(DisplayInterface):
    """
    Display implementation using PyLEDSimulator for development
    """
    
    def __init__(self, config=None):
        """
        Initialize the PyLEDSimulator display
        
        Args:
            config: Optional configuration dictionary
        """
        self.device = None
        self.matrix = None
        self.display = None
        self.font = None
        self.settings_manager = config.get('settings_manager') if config else None
        
        # For scrolling
        self.scroll_position = 0
        self.scroll_delay = 0.04
        
        # Display groups
        self.main_group = None
        self.scrolling_group = None
        self.wait_time_name_group = None
        self.wait_time_group = None
        self.closed_group = None
        self.splash_group = None
        self.update_group = None
        self.required_group = None
        self.centered_group = None
        self.queue_group = None
        
        # Labels
        self.scrolling_label = None
        self.wait_time_name = None
        self.wait_time = None
        self.closed = None
        self.splash_line1 = None
        self.splash_line2 = None
        self.update_line1 = None
        self.update_line2 = None
        self.required_line1 = None
        self.required_line2 = None
        self.centered_line1 = None
        self.centered_line2 = None
        self.queue_line1 = None
        self.queue_line2 = None
        
    def initialize(self):
        """Initialize the PyLEDSimulator display"""
        try:
            logger.info("Initializing PyLEDSimulator display")
            
            # Create MatrixPortal S3 device
            self.device = MatrixPortalS3(width=64, height=32)
            self.device.initialize()
            
            # Get references to the display components
            self.matrix = self.device.matrix
            self.display = self.device.display
            self.font = terminalio_FONT
            
            # Set up display groups (similar to hardware_display.py)
            self.main_group = displayio.Group()
            self.display.root_group = self.main_group
            
            # Configure generic scrolling message
            self.scrolling_label = Label(terminalio_FONT)
            self.scrolling_label.x = 0
            self.scrolling_label.y = 16
            self.scrolling_group = displayio.Group()
            self.scrolling_group.append(self.scrolling_label)
            self.scrolling_group.hidden = True

            # Configure Ride Times
            self.wait_time_name = Label(terminalio_FONT)
            self.wait_time_name.x = 0
            self.wait_time_name.y = 2
            self.wait_time_name.scale = 1
            self.wait_time_name_group = displayio.Group()
            self.wait_time_name_group.append(self.wait_time_name)
            self.wait_time_name_group.hidden = True

            self.wait_time = Label(terminalio_FONT)
            self.wait_time.x = 0
            self.wait_time.y = 12
            self.wait_time.scale = 2
            self.wait_time_group = displayio.Group()
            self.wait_time_group.append(self.wait_time)
            self.wait_time_group.hidden = True

            self.closed = Label(terminalio_FONT)
            self.closed.x = 14
            self.closed.y = 14
            self.closed.scale = 1
            self.closed.text = "Closed"
            self.closed_group = displayio.Group()
            self.closed_group.hidden = True
            self.closed_group.append(self.closed)

            # Main Splash Screen
            self.splash_line1 = Label(
                terminalio_FONT,
                text="THEME PARK"
            )
            self.splash_line1.x = 2
            self.splash_line1.y = 7
            self.splash_line2 = Label(
                terminalio_FONT,
                text="WAITS",
                scale=2)
            self.splash_line2.x = 3
            self.splash_line2.y = 12
            self.splash_group = displayio.Group()
            self.splash_group.hidden = True
            self.splash_group.append(self.splash_line1)
            self.splash_group.append(self.splash_line2)
            self.splash_line1.color = int(ColorUtils.colors["Yellow"], 16)
            self.splash_line2.color = int(ColorUtils.colors["Orange"], 16)

            # Message to show when wait times are updating
            self.update_line1 = Label(
                terminalio_FONT,
                text="Wait Times"
            )
            self.update_line1.x = 2
            self.update_line1.y = 2
            self.update_line2 = Label(
                terminalio_FONT,
                text="Powered By",
                scale=1)
            self.update_line2.x = 2
            self.update_line2.y = 12
            self.update_group = displayio.Group()
            self.update_group.hidden = True
            self.update_group.append(self.update_line1)
            self.update_group.append(self.update_line2)
            self.update_line1.color = int(ColorUtils.colors["Yellow"], 16)
            self.update_line2.color = int(ColorUtils.colors["Yellow"], 16)

            # Required attribution message
            try:
                # Try loading the small font
                small_font = bitmap_font.load_font("src/fonts/tom-thumb.bdf")
            except:
                # Fallback to terminal font if small font not available
                small_font = terminalio_FONT
                
            self.required_line1 = Label(
                small_font,
                text="QUEUE-TIMES.COM"
            )
            self.required_line2 = Label(
                small_font,
                text="UPDATING NOW"
            )
            self.required_line1.x = 3
            self.required_line1.y = 4
            self.required_line2.x = 8
            self.required_line2.y = 10
            self.required_group = displayio.Group()
            self.required_group.hidden = True
            self.required_group.append(self.required_line1)
            self.required_group.append(self.required_line2)
            self.required_line1.color = int(ColorUtils.colors["Yellow"], 16)
            self.required_line2.color = int(ColorUtils.colors["Yellow"], 16)

            # Centered generic messages
            self.centered_line1 = Label(terminalio_FONT, text="Test Line1")
            self.centered_line2 = Label(terminalio_FONT, text="TEST LINE2")
            self.centered_line1.x = 0
            self.centered_line1.y = 1
            self.centered_line2.x = 0
            self.centered_line2.y = 13
            self.centered_group = displayio.Group()
            self.centered_group.hidden = True
            self.centered_group.append(self.centered_line1)
            self.centered_group.append(self.centered_line2)
            
            # Queue-times attribution
            self.queue_line1 = Label(
                terminalio_FONT,
                text="Powered by"
            )
            self.queue_line1.color = int(ColorUtils.colors["Yellow"], 16)
            self.queue_line1.x = 0
            self.queue_line1.y = 2

            self.queue_line2 = Label(
                small_font,
                text="queue-times.com"
            )
            self.queue_line2.color = int(ColorUtils.colors["Orange"], 16)
            self.queue_line2.x = 1
            self.queue_line2.y = 15
            self.queue_group = displayio.Group()
            self.queue_group.hidden = True
            self.queue_group.append(self.queue_line1)
            self.queue_group.append(self.queue_line2)

            # Add all groups to the main group
            self.main_group.append(self.scrolling_group)
            self.main_group.append(self.wait_time_name_group)
            self.main_group.append(self.wait_time_group)
            self.main_group.append(self.closed_group)
            self.main_group.append(self.splash_group)
            self.main_group.append(self.update_group)
            self.main_group.append(self.required_group)
            self.main_group.append(self.centered_group)
            self.main_group.append(self.queue_group)
            
            # Set colors if settings manager exists
            if self.settings_manager:
                self.set_colors(self.settings_manager)
                
            # Initialize pygame and the matrix surface
            if hasattr(self.matrix, 'initialize_surface'):
                self.matrix.initialize_surface()
                
            logger.info("PyLEDSimulator display initialized successfully")
            return True
            
        except Exception as e:
            logger.error(e, "Failed to initialize PyLEDSimulator display")
            return False
    
    def set_text(self, text, color=None):
        """
        Set text to display on the matrix
        
        Args:
            text: Text to display
            color: Optional color (default: white)
        """
        if not self.scrolling_label:
            return
            
        self.scrolling_label.text = text
        if color:
            self.scrolling_label.color = int(color)
        self.scrolling_group.hidden = False
    
    def scroll(self, frame_delay=0.04):
        """
        Scroll the current text
        
        Args:
            frame_delay: Delay between frames in seconds
        """
        self.scroll_delay = frame_delay
    
    def clear(self):
        """Clear the display"""
        self._hide_all_groups()
    
    def update(self):
        """Update the display"""
        if self.display:
            # Handle pygame events to keep window responsive
            import pygame
            
            # Check if pygame is initialized
            if not pygame.get_init():
                # Skip pygame operations if not initialized
                self.display.refresh(minimum_frames_per_second=0)
                return True
            
            # Check if display mode has been set (window created)
            if pygame.display.get_surface() is None:
                # Window not created yet, just refresh the display
                self.display.refresh(minimum_frames_per_second=0)
                return True
                
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return False
            
            # Update the display
            self.display.refresh(minimum_frames_per_second=0)
            
            # Update the pygame display
            if hasattr(self.matrix, 'render'):
                self.matrix.render()
            pygame.display.flip()
            
        return True
    
    async def run_async(self):
        """Run the display in an async loop"""
        # Initialize pygame if not already done
        import pygame
        if not pygame.get_init():
            pygame.init()
            
        # Create the window
        screen = pygame.display.set_mode((self.matrix.surface_width, self.matrix.surface_height))
        pygame.display.set_caption("Theme Park Waits - PyLEDSimulator")
        
        # Main display loop
        clock = pygame.time.Clock()
        running = True
        
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    # Exit the entire application
                    import sys
                    pygame.quit()
                    sys.exit(0)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        # Exit the entire application
                        import sys
                        pygame.quit()
                        sys.exit(0)
            
            # Update the display
            if self.display and self.display.root_group:
                self.display.refresh(minimum_frames_per_second=0)
            
            # Render to screen
            if hasattr(self.matrix, 'render'):
                self.matrix.render()
                # Get the rendered surface and blit to screen
                if hasattr(self.matrix, 'surface'):
                    screen.blit(self.matrix.surface, (0, 0))
            
            pygame.display.flip()
            clock.tick(60)  # 60 FPS
            
            # Yield control to allow other async tasks to run
            await asyncio.sleep(0.001)
        
        # Clean up
        pygame.quit()
    
    def show_image(self, image, x=0, y=0):
        """
        Display an image on the matrix
        
        Args:
            image: PIL Image object
            x: X position
            y: Y position
        """
        try:
            # PyLEDSimulator supports PIL images directly
            if hasattr(image, 'mode') and image.mode:
                # Convert to displayio bitmap
                bitmap = displayio.Bitmap(image.width, image.height, 256)
                palette = displayio.Palette(256)
                
                # Convert image to RGB if needed
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Copy pixels
                for y_pos in range(image.height):
                    for x_pos in range(image.width):
                        pixel = image.getpixel((x_pos, y_pos))
                        color = (pixel[0] << 16) | (pixel[1] << 8) | pixel[2]
                        # Find or add color to palette
                        color_index = 0
                        for i in range(len(palette)):
                            if palette[i] == color:
                                color_index = i
                                break
                        else:
                            if len(palette) < 256:
                                palette[len(palette)] = color
                                color_index = len(palette) - 1
                        bitmap[x_pos, y_pos] = color_index
                
                # Create TileGrid
                tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
                
                # Create a group and add the TileGrid
                image_group = displayio.Group()
                image_group.append(tile_grid)
                
                # Position the image
                image_group.x = x
                image_group.y = y
                
                # Clear the display
                self._hide_all_groups()
                
                # Add the image group to the main group
                self.main_group.append(image_group)
                
                # Update the display
                self.update()
                
        except Exception as e:
            logger.error(e, "Error displaying image")
    
    def set_brightness(self, brightness):
        """
        Set display brightness
        
        Args:
            brightness: Brightness value (0.0-1.0)
        """
        if self.display:
            try:
                brightness = min(max(brightness, 0.0), 1.0)
                self.display.brightness = brightness
            except Exception as e:
                logger.error(e, "Failed to set brightness")
    
    def set_rotation(self, rotation):
        """
        Set display rotation
        
        Args:
            rotation: Rotation in degrees (0, 90, 180, 270)
        """
        if self.display:
            try:
                # Map rotation degrees to displayio constants
                rotation_map = {
                    0: 0,
                    90: 1,
                    180: 2,
                    270: 3
                }
                if rotation in rotation_map:
                    self.display.rotation = rotation_map[rotation]
            except Exception as e:
                logger.error(e, "Failed to set rotation")
    
    def _hide_all_groups(self):
        """Hide all display groups"""
        groups = [
            self.scrolling_group, 
            self.wait_time_name_group,
            self.wait_time_group, 
            self.closed_group,
            self.splash_group, 
            self.update_group,
            self.required_group, 
            self.centered_group,
            self.queue_group
        ]
        
        for group in groups:
            if group:
                group.hidden = True
    
    def set_colors(self, settings):
        """
        Set colors from settings
        
        Args:
            settings: The settings manager
        """
        if not hasattr(settings, 'settings'):
            return
            
        try:
            scale = float(settings.settings.get("brightness_scale", "0.5"))
            
            # Helper function to convert color value to int
            def color_to_int(color_value):
                if isinstance(color_value, str):
                    return int(color_value, 16)
                return int(color_value)
            
            self.wait_time_name.color = color_to_int(ColorUtils.scale_color(settings.settings.get("ride_name_color", ColorUtils.colors["Blue"]), scale))
            self.wait_time.color = color_to_int(ColorUtils.scale_color(settings.settings.get("ride_wait_time_color", ColorUtils.colors["Old Lace"]), scale))
            self.closed.color = color_to_int(ColorUtils.scale_color(settings.settings.get("ride_wait_time_color", ColorUtils.colors["Old Lace"]), scale))
            self.scrolling_label.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.splash_line1.color = color_to_int(ColorUtils.scale_color(ColorUtils.colors["Yellow"], scale))
            self.splash_line2.color = color_to_int(ColorUtils.scale_color(ColorUtils.colors["Orange"], scale))
            self.update_line1.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.update_line2.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.required_line1.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.required_line2.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.centered_line1.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.centered_line2.color = color_to_int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
        except Exception as e:
            logger.error(e, "Error setting colors")
    
    # Additional display-specific methods
    
    async def show_splash(self, duration=8, reveal_style=False):
        """
        Show the splash screen
        
        Args:
            duration: Duration to show in seconds
            reveal_style: If True, use reveal animation
        """
        logger.debug(f"PyLEDSimulator.show_splash called with duration={duration}, reveal_style={reveal_style}")
        self._hide_all_groups()
        
        if reveal_style:
            logger.debug("Using reveal animation style")
            await show_reveal_splash(self.main_group)
        else:
            logger.debug(f"Showing the splash screen for {duration} seconds")
            self.splash_group.hidden = False
            await asyncio.sleep(duration)
            self.splash_group.hidden = True
    
    
    async def show_ride_name(self, ride_name):
        """
        Show a ride name
        
        Args:
            ride_name: The name of the ride
        """
        await asyncio.sleep(.5)
        self.wait_time_name.text = ride_name
        self.wait_time_name_group.hidden = False
        
        # Scroll the text if needed
        while self._scroll_x(self.wait_time_name):
            await asyncio.sleep(self.scroll_delay)
            self.update()
            
        await asyncio.sleep(1)
        self.wait_time.text = ""
        self.wait_time_name.text = ""
        self.wait_time_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.closed_group.hidden = True
        
    async def show_ride_closed(self, dummy):
        """
        Show that a ride is closed
        
        Args:
            dummy: Unused parameter for API consistency
        """
        self.closed_group.hidden = False
        
    async def show_ride_wait_time(self, ride_wait_time):
        """
        Show a ride wait time
        
        Args:
            ride_wait_time: The wait time to display
        """
        self.wait_time.text = ride_wait_time
        self._center_text(self.wait_time)
        self.wait_time_group.hidden = False
        
    async def show_scroll_message(self, message):
        """
        Show a scrolling message
        
        Args:
            message: The message to scroll
        """
        logger.debug(f"Scrolling message: {message}")
        self._hide_all_groups()
        self.scrolling_label.text = message
        self.scrolling_group.hidden = False
        await asyncio.sleep(.5)
        
        # Scroll until complete
        while self._scroll_x(self.scrolling_label):
            await asyncio.sleep(self.scroll_delay)
            self.update()
            
        self.scrolling_group.hidden = True
        
    def _scroll_x(self, line):
        """
        Scroll a line horizontally
        
        Args:
            line: The line to scroll
            
        Returns:
            True if still scrolling, False if done
        """
        line.x = line.x - 1
        line_width = line.bounding_box[2]
        if line.x < -line_width:
            line.x = self.display.width
            return False
        return True
        
    def _center_text(self, text_label):
        """
        Center a text label horizontally
        
        Args:
            text_label: The label to center
        """
        width = self.display.width
        
        # Get the bounding box and account for scale
        bounding_box = text_label.bounding_box
        if bounding_box:
            # The bounding box width needs to be multiplied by scale
            label_width = bounding_box[2] * text_label.scale
            
            # Calculate padding to center the text
            padding = int((width - label_width) / 2)
            text_label.x = max(0, padding)
            
            # Debug logging for 3-digit wait times
            if len(text_label.text) >= 3:
                logger.debug(f"Centering text '{text_label.text}': width={width}, label_width={label_width}, scale={text_label.scale}, padding={padding}")