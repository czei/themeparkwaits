from rainbowio import colorwheel

def remove_non_ascii(orig_str):
    new_str = ""
    for c in orig_str:
        if ord(c) < 128:
            new_str += c
    return new_str

class ColorPicker:
    def __init__(self):
        self.index = 0

    def get_next_color(self):
        self.index = (self.index + 1) % 256
        color = colorwheel(self.index)
        print(f"color = {color}")
        return color


def generate_header():
    page = "<link rel=\"stylesheet\" href=\"style.css\">"
    page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    page += "</head>"
    page += "<body style=\"background-color:white;\">"

    page += "<div class=\"navbar\">"
    page += "<a href=\"/\">Theme Park Wait Times</a>\n"
    page += "<div class=\"settings\">"
    page += "<a href=\"/settings.html\" class=\"settings\">&#x2699;</a>\n"
    page += "</div>"
    page += "</div>"
    return page
