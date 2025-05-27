"""
URL utilities for handling URL encoding and decoding.
Copyright 2024 3DUPFitters LLC
"""


def url_decode(input_string):
    """
    Decode URL-encoded strings
    
    Args:
        input_string: The URL-encoded string to decode
        
    Returns:
        The decoded string
    """
    input_string = input_string.replace('+', ' ')
    hex_chars = "0123456789abcdef"
    result = ""
    i = 0
    while i < len(input_string):
        if input_string[i] == "%" and i < len(input_string) - 2:
            hex_value = input_string[i + 1:i + 3].lower()
            if all(c in hex_chars for c in hex_value):
                result += chr(int(hex_value, 16))
                i += 3
                continue
        result += input_string[i]
        i += 1
    return result


def load_credentials():
    """
    Load WiFi credentials from secrets.py
    
    Returns:
        A tuple of (ssid, password)
    """
    try:
        from secrets import secrets
        return secrets['ssid'], secrets['password']
    except ImportError:
        return "", ""