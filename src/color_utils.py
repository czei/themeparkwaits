class ColorUtils:
    colors = {'White': '0x7f7f7f',
              'Red': '0xff0000',
              'Yellow': '0xffff00',
              'Orange': '0xffa500',
              'Green': '0x00ff00',
              'Teal': '0x00ff78',
              'Cyan': '0x00ffff',
              'Blue': '0x0000aa',
              'Purple': '0xb400ff',
              'Magenta': '0xff00ff',
              'Black': '0x000000',
              'Gold': '0xffde1e',
              'Pink': '0xf25aff',
              'Aqua': '0x32ffff',
              'Jade': '0x00ff28',
              'Amber': '0xff6400',
              'Old Lace': '0xfdf5e6'}

    @staticmethod
    def html_color_chooser(name, hex_num_str):
        """
        :param name: Name of the HTML select field
        :param hex_num_str:  A string representation of the selected color
        :return:
        """
        html = ""
        html += f"<select name=\"{name}\" id=\"{id}\">\n"
        for color in ColorUtils.colors:
            if ColorUtils.colors[color] == hex_num_str:
                html += f"<option value=\"{ColorUtils.colors[color]}\" selected>{color}</option>\n"
            else:
                html += f"<option value=\"{ColorUtils.colors[color]}\">{color}</option>\n"

        html += "</select>"
        return html

    @staticmethod
    def hex_str_to_number(hex_string):
        return int(hex_string, 16)

    @staticmethod
    def number_to_hex_string(num):
        return hex(num)

    @staticmethod
    def scale_color(hex_string, scale):
        r, g, b = ColorUtils.hex_str_to_rgb(hex_string)
        r = int(r * scale)
        g = int(g * scale)
        b = int(b * scale)
        r_hex = hex(r)
        if r == 0:
            r_hex = "00"
        elif r_hex.startswith("0x"):
            r_hex = r_hex[2:]

        g_hex = hex(g)
        if g == 0:
            g_hex = "00"
        elif g_hex.startswith("0x"):
            g_hex = g_hex[2:]

        b_hex = hex(b)
        if b == 0:
            b_hex = "00"
        elif b_hex.startswith("0x"):
            b_hex = b_hex[2:]

        new_hex_str = "0x" + r_hex + g_hex + b_hex
        return new_hex_str

    @staticmethod
    def hex_str_to_rgb(hex_string):
        # Remove leading characters
        if hex_string.startswith('0x'):
            hex_string = hex_string[2:]

        # Check that the input is valid
        if len(hex_string) != 6:
            raise ValueError('Input string should be in the format #RRGGBB')

        # Split the input into rgb components
        r, g, b = int(hex_string[0:2], 16), int(hex_string[2:4], 16), int(hex_string[4:6], 16)

        return r, g, b

    @staticmethod
    def convert_3bit_bitmap_to_4bit(bitmap_3_bit, palette):
        # 3-bit max value is 8 and 6-bit max value is 64
        scale_factor = 16 / 8   # 2 to the 18th power = 262,144
        scale_factor = 1.0

        # Calculate new width and height
        width = bitmap_3_bit.width
        height = bitmap_3_bit.height

        # Create 4-bit bitmap with same dimensions
        bitmap_4_bit = displayio.Bitmap(width, height, 4096)

        # Copy and scale pixel values from 3-bit to 6-bit bitmap
        for y in range(height):
            for x in range(width):
                old_value = bitmap_3_bit[x, y]
                hex_value = ColorUtils.pad_hex(old_value)
                #print(f"Old Value = {old_value} Hex = {hex_value}")
                new_value = ColorUtils.hex_str_to_number(ColorUtils.scale_color(hex_value, scale_factor))
                # new_value = round(old_value * scale_factor)
                #print(f"Old Value = {old_value} Scaled = {new_value}")
                bitmap_4_bit[x, y] = new_value

        return bitmap_4_bit

    @staticmethod
    def pad_hex(num):
        hex_val = hex(num)[2:]  # remove '0x'
        # return hex_val.zfill(6)
        length = len(hex_val)
        for i in range(0, 6 - length):
            hex_val = "0" + hex_val
        return hex_val