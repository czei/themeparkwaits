"""
Roller Coaster Animation for LED Matrix Display
Uses sprites for optimized performance on CircuitPython
Copyright 2024 3DUPFitters LLC
"""
import time
import math
import asyncio
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

# Check if running on CircuitPython
try:
    import displayio
    import terminalio
    from adafruit_display_text import label
    CIRCUITPYTHON = True
except ImportError:
    # For simulator, these will be provided by the display
    CIRCUITPYTHON = False
    displayio = None


class RollerCoasterAnimation:
    """Animated roller coaster demo with sprite-based cart"""
    
    def __init__(self, display_width=64, display_height=32):
        """
        Initialize the roller coaster animation
        
        Args:
            display_width: Width of the display in pixels
            display_height: Height of the display in pixels
        """
        self.width = display_width
        self.height = display_height
        
        # Cart dimensions - 1/3 of display height
        self.cart_height = max(8, self.height // 3)  # ~10 pixels for 32 pixel display, minimum 8
        self.cart_width = int(self.cart_height * 1.5)  # Slightly wider than tall
        
        # Track parameters
        self.track_points = []
        self.track_length = 0
        self.generate_track()
        
        # Cart position (0.0 to 1.0 along track)
        self.cart_position = 0.0
        self.cart_speed = 0.02  # Speed along track
        
        # Display groups
        self.main_group = None
        self.track_group = None
        self.cart_sprite = None
        self.cart_bitmap = None
        self.initialized = False
        
    def generate_track(self):
        """Generate a smoother, rounder roller coaster track path"""
        points = []
        
        # Create a smooth roller coaster path using bezier-like curves
        total_width = self.width + 40  # Extend beyond screen for wrapping
        
        # Define key control points for a smooth track
        control_points = [
            (0, self.height - 8),           # Start at bottom
            (15, self.height - 18),         # Gentle climb
            (35, 8),                        # High peak
            (50, 25),                       # Drop to mid-level
            (65, 12),                       # Small hill
            (80, 20),                       # Valley
            (100, 15),                      # Gentle hill
            (120, 22),                      # End point (wraps around)
        ]
        
        # Generate smooth curves between control points using spline interpolation
        for i in range(len(control_points) - 1):
            x1, y1 = control_points[i]
            x2, y2 = control_points[i + 1]
            
            # Number of interpolation points between control points
            num_points = max(10, int(abs(x2 - x1) / 2))
            
            for j in range(num_points):
                t = j / float(num_points - 1) if num_points > 1 else 0
                
                # Smooth interpolation with easing
                # Use smoothstep function for natural curves
                smooth_t = t * t * (3 - 2 * t)
                
                x = x1 + (x2 - x1) * smooth_t
                y = y1 + (y2 - y1) * smooth_t
                
                # Add slight curve variation for realism
                curve_offset = math.sin(t * math.pi) * 2
                y += curve_offset
                
                # Clamp y to display bounds with margin
                y = max(5, min(y, self.height - 5))
                
                points.append((x, int(y)))
        
        # Store track points
        self.track_points = points
        self.track_length = len(points)
        
    def create_cart_bitmap(self):
        """Create a mine cart bitmap with bucket shape"""
        if not CIRCUITPYTHON and not displayio:
            return None
            
        # Create bitmap for mine cart
        bitmap = displayio.Bitmap(self.cart_width, self.cart_height, 5)
        
        # Define palette for mine cart
        palette = displayio.Palette(5)
        palette[0] = 0x000000  # Transparent black
        palette[1] = 0x8B4513  # Brown (wooden cart body)
        palette[2] = 0xC0C0C0  # Silver (metal bands)
        palette[3] = 0x404040  # Dark gray (wheels)
        palette[4] = 0xFFD700  # Gold (contents/details)
        
        # Draw mine cart bucket shape
        # Bottom of bucket (tapered)
        bottom_width = max(2, self.cart_width - 4)
        bottom_start = (self.cart_width - bottom_width) // 2
        for x in range(bottom_start, bottom_start + bottom_width):
            bitmap[x, self.cart_height - 3] = 1  # Brown bottom
        
        # Bucket sides (flared outward)
        for y in range(2, self.cart_height - 3):
            # Calculate bucket width at this height (wider at top)
            bucket_progress = (self.cart_height - 3 - y) / float(self.cart_height - 5)
            width_at_y = int(bottom_width + bucket_progress * 2)
            width_at_y = min(width_at_y, self.cart_width - 2)
            
            start_x = (self.cart_width - width_at_y) // 2
            
            # Left and right sides
            bitmap[start_x, y] = 1
            bitmap[start_x + width_at_y - 1, y] = 1
            
            # Fill bucket interior with gold (mine contents)
            if y > 3 and width_at_y > 4:
                for x in range(start_x + 1, start_x + width_at_y - 1):
                    if (x + y) % 3 == 0:  # Sparse gold nuggets
                        bitmap[x, y] = 4
        
        # Top rim of bucket
        top_width = min(self.cart_width - 2, bottom_width + 2)
        top_start = (self.cart_width - top_width) // 2
        for x in range(top_start, top_start + top_width):
            bitmap[x, 2] = 1
        
        # Metal reinforcement bands
        band_y = self.cart_height - 5
        if band_y > 2:
            band_width = min(self.cart_width - 2, bottom_width + 1)
            band_start = (self.cart_width - band_width) // 2
            for x in range(band_start, band_start + band_width):
                bitmap[x, band_y] = 2  # Silver band
        
        # Wheels (under the bucket)
        wheel_y = self.cart_height - 2
        wheel_positions = [1, self.cart_width - 2]
        if self.cart_width > 8:
            wheel_positions.append(self.cart_width // 2)  # Middle wheel for longer carts
        
        for wheel_x in wheel_positions:
            if 0 <= wheel_x < self.cart_width:
                bitmap[wheel_x, wheel_y] = 3
                bitmap[wheel_x, wheel_y + 1] = 3
        
        self.cart_bitmap = bitmap
        return bitmap, palette
        
    def init_display(self, display):
        """
        Initialize the display groups and sprites
        
        Args:
            display: The display object to render to
        """
        if not displayio:
            logger.error(None, "displayio not available")
            return False
            
        try:
            # Create main group
            self.main_group = displayio.Group()
            
            # Create track bitmap with supports
            track_bitmap = displayio.Bitmap(self.width, self.height, 3)
            track_palette = displayio.Palette(3)
            track_palette[0] = 0x000000  # Black background
            track_palette[1] = 0x606060  # Gray track rails
            track_palette[2] = 0x8B4513  # Brown supports
            
            # Draw track supports first (behind rails)
            self.draw_track_supports(track_bitmap, 2)
            
            # Draw track
            for i in range(len(self.track_points) - 1):
                x1, y1 = self.track_points[i]
                x2, y2 = self.track_points[i + 1]
                self.draw_line(track_bitmap, x1, y1, x2, y2, 1)
            
            # Draw track rails (double lines)
            for i in range(len(self.track_points) - 1):
                x1, y1 = self.track_points[i]
                x2, y2 = self.track_points[i + 1]
                # Upper rail
                if y1 > 2 and y2 > 2:
                    self.draw_line(track_bitmap, x1, y1 - 2, x2, y2 - 2, 1)
                # Lower rail
                if y1 < self.height - 2 and y2 < self.height - 2:
                    self.draw_line(track_bitmap, x1, y1 + 2, x2, y2 + 2, 1)
            
            # Create track tile grid
            self.track_group = displayio.TileGrid(track_bitmap, pixel_shader=track_palette)
            self.main_group.append(self.track_group)
            
            # Create cart sprite
            cart_bitmap, cart_palette = self.create_cart_bitmap()
            if cart_bitmap:
                self.cart_sprite = displayio.TileGrid(
                    cart_bitmap, 
                    pixel_shader=cart_palette,
                    x=0, y=0
                )
                self.main_group.append(self.cart_sprite)
            
            # Show the main group
            display.root_group = self.main_group
            
            self.initialized = True
            logger.info("Roller coaster animation initialized")
            return True
            
        except Exception as e:
            logger.error(e, "Failed to initialize roller coaster animation")
            return False
    
    def draw_line(self, bitmap, x1, y1, x2, y2, color):
        """Draw a line on the bitmap using Bresenham's algorithm"""
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        while True:
            if 0 <= x1 < self.width and 0 <= y1 < self.height:
                bitmap[x1, y1] = color
            
            if x1 == x2 and y1 == y2:
                break
                
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy
    
    def draw_track_supports(self, bitmap, color):
        """Draw vertical supports from ground to track"""
        # Draw supports every 8-12 pixels along the track
        support_spacing = 10
        
        for i in range(0, len(self.track_points), support_spacing):
            x, y = self.track_points[i]
            
            # Only draw supports where track is significantly above ground
            ground_level = self.height - 1
            if y < ground_level - 4:  # Support needed if track is 4+ pixels above ground
                # Draw vertical support from ground to track
                for support_y in range(int(y + 2), ground_level):
                    if 0 <= x < self.width and 0 <= support_y < self.height:
                        bitmap[x, support_y] = color
                
                # Add cross-bracing every other support
                if i % (support_spacing * 2) == 0 and i + support_spacing < len(self.track_points):
                    next_x, next_y = self.track_points[min(i + support_spacing, len(self.track_points) - 1)]
                    
                    # Draw diagonal cross-brace
                    mid_y = (y + next_y) // 2 + 3
                    if mid_y < ground_level - 2:
                        # Left diagonal
                        brace_steps = min(8, abs(next_x - x))
                        for step in range(brace_steps):
                            if brace_steps > 0:
                                brace_x = int(x + (next_x - x) * step / brace_steps)
                                brace_y = int(mid_y + 2 * step // brace_steps)
                                if (0 <= brace_x < self.width and 0 <= brace_y < self.height 
                                    and brace_y < ground_level):
                                    bitmap[brace_x, brace_y] = color
                        
                        # Right diagonal  
                        for step in range(brace_steps):
                            if brace_steps > 0:
                                brace_x = int(x + (next_x - x) * step / brace_steps)
                                brace_y = int(mid_y + 4 - 2 * step // brace_steps)
                                if (0 <= brace_x < self.width and 0 <= brace_y < self.height 
                                    and brace_y < ground_level):
                                    bitmap[brace_x, brace_y] = color
    
    def update(self):
        """Update the animation - move cart along track"""
        if not self.initialized or not self.cart_sprite:
            return
            
        # Move cart along track
        self.cart_position += self.cart_speed
        if self.cart_position >= 1.0:
            self.cart_position = 0.0
        
        # Calculate cart position on track
        track_index = int(self.cart_position * (self.track_length - 1))
        if track_index < self.track_length:
            x, y = self.track_points[track_index]
            
            # Position cart centered on track
            self.cart_sprite.x = int(x - self.cart_width // 2)
            self.cart_sprite.y = int(y - self.cart_height + 2)  # Cart sits on track
            
            # Keep cart on screen
            self.cart_sprite.x = max(-self.cart_width, 
                                    min(self.cart_sprite.x, self.width))
            self.cart_sprite.y = max(0, 
                                    min(self.cart_sprite.y, self.height - self.cart_height))
            
            # Vary speed based on track position (slower uphill, faster downhill)
            if track_index > 0 and track_index < self.track_length - 1:
                prev_y = self.track_points[track_index - 1][1]
                next_y = self.track_points[track_index + 1][1]
                slope = next_y - prev_y
                
                # Adjust speed based on slope
                base_speed = 0.02
                if slope > 0:  # Going down
                    self.cart_speed = base_speed * (1 + slope * 0.1)
                else:  # Going up
                    self.cart_speed = base_speed * (1 + slope * 0.05)
                
                # Clamp speed
                self.cart_speed = max(0.005, min(0.05, self.cart_speed))


async def run_roller_coaster_demo(display):
    """
    Run the roller coaster animation demo
    
    Args:
        display: Display object to render to
    """
    logger.info("Starting roller coaster demo")
    
    # Create animation
    coaster = RollerCoasterAnimation(
        display_width=64,
        display_height=32
    )
    
    # Initialize display
    if hasattr(display, 'hardware') and display.hardware:
        # Hardware display
        success = coaster.init_display(display.hardware.display)
    else:
        # Simulator display - need to handle differently
        logger.info("Running on simulator display")
        # For simulator, we'll draw directly
        return await run_roller_coaster_simulator(display, coaster)
    
    if not success:
        logger.error(None, "Failed to initialize roller coaster display")
        return
    
    # Run animation loop
    logger.info("Running roller coaster animation loop")
    start_time = time.monotonic()
    
    while (time.monotonic() - start_time) < 30:  # Run for 30 seconds
        coaster.update()
        await asyncio.sleep(0.05)  # 20 FPS
    
    logger.info("Roller coaster demo complete")


async def run_roller_coaster_simulator(display, coaster):
    """
    Run roller coaster on simulator display using pygame directly
    
    Args:
        display: Simulator display object
        coaster: RollerCoasterAnimation instance
    """
    import pygame
    
    logger.info("Running roller coaster on simulator")
    
    # Get pygame screen from display
    if not hasattr(display, 'screen') or not display.screen:
        logger.error(None, "Display doesn't have pygame screen")
        return
    
    screen = display.screen
    
    # Calculate LED size and spacing
    led_size = int(display.led_size * display.window_scale)
    spacing = int(display.spacing * display.window_scale)
    cell_size = led_size + spacing
    
    # Animation loop
    start_time = time.monotonic()
    frame_count = 0
    clock = pygame.time.Clock()
    
    while (time.monotonic() - start_time) < 30:  # Run for 30 seconds
        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                logger.info("User closed window")
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    logger.info("User pressed ESC")
                    return
        
        # Clear screen
        screen.fill(display.bg_color)
        
        # Create a pixel buffer
        pixel_buffer = {}
        
        # Draw track supports first (behind track)
        support_color = (139, 69, 19)  # Brown supports
        support_spacing = 10
        ground_level = coaster.height - 1
        
        for i in range(0, len(coaster.track_points), support_spacing):
            x, y = coaster.track_points[i]
            
            # Only draw supports where track is significantly above ground
            if y < ground_level - 4:  # Support needed if track is 4+ pixels above ground
                # Draw vertical support from ground to track
                for support_y in range(int(y + 2), ground_level):
                    if 0 <= x < coaster.width and 0 <= support_y < coaster.height:
                        pixel_buffer[(x, support_y)] = support_color
                
                # Add cross-bracing every other support
                if i % (support_spacing * 2) == 0 and i + support_spacing < len(coaster.track_points):
                    next_idx = min(i + support_spacing, len(coaster.track_points) - 1)
                    next_x, next_y = coaster.track_points[next_idx]
                    
                    # Draw diagonal cross-brace
                    mid_y = (y + next_y) // 2 + 3
                    if mid_y < ground_level - 2:
                        # Simplified cross-bracing for simulator
                        brace_steps = min(6, abs(next_x - x))
                        for step in range(brace_steps):
                            if brace_steps > 0:
                                brace_x = int(x + (next_x - x) * step / brace_steps)
                                brace_y = int(mid_y + step)
                                if (0 <= brace_x < coaster.width and 0 <= brace_y < coaster.height 
                                    and brace_y < ground_level):
                                    pixel_buffer[(brace_x, brace_y)] = support_color
        
        # Draw track
        track_color = (64, 64, 64)  # Gray track
        for i in range(len(coaster.track_points) - 1):
            x1, y1 = coaster.track_points[i]
            x2, y2 = coaster.track_points[i + 1]
            
            # Draw main rail with interpolation
            steps = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
            for step in range(steps):
                t = step / float(steps - 1) if steps > 1 else 0
                x = int(x1 + (x2 - x1) * t)
                y = int(y1 + (y2 - y1) * t)
                if 0 <= x < coaster.width and 0 <= y < coaster.height:
                    pixel_buffer[(x, y)] = track_color
            
            # Draw upper rail
            if y1 > 2 and y2 > 2:
                for step in range(steps):
                    t = step / float(steps - 1) if steps > 1 else 0
                    x = int(x1 + (x2 - x1) * t)
                    y = int((y1 - 2) + ((y2 - 2) - (y1 - 2)) * t)
                    if 0 <= x < coaster.width and 0 <= y < coaster.height:
                        pixel_buffer[(x, y)] = track_color
            
            # Draw lower rail
            if y1 < coaster.height - 2 and y2 < coaster.height - 2:
                for step in range(steps):
                    t = step / float(steps - 1) if steps > 1 else 0
                    x = int(x1 + (x2 - x1) * t)
                    y = int((y1 + 2) + ((y2 + 2) - (y1 + 2)) * t)
                    if 0 <= x < coaster.width and 0 <= y < coaster.height:
                        pixel_buffer[(x, y)] = track_color
        
        # Update cart position
        coaster.cart_position += coaster.cart_speed
        if coaster.cart_position >= 1.0:
            coaster.cart_position = 0.0
        
        # Get cart position on track
        track_index = int(coaster.cart_position * (coaster.track_length - 1))
        if track_index < coaster.track_length:
            cart_x, cart_y = coaster.track_points[track_index]
            
            # Adjust speed based on slope
            if track_index > 0 and track_index < coaster.track_length - 1:
                prev_y = coaster.track_points[track_index - 1][1]
                next_y = coaster.track_points[track_index + 1][1]
                slope = next_y - prev_y
                
                base_speed = 0.02
                if slope > 0:  # Going down
                    coaster.cart_speed = base_speed * (1 + slope * 0.1)
                else:  # Going up
                    coaster.cart_speed = base_speed * (1 + slope * 0.05)
                
                coaster.cart_speed = max(0.005, min(0.05, coaster.cart_speed))
            
            # Draw mine cart (centered on track)
            cart_left = int(cart_x - coaster.cart_width // 2)
            cart_top = int(cart_y - coaster.cart_height + 2)
            
            # Mine cart colors
            brown = (139, 69, 19)    # Brown bucket
            silver = (192, 192, 192) # Silver bands
            gold = (255, 215, 0)     # Gold contents
            dark_gray = (64, 64, 64) # Wheels
            
            # Draw mine cart bucket shape
            # Bottom of bucket (tapered)
            bottom_width = max(2, coaster.cart_width - 4)
            bottom_start = (coaster.cart_width - bottom_width) // 2
            for x in range(bottom_start, bottom_start + bottom_width):
                px = cart_left + x
                py = cart_top + coaster.cart_height - 3
                if 0 <= px < coaster.width and 0 <= py < coaster.height:
                    pixel_buffer[(px, py)] = brown
            
            # Bucket sides (flared outward)
            for y in range(2, coaster.cart_height - 3):
                # Calculate bucket width at this height (wider at top)
                bucket_progress = (coaster.cart_height - 3 - y) / float(coaster.cart_height - 5)
                width_at_y = int(bottom_width + bucket_progress * 2)
                width_at_y = min(width_at_y, coaster.cart_width - 2)
                
                start_x = (coaster.cart_width - width_at_y) // 2
                
                # Left and right sides
                px_left = cart_left + start_x
                px_right = cart_left + start_x + width_at_y - 1
                py = cart_top + y
                if 0 <= px_left < coaster.width and 0 <= py < coaster.height:
                    pixel_buffer[(px_left, py)] = brown
                if 0 <= px_right < coaster.width and 0 <= py < coaster.height:
                    pixel_buffer[(px_right, py)] = brown
                
                # Fill bucket interior with gold (mine contents)
                if y > 3 and width_at_y > 4:
                    for x in range(start_x + 1, start_x + width_at_y - 1):
                        if (x + y) % 3 == 0:  # Sparse gold nuggets
                            px = cart_left + x
                            if 0 <= px < coaster.width and 0 <= py < coaster.height:
                                pixel_buffer[(px, py)] = gold
            
            # Top rim of bucket
            top_width = min(coaster.cart_width - 2, bottom_width + 2)
            top_start = (coaster.cart_width - top_width) // 2
            for x in range(top_start, top_start + top_width):
                px = cart_left + x
                py = cart_top + 2
                if 0 <= px < coaster.width and 0 <= py < coaster.height:
                    pixel_buffer[(px, py)] = brown
            
            # Metal reinforcement band
            band_y = coaster.cart_height - 5
            if band_y > 2:
                band_width = min(coaster.cart_width - 2, bottom_width + 1)
                band_start = (coaster.cart_width - band_width) // 2
                for x in range(band_start, band_start + band_width):
                    px = cart_left + x
                    py = cart_top + band_y
                    if 0 <= px < coaster.width and 0 <= py < coaster.height:
                        pixel_buffer[(px, py)] = silver
            
            # Wheels (under the bucket)
            wheel_y = coaster.cart_height - 2
            wheel_positions = [1, coaster.cart_width - 2]
            if coaster.cart_width > 8:
                wheel_positions.append(coaster.cart_width // 2)  # Middle wheel for longer carts
            
            for wheel_x in wheel_positions:
                for wy in [0, 1]:  # 2 pixels high wheels
                    px = cart_left + wheel_x
                    py = cart_top + wheel_y + wy
                    if 0 <= px < coaster.width and 0 <= py < coaster.height:
                        pixel_buffer[(px, py)] = dark_gray
        
        # Draw all pixels as LED squares
        for (x, y), color in pixel_buffer.items():
            screen_x = x * cell_size + spacing
            screen_y = y * cell_size + spacing
            pygame.draw.rect(screen, color, 
                           pygame.Rect(screen_x, screen_y, led_size, led_size))
        
        # Draw a border
        pygame.draw.rect(screen, (40, 40, 40),
                        pygame.Rect(0, 0, display.window_width, display.window_height), 2)
        
        # Update display
        pygame.display.flip()
        clock.tick(20)  # 20 FPS
        
        frame_count += 1
        if frame_count % 100 == 0:
            logger.info(f"Roller coaster frame {frame_count}")
    
    logger.info("Roller coaster demo complete")
    screen.fill(display.bg_color)
    pygame.display.flip()


async def show_roller_coaster_animation(display, duration=10):
    """
    Show a roller coaster animation for a specified duration
    
    Args:
        display: Display object to render to
        duration: Duration to run animation in seconds
    """
    logger.info(f"Showing roller coaster animation for {duration} seconds")
    
    # Create animation
    coaster = RollerCoasterAnimation(
        display_width=64,
        display_height=32
    )
    
    # Run animation for specified duration
    if hasattr(display, 'screen'):
        # Simulator display
        await run_roller_coaster_simulator_duration(display, coaster, duration)
    else:
        # Hardware display or other
        await run_roller_coaster_demo_duration(display, coaster, duration)


async def run_roller_coaster_simulator_duration(display, coaster, duration):
    """Run roller coaster on simulator for specific duration"""
    import pygame
    
    if not hasattr(display, 'screen') or not display.screen:
        logger.error(None, "Display doesn't have pygame screen")
        return
    
    screen = display.screen
    led_size = int(display.led_size * display.window_scale)
    spacing = int(display.spacing * display.window_scale)
    cell_size = led_size + spacing
    
    start_time = time.monotonic()
    clock = pygame.time.Clock()
    
    while (time.monotonic() - start_time) < duration:
        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                return
        
        # Clear screen
        screen.fill(display.bg_color)
        pixel_buffer = {}
        
        # Draw track (simplified for shorter duration)
        track_color = (64, 64, 64)
        for i in range(0, len(coaster.track_points) - 1, 2):  # Skip every other point for performance
            x, y = coaster.track_points[i]
            if 0 <= x < coaster.width and 0 <= y < coaster.height:
                pixel_buffer[(x, y)] = track_color
        
        # Update and draw cart
        coaster.cart_position += coaster.cart_speed
        if coaster.cart_position >= 1.0:
            coaster.cart_position = 0.0
        
        track_index = int(coaster.cart_position * (coaster.track_length - 1))
        if track_index < coaster.track_length:
            cart_x, cart_y = coaster.track_points[track_index]
            cart_left = int(cart_x - coaster.cart_width // 2)
            cart_top = int(cart_y - coaster.cart_height + 2)
            
            # Draw simplified cart
            for y in range(coaster.cart_height):
                for x in range(coaster.cart_width):
                    px = cart_left + x
                    py = cart_top + y
                    if 0 <= px < coaster.width and 0 <= py < coaster.height:
                        # Color based on position in cart
                        if y < 2 or y >= coaster.cart_height - 2:
                            pixel_buffer[(px, py)] = (128, 128, 128)  # Wheels/base
                        elif x < 2 or x >= coaster.cart_width - 2:
                            pixel_buffer[(px, py)] = (255, 255, 0)    # Yellow details
                        else:
                            pixel_buffer[(px, py)] = (255, 0, 0)      # Red body
        
        # Draw all pixels
        for (x, y), color in pixel_buffer.items():
            screen_x = x * cell_size + spacing
            screen_y = y * cell_size + spacing
            pygame.draw.rect(screen, color, pygame.Rect(screen_x, screen_y, led_size, led_size))
        
        # Draw border
        pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(0, 0, display.window_width, display.window_height), 2)
        
        pygame.display.flip()
        clock.tick(20)
        await asyncio.sleep(0.01)  # Allow other async tasks


async def run_roller_coaster_demo_duration(display, coaster, duration):
    """Run roller coaster on hardware display for specific duration"""
    # For hardware displays, try to use displayio sprites
    if not coaster.init_display(display):
        logger.error(None, "Failed to initialize roller coaster on hardware display")
        return
    
    start_time = time.monotonic()
    
    while (time.monotonic() - start_time) < duration:
        coaster.update()
        await asyncio.sleep(0.05)  # 20 FPS