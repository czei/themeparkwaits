

import board
import digitalio
import storage
import os


# See if we need to mount the drive read-only on the Matrix S3
# side so the computer side can edit files.
button_pin = board.BUTTON_DOWN  # Change this to the actual pin connected to your button

# Create a digital input object for the button
button = digitalio.DigitalInOut(button_pin)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP  # You may need to adjust the pull direction based on your circuit
drive_state = not button.value

# False makes the USB drive read-only to the computer
# storage.remount("/", False)
print(f"Drive mount logic is: {drive_state}")
storage.remount("/", drive_state)

def remove_file(filename):
    try:
        os.remove(filename)
    except OSError:
        print(f"File {filename} could not be deleted.")

# See if the user wants to reset the Wifi and default settings
button = digitalio.DigitalInOut(board.BUTTON_UP)
if button.value is False:
    remove_file("secrets.py")
    remove_file("settings.json")
    remove_file("error_log")



