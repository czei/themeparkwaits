"""
Shared reveal animation module that works in both CircuitPython and PyLEDSimulator environments.
Uses PyLEDSimulator's compatibility layer for unified implementation.
"""
import asyncio
import random
import time

try:
    # Try PyLEDSimulator import first
    from pyledsimulator import displayio
except ImportError:
    # Fall back to CircuitPython displayio
    import displayio

from src.utils.error_handler import ErrorHandler

logger = ErrorHandler("error_log")


def get_theme_park_waits_pixels():
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


def simple_shuffle(lst):
    """Simple in-place shuffle for CircuitPython compatibility."""
    for i in range(len(lst)):
        j = random.randint(0, len(lst) - 1)
        lst[i], lst[j] = lst[j], lst[i]


async def show_reveal_splash(main_group):
    """
    Show the splash screen with reveal animation style.
    This function works in both CircuitPython and PyLEDSimulator environments
    by using the displayio compatibility layer.
    
    Args:
        main_group: The main display group to add the reveal animation to
    """
    try:
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
        main_group.append(reveal_group)
        
        # Get target pixels for THEME PARK WAITS
        target_pixels = get_theme_park_waits_pixels()
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
        
        # Shuffle for randomness
        simple_shuffle(incorrect_on)
        simple_shuffle(missing_text)
        
        logger.debug(f"Initial state: {len(incorrect_on)} incorrect on, {len(missing_text)} text missing")
        
        # Reveal animation loop
        start_time = time.monotonic()
        last_update = time.monotonic()
        animation_complete = False
        
        while not animation_complete:
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
        
        await asyncio.sleep(2)
        
        # Clean up - remove reveal group
        main_group.remove(reveal_group)
        
    except Exception as e:
        logger.error(e, "Error in reveal splash animation")