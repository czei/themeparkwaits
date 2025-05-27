class Pixel:
    def __init__(self, x, y, value):
        self.x = x
        self.y = y
        self.value = value


class ImageProcessor:
    def __init__(self, image_bitmap):

        # Needed later to write over with modified values
        self.image = image_bitmap

        # Which pixel are we on when cycling through a change?
        self.pixel_index = 0

        #
        # Find list of pixels that have values
        #
        self.pixels = []
        self.detect_pixels(image_bitmap)

    def detect_pixels(self, image_matrix):
        for y in range(image_matrix.height - 1):
            for x in range(image_matrix.width - 1):
                if image_matrix[x, y] > 0:
                    self.pixels.append(Pixel(x, y, image_matrix[x, y]))

    def get_current_pixel(self):
        return self.pixels[self.pixel_index]

    # Find the pixel we messed with the last time and set it
    # back to its original value
    def reset_previous_pixel(self):
        if self.pixel_index < 1:
            return
        p = self.pixels[self.pixel_index-1]
        self.image[p.x,p.y] = p.value

    # Change the current pixel's value
    def handle_next_pixel(self):
        p = self.get_current_pixel()
        self.image[p.x, p.y] = ImageProcessor.process_pixel(p)
        self.pixel_index += 1
        if self.pixel_index >= len(self.pixels):
            self.pixel_index = 0
            return True
        return False

    # Calculate a color or brightness change for each pixel
    @staticmethod
    def process_pixel(self, p):
        return p.value * 1.5
