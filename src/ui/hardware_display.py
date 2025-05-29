"""
Hardware display implementation for CircuitPython on MatrixPortal S3.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time

# Import CircuitPython-specific libraries
import displayio
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label

from src.ui.display_interface import DisplayInterface
from src.utils.color_utils import ColorUtils
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class MatrixDisplay(DisplayInterface):
    """
    Display implementation for MatrixPortal S3 hardware
    """
    
    def __init__(self, config=None):
        """
        Initialize the display
        
        Args:
            config: Optional configuration dictionary
        """
        self.hardware = None
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
        """Initialize the display hardware"""
        try:
            # Import here to allow for running on non-CircuitPython platforms
            from adafruit_matrixportal.matrix import Matrix
            
            # Initialize the Matrix object
            self.hardware = Matrix()
            self.font = terminalio.FONT
            
            # Set up display groups
            self.main_group = displayio.Group()
            self.hardware.display.root_group = self.main_group
            self.main_group.hidden = False

            # Configure generic scrolling message
            self.scrolling_label = Label(terminalio.FONT)
            self.scrolling_label.x = 0
            self.scrolling_label.y = 15
            self.scrolling_group = displayio.Group()
            self.scrolling_group.append(self.scrolling_label)
            self.scrolling_group.hidden = True

            # Configure Ride Times
            self.wait_time_name = Label(terminalio.FONT)
            self.wait_time_name.x = 0
            self.wait_time_name.y = 7
            self.wait_time_name.scale = 1
            self.wait_time_name_group = displayio.Group()
            self.wait_time_name_group.append(self.wait_time_name)
            self.wait_time_name_group.hidden = True

            self.wait_time = Label(terminalio.FONT)
            self.wait_time.x = 0
            self.wait_time.y = 22
            self.wait_time.scale = (2)
            self.wait_time_group = displayio.Group()
            self.wait_time_group.append(self.wait_time)
            self.wait_time_group.hidden = True

            self.closed = Label(terminalio.FONT)
            self.closed.x = 14
            self.closed.y = 22
            self.closed.scale = (1)
            self.closed.text = "Closed"
            self.closed_group = displayio.Group()
            self.closed_group.hidden = True
            self.closed_group.append(self.closed)

            # Main Splash Screen
            self.splash_line1 = Label(
                terminalio.FONT,
                text="THEME PARK")
            self.splash_line1.x = 2
            self.splash_line1.y = 7
            self.splash_line2 = Label(
                terminalio.FONT,
                text="WAITS",
                scale=2)
            self.splash_line2.x = 3
            self.splash_line2.y = 22
            self.splash_group = displayio.Group()
            self.splash_group.hidden = True
            self.splash_group.append(self.splash_line1)
            self.splash_group.append(self.splash_line2)
            self.splash_line1.color = int(ColorUtils.colors["Yellow"])
            self.splash_line2.color = int(ColorUtils.colors["Orange"])

            # Message to show when wait times are updating
            self.update_line1 = Label(
                terminalio.FONT,
                text="Wait Times")
            self.update_line1.x = 2
            self.update_line1.y = 10
            self.update_line2 = Label(
                terminalio.FONT,
                text="Powered By",
                scale=1)
            self.update_line2.x = 2
            self.update_line2.y = 22
            self.update_group = displayio.Group()
            self.update_group.hidden = True
            self.update_group.append(self.update_line1)
            self.update_group.append(self.update_line2)
            self.update_line1.color = int(ColorUtils.colors["Yellow"])
            self.update_line2.color = int(ColorUtils.colors["Yellow"])

            # Message to show when wait times are updating
            self.required_line1 = Label(
                bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
                text="QUEUE-TIMES.COM")
            self.required_line2 = Label(
                bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
                text="UPDATING NOW")
            self.required_line1.x = 3
            self.required_line1.y = 12
            self.required_line2.x = 8
            self.required_line2.y = 20
            self.required_group = displayio.Group()
            self.required_group.hidden = True
            self.required_group.append(self.required_line1)
            self.required_group.append(self.required_line2)
            self.required_line1.color = int(ColorUtils.colors["Yellow"])
            self.required_line2.color = int(ColorUtils.colors["Yellow"])

            # Centered generic messages
            self.centered_line1 = Label(terminalio.FONT, text="Test Line1")
            self.centered_line2 = Label(terminalio.FONT, text="TEST LINE2")
            self.centered_line1.x = 0
            self.centered_line1.y = 9
            self.centered_line2.x = 0
            self.centered_line2.y = 23
            self.centered_group = displayio.Group()
            self.centered_group.hidden = True
            self.centered_group.append(self.centered_line1)
            self.centered_group.append(self.centered_line2)
            
            # Queue-times attribution
            self.queue_line1 = Label(
                terminalio.FONT,
                text="Powered by")
            self.queue_line1.color = int(ColorUtils.colors["Yellow"])
            self.queue_line1.x = 0
            self.queue_line1.y = 10

            self.queue_line2 = Label(
                bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
                text="queue-times.com")
            self.queue_line2.color = int(ColorUtils.colors["Orange"])
            self.queue_line2.x = 1
            self.queue_line2.y = 25
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
                
            logger.info("Hardware display initialized successfully")
            return True
            
        except Exception as e:
            logger.error(e, "Failed to initialize hardware display")
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
        # The actual scrolling is handled in hardware auto-scroll
    
    def clear(self):
        """Clear the display"""
        self._hide_all_groups()
    
    def update(self):
        """Update the display - hardware display updates automatically"""
        if self.hardware:
            self.hardware.display.refresh(minimum_frames_per_second=0)
        return True
    
    def show_image(self, image, x=0, y=0):
        """
        Display an image on the matrix
        
        Args:
            image: PIL Image object
            x: X position
            y: Y position
        """
        try:
            # Convert PIL Image to displayio bitmap
            if hasattr(image, 'mode') and image.mode:
                import displayio
                from adafruit_imaging.bitmap import displayio_bitmap_from_pil_image
                
                # Convert to displayio bitmap
                bitmap = displayio_bitmap_from_pil_image(image)
                
                # Create a TileGrid from the bitmap
                tile_grid = displayio.TileGrid(bitmap, pixel_shader=displayio.ColorConverter())
                
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
        if self.hardware:
            try:
                brightness = min(max(brightness, 0.0), 1.0)
                # MatrixPortal S3 brightness is 0-1.0
                self.hardware.display.brightness = brightness
            except Exception as e:
                logger.error(e, "Failed to set brightness")
    
    def set_rotation(self, rotation):
        """
        Set display rotation
        
        Args:
            rotation: Rotation in degrees (0, 90, 180, 270)
        """
        if self.hardware:
            try:
                # Map rotation degrees to displayio constants
                rotation_map = {
                    0: 0,
                    90: 1,
                    180: 2,
                    270: 3
                }
                if rotation in rotation_map:
                    self.hardware.display.rotation = rotation_map[rotation]
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
            self.wait_time_name.color = int(ColorUtils.scale_color(settings.settings.get("ride_name_color", ColorUtils.colors["Blue"]), scale))
            self.wait_time.color = int(ColorUtils.scale_color(settings.settings.get("ride_wait_time_color", ColorUtils.colors["Old Lace"]), scale))
            self.closed.color = int(ColorUtils.scale_color(settings.settings.get("ride_wait_time_color", ColorUtils.colors["Old Lace"]), scale))
            self.scrolling_label.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.splash_line1.color = int(ColorUtils.scale_color(ColorUtils.colors["Yellow"], scale))
            self.splash_line2.color = int(ColorUtils.scale_color(ColorUtils.colors["Orange"], scale))
            self.update_line1.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.update_line2.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.required_line1.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.required_line2.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.centered_line1.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
            self.centered_line2.color = int(ColorUtils.scale_color(settings.settings.get("default_color", ColorUtils.colors["Yellow"]), scale))
        except Exception as e:
            logger.error(e, "Error setting colors")
    
    # Additional display-specific methods
    
    async def show_splash(self, duration=4, reveal_style=False):
        """
        Show the splash screen
        
        Args:
            duration: Duration to show in seconds
            reveal_style: If True, use reveal animation instead of static display
        """
        logger.debug(f"HardwareDisplay.show_splash called with duration={duration}, reveal_style={reveal_style}")
        self._hide_all_groups()
        
        if reveal_style:
            logger.debug("Using reveal animation style")
            await self._show_reveal_splash(duration)
        else:
            logger.debug(f"Showing the splash screen for {duration} seconds")
            self.splash_group.hidden = False
            await asyncio.sleep(duration)
            self.splash_group.hidden = True
    
    async def _show_reveal_splash(self, duration=4):
        """
        Show the splash screen with reveal animation style
        
        Args:
            duration: Duration to show in seconds
        """
        try:
            import random
            import time
            
            logger.debug("Starting reveal-style splash animation")
            
            # Create a bitmap for direct pixel manipulation
            bitmap = displayio.Bitmap(64, 32, 2)
            palette = displayio.Palette(2)
            palette[0] = 0x000000  # Black
            palette[1] = 0xFFFF00  # Yellow
            
            # Create TileGrid and Group for reveal animation
            tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
            reveal_group = displayio.Group()
            reveal_group.append(tile_grid)
            self.main_group.append(reveal_group)
            
            # Get target pixels for THEME PARK WAITS
            target_pixels = self._get_theme_park_waits_pixels()
            target_set = set(target_pixels)
            
            # Start with RANDOM LEDs turned on (50% chance)
            for x in range(64):
                for y in range(32):
                    if random.random() < 0.5:
                        bitmap[x, y] = 1
                    else:
                        bitmap[x, y] = 0
            
            # Categorize LEDs for reveal animation
            incorrect_on = []  # LEDs on but shouldn't be
            missing_text = []  # Text LEDs off but should be on
            
            for x in range(64):
                for y in range(32):
                    pixel = (x, y)
                    is_on = bitmap[x, y] == 1
                    is_text = pixel in target_set
                    
                    if is_on and not is_text:
                        incorrect_on.append(pixel)
                    elif not is_on and is_text:
                        missing_text.append(pixel)
            
            # Simple shuffle for CircuitPython compatibility
            def simple_shuffle(lst):
                for i in range(len(lst)):
                    j = random.randint(0, len(lst) - 1)
                    lst[i], lst[j] = lst[j], lst[i]
            
            simple_shuffle(incorrect_on)
            simple_shuffle(missing_text)
            
            logger.debug(f"Initial state: {len(incorrect_on)} incorrect on, {len(missing_text)} text missing")
            
            # Reveal animation loop
            start_time = time.monotonic()
            last_update = time.monotonic()
            animation_complete = False
            
            while not animation_complete and (time.monotonic() - start_time) < duration:
                current_time = time.monotonic()
                
                # Update every 50ms for fast animation
                if current_time - last_update < 0.05:
                    await asyncio.sleep(0.01)
                    continue
                
                last_update = current_time
                
                # Turn off incorrect LEDs (fast rate)
                if len(incorrect_on) > 0:
                    num_to_turn_off = min(5, len(incorrect_on))
                    for _ in range(num_to_turn_off):
                        pixel = incorrect_on.pop()
                        bitmap[pixel[0], pixel[1]] = 0
                
                # Turn on missing text LEDs (fast rate)
                if len(missing_text) > 0:
                    num_to_turn_on = min(3, len(missing_text))
                    for _ in range(num_to_turn_on):
                        pixel = missing_text.pop()
                        bitmap[pixel[0], pixel[1]] = 1
                
                # Check completion
                if len(incorrect_on) == 0 and len(missing_text) == 0:
                    animation_complete = True
                    elapsed = current_time - start_time
                    logger.debug(f"THEME PARK WAITS revealed in {elapsed:.1f} seconds!")
                
                await asyncio.sleep(0.01)
            
            # Keep final result visible for remaining duration
            remaining_time = duration - (time.monotonic() - start_time)
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # Clean up - remove reveal group
            self.main_group.remove(reveal_group)
            
        except Exception as e:
            logger.error(e, "Error in reveal splash animation")
            # Fallback to regular splash
            self.splash_group.hidden = False
            await asyncio.sleep(duration)
            self.splash_group.hidden = True
    
    def _get_theme_park_waits_pixels(self):
        """Return list of (x, y) coordinates for THEME PARK WAITS text pixels."""
        pixels = []
        
        # THEME PARK - First line (8 pixels tall)
        # T (x=4, y=3)
        for x in range(4, 9): pixels.append((x, 3))
        for y in range(4, 11): pixels.append((6, y))
        
        # H (x=10, y=3)
        for y in range(3, 11): pixels.append((10, y))
        for y in range(3, 11): pixels.append((14, y))
        for x in range(11, 14): pixels.append((x, 6))
        
        # E (x=16, y=3)
        for y in range(3, 11): pixels.append((16, y))
        for x in range(16, 20): pixels.append((x, 3))
        for x in range(16, 19): pixels.append((x, 6))
        for x in range(16, 20): pixels.append((x, 10))
        
        # M (x=22, y=3)
        for y in range(3, 11): pixels.append((22, y))
        for y in range(3, 11): pixels.append((27, y))
        pixels.append((23, 4))
        pixels.append((24, 5))
        pixels.append((25, 5))
        pixels.append((26, 4))
        
        # E (x=29, y=3)
        for y in range(3, 11): pixels.append((29, y))
        for x in range(29, 33): pixels.append((x, 3))
        for x in range(29, 32): pixels.append((x, 6))
        for x in range(29, 33): pixels.append((x, 10))
        
        # P (x=36, y=3)
        for y in range(3, 11): pixels.append((36, y))
        for x in range(36, 40): pixels.append((x, 3))
        for x in range(36, 40): pixels.append((x, 6))
        pixels.append((39, 4))
        pixels.append((39, 5))
        
        # A (x=42, y=3)
        for y in range(4, 11): pixels.append((42, y))
        for y in range(4, 11): pixels.append((46, y))
        for x in range(43, 46): pixels.append((x, 3))
        for x in range(42, 47): pixels.append((x, 6))
        
        # R (x=48, y=3)
        for y in range(3, 11): pixels.append((48, y))
        for x in range(48, 52): pixels.append((x, 3))
        for x in range(48, 52): pixels.append((x, 6))
        pixels.append((51, 4))
        pixels.append((51, 5))
        pixels.append((50, 7))
        pixels.append((51, 8))
        pixels.append((52, 9))
        pixels.append((53, 10))
        
        # K (x=54, y=3)
        for y in range(3, 11): pixels.append((54, y))
        pixels.append((57, 3))
        pixels.append((56, 4))
        pixels.append((55, 5))
        pixels.append((55, 6))
        pixels.append((56, 7))
        pixels.append((57, 8))
        pixels.append((58, 9))
        pixels.append((59, 10))
        
        # WAITS - Second line (16 pixels tall, moved right by 3 LEDs)
        # W (x=5, y=15)
        for y in range(15, 31):
            pixels.append((5, y))
            pixels.append((6, y))
        for y in range(15, 31):
            pixels.append((13, y))
            pixels.append((14, y))
        for x in range(7, 9): pixels.append((x, 28))
        for x in range(7, 9): pixels.append((x, 27))
        for x in range(11, 13): pixels.append((x, 28))
        for x in range(11, 13): pixels.append((x, 27))
        for y in range(23, 27): pixels.append((9, y))
        for y in range(23, 27): pixels.append((10, y))
        
        # A (x=16, y=15)
        for y in range(17, 31): pixels.append((16, y))
        for y in range(17, 31): pixels.append((17, y))
        for y in range(17, 31): pixels.append((24, y))
        for y in range(17, 31): pixels.append((25, y))
        for x in range(18, 24): pixels.append((x, 15))
        for x in range(18, 24): pixels.append((x, 16))
        for x in range(16, 26): pixels.append((x, 22))
        for x in range(16, 26): pixels.append((x, 23))
        
        # I (x=27, y=15)
        for x in range(27, 37): pixels.append((x, 15))
        for x in range(27, 37): pixels.append((x, 16))
        for x in range(27, 37): pixels.append((x, 29))
        for x in range(27, 37): pixels.append((x, 30))
        for y in range(15, 31): pixels.append((31, y))
        for y in range(15, 31): pixels.append((32, y))
        
        # T (x=38, y=15)
        for x in range(38, 48): pixels.append((x, 15))
        for x in range(38, 48): pixels.append((x, 16))
        for y in range(15, 31): pixels.append((42, y))
        for y in range(15, 31): pixels.append((43, y))
        
        # S (x=49, y=15)
        for x in range(49, 59): pixels.append((x, 15))
        for x in range(49, 59): pixels.append((x, 16))
        for y in range(17, 22): pixels.append((49, y))
        for y in range(17, 22): pixels.append((50, y))
        for x in range(49, 59): pixels.append((x, 22))
        for x in range(49, 59): pixels.append((x, 23))
        for y in range(24, 29): pixels.append((57, y))
        for y in range(24, 29): pixels.append((58, y))
        for x in range(49, 59): pixels.append((x, 29))
        for x in range(49, 59): pixels.append((x, 30))
        
        return pixels
        
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
            line.x = self.hardware.display.width
            return False
        return True
        
    def _center_text(self, text_label):
        """
        Center a text label horizontally
        
        Args:
            text_label: The label to center
        """
        width = self.hardware.display.width
        label_width = text_label.bounding_box[2]
        padding = int((width - label_width) / 2)
        text_label.x = max(0, padding)