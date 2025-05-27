"""
Simulated LED Matrix display for development on desktop platforms.
Uses Pygame to render a visual representation of the LED matrix.
Copyright 2024 3DUPFitters LLC
"""
import pygame
import time
import sys
import os
import asyncio
from PIL import Image, ImageDraw, ImageFont
from src.ui.display_interface import DisplayInterface
from src.utils.error_handler import ErrorHandler


# Initialize logger
logger = ErrorHandler("error_log")


class SimulatedLEDMatrix(DisplayInterface):
    """
    A simulated LED Matrix display for development purposes
    """
    
    def __init__(self, width=64, height=32, led_size=10, spacing=2, bg_color=(0, 0, 0)):
        """
        Initialize the simulated display
        
        Args:
            width: Width of the matrix in LEDs
            height: Height of the matrix in LEDs
            led_size: Size of each LED in pixels
            spacing: Spacing between LEDs in pixels
            bg_color: Background color as RGB tuple
        """
        self.width = width
        self.height = height
        self.led_size = led_size
        self.spacing = spacing
        self.bg_color = bg_color
        self.window_width = width * (led_size + spacing)
        self.window_height = height * (led_size + spacing)
        self.settings_manager = None  # Will be set by set_colors method
        
        # Make window larger for better visibility
        self.window_scale = 1.5
        self.window_width = int(self.window_width * self.window_scale)
        self.window_height = int(self.window_height * self.window_scale)
        
        # Initialize display attributes
        self.pixels = [[(0, 0, 0) for _ in range(width)] for _ in range(height)]
        self.text = ""
        self.text_color = (255, 255, 255)
        self.scroll_position = 0
        self.brightness = 1.0
        self.rotation = 0
        self.running = True
        self.screen = None
        self.font = None
        self.text_surface = None
        
        # For scrolling animation
        self.scroll_timer = time.time()
        self.frame_delay = 0.04
        self.scroll_reset_delay = 2.0  # Seconds to pause at end before resetting
        self.scroll_pause_timer = 0
        self.scroll_paused = False
        
        # For combined ride display (name + wait time)
        self._current_ride_name = ""
        self._current_ride_name_color = (100, 150, 255)
        self._current_wait_time = ""
        self._current_wait_time_color = (255, 255, 0)
        
        # Separate surfaces for dual-zone display
        self._wait_time_surface = None  # Static surface for wait time
        self._ride_name_surface = None  # Scrolling surface for ride name
        self._is_dual_zone = False      # Flag to indicate dual-zone mode
        
        logger.info("Initialized Simulated LED Matrix")
    
    def initialize(self):
        """Initialize the Pygame window and components"""
        try:
            pygame.init()
            pygame.display.set_caption("Theme Park API - LED Matrix Simulator")

            # Set a reasonable fixed window size that fits most screens
            # Using 640x320 as a baseline which should fit on most displays
            self.window_width = 640
            self.window_height = 320
            self.window_scale = min(
                self.window_width / (self.width * (self.led_size + self.spacing)),
                self.window_height / (self.height * (self.led_size + self.spacing))
            )
            self.screen = pygame.display.set_mode((self.window_width, self.window_height))

            # Find a suitable font from the system for best compatibility
            system_fonts = pygame.font.get_fonts()
            preferred_fonts = ["arial", "helvetica", "verdana", "dejavusans"]

            selected_font = None
            for font in preferred_fonts:
                if font in system_fonts:
                    selected_font = font
                    break

            font_path = self._find_font()
            # Just use a very large size directly (48pt) for consistent results
            font_size = 48

            try:
                if selected_font:
                    # Use system font (more reliable)
                    self.font = pygame.font.SysFont(selected_font, font_size, bold=True)
                    logger.info(f"Using system font: {selected_font} at {font_size}px")
                elif font_path:
                    # Fall back to file font if selected_font not available
                    self.font = pygame.font.Font(font_path, font_size)
                    logger.info(f"Using file font: {font_path} at {font_size}px")
                else:
                    # Last resort
                    self.font = pygame.font.SysFont("Arial", font_size, bold=True)
                    logger.info(f"Using fallback font: Arial at {font_size}px")
            except Exception as e:
                logger.error(e, "Error loading font, falling back to default")
                self.font = pygame.font.SysFont(None, font_size, bold=True)  # Default system font
                
            # Set up the event handling for window close
            pygame.event.set_allowed([pygame.QUIT, pygame.KEYDOWN])
            
            # Print font info for debugging
            logger.info(f"Using font size: {font_size}px in window size: {self.window_width}x{self.window_height}")
            logger.info("Pygame initialized successfully")
            return True
            
        except Exception as e:
            logger.error(e, "Failed to initialize Pygame")
            return False
    
    def _find_font(self):
        """Find a suitable font for the simulator"""
        # Try to use the same font as the hardware if available
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "fonts", "tom-thumb.bdf"),
            os.path.join(os.path.dirname(__file__), "..", "fonts", "Teeny-Tiny-Pixls-5.bdf"),
            "/System/Library/Fonts/Monaco.ttf",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
            "C:\\Windows\\Fonts\\consola.ttf"  # Windows
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.debug(f"Using font: {path}")
                return path
                
        return None
        
    def set_text(self, text, color=None):
        """
        Set the text to display

        Args:
            text: The text to display
            color: RGB color tuple (default: white)
        """
        self.text = text

        if color:
            if isinstance(color, int):
                # Convert hex to RGB tuple
                r = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                b = color & 0xFF
                self.text_color = (r, g, b)
            else:
                self.text_color = color

        if self.font and text:
            try:
                # For simulator, render at a higher quality with anti-aliasing
                self.text_surface = self.font.render(text, True, self.text_color)

                # IMPORTANT FIX: Create a much larger text surface for better visibility
                # Scale up the text by 3x from what the font normally renders
                text_width = self.text_surface.get_width()
                text_height = self.text_surface.get_height()

                # Scale the text based on its length for optimal display
                # Longer text should be smaller to fit better in the display
                text_length = len(text)

                # For shorter text (under 20 chars), use larger size (60% of window height)
                # For longer text, gradually reduce size down to 40% of window height
                height_percentage = max(0.4, min(0.6, 0.6 - (text_length - 20) * 0.01))
                desired_height = int(self.window_height * height_percentage)

                # Calculate scale factor and resulting dimensions
                scale_factor = desired_height / text_height
                scaled_width = int(text_width * scale_factor)
                scaled_height = int(text_height * scale_factor)

                # Log text size info
                logger.info(f"Text length: {text_length}, height %: {height_percentage:.2f}, scale: {scale_factor:.2f}")

                # Create a scaled version of the text surface
                scaled_surface = pygame.transform.scale(self.text_surface, (scaled_width, scaled_height))
                self.text_surface = scaled_surface

                # Reset scroll position
                self.scroll_position = self.window_width
                logger.info(f"Rendered text at size: {scaled_width}x{scaled_height}")
            except Exception as e:
                logger.error(e, f"Error rendering text: {text}")
    
    def scroll(self, frame_delay=0.04):
        """
        Scroll the text across the display
        
        Args:
            frame_delay: Delay between frame updates in seconds (smaller = faster)
        """
        # Use a slightly slower default scroll for better readability in simulator
        self.frame_delay = max(frame_delay, 0.02)
        self.scroll_position = self.window_width  # Start from right edge
        self.scroll_paused = False  # Reset pause state
        logger.debug(f"Set scroll speed: {self.frame_delay} seconds between frames")
    
    def clear(self):
        """Clear the display"""
        self.pixels = [[(0, 0, 0) for _ in range(self.width)] for _ in range(self.height)]
        self.text = ""
        self.text_surface = None
    
    def update(self):
        """Update the display state and render to screen"""
        # Check for quit events
        self._handle_events()
        
        if not self.screen:
            return False
            
        # Clear screen with background color
        self.screen.fill(self.bg_color)
        
        # Skip drawing individual LEDs to improve performance
        # Just draw a border around the display area to indicate boundaries
        pygame.draw.rect(self.screen, (40, 40, 40),
                        pygame.Rect(0, 0, self.window_width, self.window_height), 2)
        
        # Handle text scrolling with pausing at end
        if self.text_surface:
            current_time = time.time()
            
            # If we're in the pause state at the end of scrolling
            if self.scroll_paused:
                if current_time - self.scroll_pause_timer > self.scroll_reset_delay:
                    # Resume scrolling from the right edge after pause
                    self.scroll_paused = False
                    self.scroll_position = self.window_width
            # Normal scrolling behavior
            elif current_time - self.scroll_timer > self.frame_delay:
                self.scroll_timer = current_time

                # Adjust scroll speed based on text length - ensure full text can be seen
                # Move at least 3 pixels per frame for faster scrolling
                speed = max(3, int(self.text_surface.get_width() / 200))
                self.scroll_position -= speed  # Faster scrolling for longer texts
                
                # When text scrolls past the left edge completely
                if self.scroll_position < -self.text_surface.get_width():
                    # Enter paused state and record time
                    self.scroll_paused = True
                    self.scroll_pause_timer = current_time
                    # Position text just past the left edge during pause
                    self.scroll_position = -self.text_surface.get_width()
            
            # Handle dual-zone display or normal scrolling text
            if self._is_dual_zone and self._wait_time_surface and self._ride_name_surface:
                # Dual zone mode: scrolling ride name on top, static wait time on bottom
                top_zone_height = self.window_height // 3
                bottom_zone_height = self.window_height - top_zone_height
                
                # Draw scrolling ride name in top zone
                name_y = (top_zone_height - self._ride_name_surface.get_height()) // 2
                self.screen.blit(self._ride_name_surface, (self.scroll_position, name_y))
                
                # Draw static wait time in bottom zone (centered)
                time_x = (self.window_width - self._wait_time_surface.get_width()) // 2
                time_y = top_zone_height + (bottom_zone_height - self._wait_time_surface.get_height()) // 2
                self.screen.blit(self._wait_time_surface, (time_x, time_y))
                
            else:
                # Normal single text scrolling mode
                text_y = (self.window_height - self.text_surface.get_height()) // 2
                self.screen.blit(self.text_surface, (self.scroll_position, text_y))

            # No longer need debug outline for production use
            
            # Draw a marker for visual reference (simulation edges)
            pygame.draw.lines(self.screen, (50, 50, 50), False, [
                (0, 0), (0, self.window_height), 
                (self.window_width, self.window_height), 
                (self.window_width, 0), 
                (0, 0)
            ], 2)
        
        # Update the display
        pygame.display.flip()
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
            # If it's a PIL Image
            if hasattr(image, 'mode') and image.mode:
                # Resize to fit matrix if needed
                width, height = image.size
                if width > self.width or height > self.height:
                    image = image.resize((self.width, self.height))
                
                # Convert PIL Image to pygame surface directly
                image_data = image.convert('RGB')
                
                # Fill pixel array directly from image
                for py in range(min(image.height, self.height)):
                    for px in range(min(image.width, self.width)):
                        r, g, b = image_data.getpixel((px, py))
                        y_pos = y + py
                        x_pos = x + px
                        if 0 <= y_pos < self.height and 0 <= x_pos < self.width:
                            self.pixels[y_pos][x_pos] = (r, g, b)
                
        except Exception as e:
            logger.error(e, "Error displaying image")
    
    def set_brightness(self, brightness):
        """
        Set the display brightness
        
        Args:
            brightness: Float between 0.0 and 1.0
        """
        self.brightness = min(max(brightness, 0.0), 1.0)
    
    def set_rotation(self, rotation):
        """
        Set display rotation
        
        Args:
            rotation: Rotation angle in degrees (0, 90, 180, 270)
        """
        self.rotation = rotation
    
    def _handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    pygame.quit()
                    sys.exit()
    
    def _apply_brightness(self, color):
        """Apply brightness adjustment to a color"""
        r, g, b = color
        return (
            int(r * self.brightness),
            int(g * self.brightness),
            int(b * self.brightness)
        )
    
    async def run_async(self):
        """Run the display in an async loop"""
        while self.running:
            self.update()
            await asyncio.sleep(0.01)  # Small delay to prevent CPU hogging
    
    # Additional methods required by app.py
    
    async def show_splash(self, duration=4):
        """Show splash screen for specified duration"""
        logger.info(f"Showing splash screen for {duration} seconds")
        try:
            # Clear ride display when showing splash
            self.clear_ride_display()
            
            # Try to load splash image from images folder
            splash_path = os.path.join(os.path.dirname(__file__), "..", "images", "OpeningLEDLogo.bmp")
            if os.path.exists(splash_path):
                splash_image = Image.open(splash_path)
                self.show_image(splash_image)
            else:
                # Create a text splash
                self.set_text("Theme Park API", (0, 255, 0))  # Green text
            
            await asyncio.sleep(duration)
        except Exception as e:
            logger.error(e, "Error showing splash screen")
    
    async def show_scroll_message(self, message, duration=None):
        """
        Show a scrolling message
        
        Args:
            message: The message to scroll
            duration: Optional duration to show the message
        """
        logger.info(f"Scroll message: {message}")
        # Clear ride display when showing a scroll message
        self.clear_ride_display()
        self.set_text(message)
        
        # Use slower scroll speed for simulator to improve readability
        # This gives a better experience in the simulator
        self.scroll(0.03)  # Slightly slower scroll speed for better readability
        
        # In simulator, we need to give time for the full text to display
        # before continuing. If no duration is specified, let it scroll at least
        # once across the full display width.
        if not duration:
            # Calculate a reasonable duration based on text length
            # This ensures long messages can be read completely
            estimated_scroll_time = max(3.0, len(message) * 0.15)
            await asyncio.sleep(estimated_scroll_time)
        else:
            await asyncio.sleep(duration)
    
    async def show_centered(self, line1, line2=None, duration=2):
        """Show centered text"""
        logger.info(f"Centered message: {line1} / {line2 or ''}")
        self.clear()
        
        # Display first line
        self.set_text(line1)
        
        # If there's a second line, we'd handle it here
        # For simulator just show the first line for now
        
        if duration:
            await asyncio.sleep(duration)
            
    async def show_ride_wait_time(self, wait_time):
        """
        Show a ride's wait time
        
        Args:
            wait_time: The wait_time to display (as string)
        """
        logger.info(f"Showing ride wait time: {wait_time}")
        # Clear previous ride name when starting a new ride
        self._current_ride_name = ""
        self._current_wait_time = wait_time
        self._current_wait_time_color = (255, 255, 0)  # Yellow color for wait time
        self._update_combined_display()
        
    async def show_ride_closed(self, message):
        """
        Show that a ride is closed
        
        Args:
            message: The message to display (usually "Closed")
        """
        logger.info(f"Showing ride closed: {message}")
        # Clear previous ride name when starting a new ride
        self._current_ride_name = ""
        self._current_wait_time = message
        self._current_wait_time_color = (255, 0, 0)  # Red color for closed rides
        self._update_combined_display()
        
    async def show_ride_name(self, ride_name):
        """
        Show a ride's name
        
        Args:
            ride_name: The name of the ride to display
        """
        logger.info(f"Showing ride name: {ride_name}")
        # Store ride name for combined display
        self._current_ride_name = ride_name
        self._current_ride_name_color = (100, 150, 255)  # Light blue color for ride names
        self._update_combined_display()
        # Minimal sleep to allow other tasks to run
        # Just yield control without significant delay
        await asyncio.sleep(0.01)
    
    def set_colors(self, settings_manager):
        """Set display colors from settings"""
        try:
            # Store settings manager for use by message queue
            self.settings_manager = settings_manager
            
            # Extract color settings
            settings = getattr(settings_manager, 'settings', {})
            
            # Apply colors if available
            bg_color = settings.get('background_color', 0x000000)
            text_color = settings.get('text_color', 0xFFFFFF)
            
            # Convert hex to RGB tuples if needed
            if isinstance(bg_color, int):
                r = (bg_color >> 16) & 0xFF
                g = (bg_color >> 8) & 0xFF
                b = bg_color & 0xFF
                self.bg_color = (r, g, b)
            
            if isinstance(text_color, int):
                r = (text_color >> 16) & 0xFF
                g = (text_color >> 8) & 0xFF
                b = text_color & 0xFF
                self.text_color = (r, g, b)
                
            logger.info(f"Set display colors - bg: {self.bg_color}, text: {self.text_color}")
            
        except Exception as e:
            logger.error(e, "Error setting display colors")
            # Use default colors
            self.bg_color = (0, 0, 0)  # Black
            self.text_color = (255, 255, 255)  # White
    
    def _update_combined_display(self):
        """Update the display to show both ride name and wait time simultaneously"""
        try:
            # Clear the display
            self.clear()
            
            # If we have both ride name and wait time, display them in dual zones
            if self._current_ride_name and self._current_wait_time:
                self._render_dual_zone_display(self._current_ride_name, self._current_wait_time)
            elif self._current_ride_name:
                # Only ride name - exit dual zone mode and use normal text display
                self._is_dual_zone = False
                self._wait_time_surface = None
                self._ride_name_surface = None
                self.set_text(self._current_ride_name, self._current_ride_name_color)
            elif self._current_wait_time:
                # Only wait time - exit dual zone mode and use normal text display
                self._is_dual_zone = False
                self._wait_time_surface = None
                self._ride_name_surface = None
                self.set_text(self._current_wait_time, self._current_wait_time_color)
            
        except Exception as e:
            logger.error(e, "Error updating combined display")
    
    def _render_dual_zone_display(self, ride_name, wait_time):
        """Render ride name on top (scrolling) and wait time on bottom (static)"""
        try:
            if not self.font:
                return
            
            # Set dual-zone mode
            self._is_dual_zone = True
            
            # Calculate zones: top 1/3 for ride name, bottom 2/3 for wait time
            top_zone_height = self.window_height // 3
            bottom_zone_height = self.window_height - top_zone_height
            
            # Create ride name surface (for scrolling in top zone)
            ride_name_surface = self.font.render(ride_name, True, self._current_ride_name_color)
            # Scale ride name to fit top zone height
            name_scale = (top_zone_height * 0.7) / ride_name_surface.get_height()
            scaled_name_width = int(ride_name_surface.get_width() * name_scale)
            scaled_name_height = int(ride_name_surface.get_height() * name_scale)
            self._ride_name_surface = pygame.transform.scale(ride_name_surface, 
                                                           (scaled_name_width, scaled_name_height))
            
            # Create wait time surface (static in bottom zone)  
            wait_time_surface = self.font.render(wait_time, True, self._current_wait_time_color)
            # Scale wait time to fit bottom zone (make it nice and large)
            time_scale = min(
                (bottom_zone_height * 0.8) / wait_time_surface.get_height(),
                (self.window_width * 0.6) / wait_time_surface.get_width()
            )
            scaled_time_width = int(wait_time_surface.get_width() * time_scale)
            scaled_time_height = int(wait_time_surface.get_height() * time_scale)
            self._wait_time_surface = pygame.transform.scale(wait_time_surface, 
                                                           (scaled_time_width, scaled_time_height))
            
            # Store text for scrolling logic
            self.text = ride_name
            self.text_surface = self._ride_name_surface  # Use ride name for scrolling
            
            # Reset scroll position for new ride name
            self.scroll_position = self.window_width
            self.scroll_paused = False
            
            logger.info(f"Dual zone display: '{ride_name}' (scrolling top) + '{wait_time}' (static bottom)")
            
        except Exception as e:
            logger.error(e, "Error rendering dual zone display")
    
    def clear_ride_display(self):
        """Clear both ride name and wait time"""
        self._current_ride_name = ""
        self._current_wait_time = ""
        self._is_dual_zone = False
        self._wait_time_surface = None
        self._ride_name_surface = None
        self.clear()
    
    def clear_wait_time(self):
        """Clear only the wait time, keep ride name"""
        self._current_wait_time = ""
        self._update_combined_display()
    
    def clear_ride_name(self):
        """Clear only the ride name, keep wait time"""
        self._current_ride_name = ""
        self._update_combined_display()