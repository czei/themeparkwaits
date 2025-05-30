"""Roller coaster animation for CircuitPython/MatrixPortal S3."""

import math
import time
import gc

# CircuitPython imports
try:
    import board
    import displayio
    from adafruit_matrixportal.matrix import Matrix
    CIRCUITPYTHON = True
except ImportError:
    # For development/testing
    CIRCUITPYTHON = False
    print("CircuitPython libraries not available - this will only work on hardware")


class RollerCoaster:
    """Roller coaster track and cart physics simulation."""
    
    def __init__(self, width=64, height=32):
        self.width = width
        self.height = height
        
        # Track points - create a fun roller coaster path
        self.track_points = []
        self._generate_track()
        
        # Cart physics
        self.cart_position = 0.0  # Position along track (0 to len(track_points))
        self.cart_velocity = 0.0  # Speed along track
        self.gravity = 0.3
        self.friction = 0.99  # Slight friction
        self.boost_power = 3.0  # Initial boost at start
        
        # Track the cart sprite position
        self.cart_x = 0
        self.cart_y = 0
        
    def _generate_track(self):
        """Generate roller coaster track points."""
        # Create a loop with hills and valleys
        points = []
        
        # Start from left side, go up
        for x in range(5, 20):
            y = 25 - (x - 5) // 2
            points.append((x, y))
            
        # First big hill
        for x in range(20, 35):
            # Parabolic hill
            t = (x - 27.5) / 7.5
            y = int(15 + 5 * (1 - t * t))  # Make hill less extreme
            y = max(5, min(28, y))  # Clamp to screen bounds
            points.append((x, y))
            
        # Drop down
        for x in range(35, 40):
            y = 18 + (x - 35) * 2
            y = max(5, min(28, y))
            points.append((x, y))
            
        # Small hill
        for x in range(40, 50):
            t = (x - 45) / 5
            y = int(24 - 4 * (1 - t * t))
            y = max(5, min(28, y))
            points.append((x, y))
            
        # Final curve back to start
        for x in range(50, 55):
            y = 20 - (x - 50)
            y = max(5, min(28, y))
            points.append((x, y))
            
        # Bottom return
        for x in range(55, 5, -1):
            points.append((x, 28))
            
        # Close the loop - go back up to start
        for y in range(28, 17, -1):
            points.append((5, y))
            
        self.track_points = points
        
    def update_cart(self):
        """Update cart position based on physics."""
        if len(self.track_points) < 2:
            return
            
        # Get current and next track positions
        current_idx = int(self.cart_position) % len(self.track_points)
        next_idx = (current_idx + 1) % len(self.track_points)
        
        # Calculate slope between current and next point
        x1, y1 = self.track_points[current_idx]
        x2, y2 = self.track_points[next_idx]
        
        # Height difference (positive = going down)
        height_diff = y2 - y1
        
        # Apply gravity based on slope
        # Going down increases velocity, going up decreases it
        acceleration = height_diff * self.gravity / 5.0
        
        # Apply boost at the start
        if self.cart_position < 5 and self.cart_velocity < 1.0:
            acceleration += self.boost_power
            
        # Update velocity and position
        self.cart_velocity += acceleration
        self.cart_velocity *= self.friction  # Apply friction
        
        # Limit max speed
        self.cart_velocity = max(-5.0, min(5.0, self.cart_velocity))
        
        # Update position
        self.cart_position += self.cart_velocity
        
        # Wrap around track
        if self.cart_position >= len(self.track_points):
            self.cart_position -= len(self.track_points)
        elif self.cart_position < 0:
            self.cart_position += len(self.track_points)
            
        # Interpolate cart position
        t = self.cart_position - current_idx
        if t < 0:
            t = 0
        elif t > 1:
            t = 1
            
        self.cart_x = int(x1 + (x2 - x1) * t)
        self.cart_y = int(y1 + (y2 - y1) * t)


def create_cart_sprite():
    """Create a cart sprite bitmap (3x2 pixels)."""
    bitmap = displayio.Bitmap(3, 2, 2)
    # Cart shape
    bitmap[0, 0] = 1
    bitmap[1, 0] = 1
    bitmap[2, 0] = 1
    bitmap[0, 1] = 1
    bitmap[2, 1] = 1
    return bitmap


def create_track_bitmap(width, height, track_points):
    """Create bitmap with track drawn on it."""
    bitmap = displayio.Bitmap(width, height, 4)  # 4 colors
    
    # Draw track
    for x, y in track_points:
        if 0 <= x < width and 0 <= y < height:
            bitmap[x, y] = 1  # Track color
            
    # Add track supports (pillars)
    for x in range(0, width, 8):
        track_y = None
        for tx, ty in track_points:
            if tx == x:
                track_y = ty
                break
                
        if track_y is not None and track_y < height - 2:
            # Draw support pillar
            for y in range(track_y + 1, height):
                if y < height:
                    bitmap[x, y] = 2  # Support color
                    
    return bitmap


def hsv_to_rgb565(h, s, v):
    """Convert HSV to RGB565 color format."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
        
    # Convert to 0-255 range
    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)
    
    # Convert to RGB565
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def run_roller_coaster():
    """Run roller coaster animation on CircuitPython."""
    if not CIRCUITPYTHON:
        print("This version requires CircuitPython and MatrixPortal S3 hardware")
        return
        
    # Initialize matrix
    matrix = Matrix(width=64, height=32, bit_depth=6)
    display = matrix.display
    
    # Create main group
    main_group = displayio.Group()
    
    # Create roller coaster simulation
    coaster = RollerCoaster(64, 32)
    
    # Create track bitmap and palette
    track_bitmap = create_track_bitmap(64, 32, coaster.track_points)
    track_palette = displayio.Palette(4)
    track_palette[0] = 0x000000  # Background (black)
    track_palette[1] = 0x808080  # Track (gray)
    track_palette[2] = 0x404040  # Supports (dark gray)
    track_palette[3] = 0xFF0000  # Reserved for effects
    
    # Create track tilegrid
    track_grid = displayio.TileGrid(track_bitmap, pixel_shader=track_palette)
    main_group.append(track_grid)
    
    # Create cart sprite
    cart_bitmap = create_cart_sprite()
    cart_palette = displayio.Palette(2)
    cart_palette[0] = 0x000000  # Transparent black
    cart_palette[1] = 0xFF0000  # Cart (red)
    
    cart_sprite = displayio.TileGrid(
        cart_bitmap,
        pixel_shader=cart_palette,
        width=1,
        height=1,
        tile_width=3,
        tile_height=2,
        default_tile=0,
        x=0,
        y=0
    )
    main_group.append(cart_sprite)
    
    # Show on display
    display.root_group = main_group
    
    # Animation variables
    frame_count = 0
    
    # Main loop
    while True:
        # Update roller coaster physics
        coaster.update_cart()
        
        # Update cart sprite position
        cart_sprite.x = coaster.cart_x - 1
        cart_sprite.y = coaster.cart_y - 1
        
        # Animate cart color based on speed
        speed_factor = abs(coaster.cart_velocity) / 5.0
        hue = 0 if speed_factor < 0.5 else (60 - speed_factor * 60)  # Red to yellow
        cart_color = hsv_to_rgb565(hue, 1.0, 1.0)
        cart_palette[1] = cart_color
        
        # Pulse track color slightly
        pulse = (math.sin(frame_count * 0.05) + 1) * 0.5
        gray_value = int(128 + 40 * pulse)
        gray_565 = ((gray_value & 0xF8) << 8) | ((gray_value & 0xFC) << 3) | (gray_value >> 3)
        track_palette[1] = gray_565
        
        frame_count += 1
        
        # Memory management
        if frame_count % 60 == 0:  # Every second at 60fps
            gc.collect()
            
        time.sleep(0.033)  # ~30 FPS to reduce processing load


if __name__ == "__main__":
    run_roller_coaster()