#
# Theme Park Waits
# View information about ride wait times at any theme park
# Copyright 2024 3DUPFitters LLC
#
import board
import asyncio
import mdns
import time
import traceback
import wifi
import ssl
import socketpool
import displayio
import rgbmatrix
import framebufferio
import adafruit_requests
import adafruit_httpserver
from adafruit_datetime import datetime

from adafruit_httpserver import (
    Status,
    REQUEST_HANDLED_RESPONSE_SENT,
    Request,
    Response,
    Headers,
    GET,
    POST
)
from adafruit_matrixportal.matrixportal import MatrixPortal

from src import theme_park_api, wifimgr
from src.theme_park_api import set_system_clock, ColorUtils, MatrixPortalDisplay
from src.theme_park_api import ThemeParkList
from src.theme_park_api import ThemePark
from src.theme_park_api import Vacation
from src.theme_park_api import AsyncScrollingDisplay
from src.theme_park_api import MessageQueue
from src.theme_park_api import SettingsManager
from src.theme_park_api import load_credentials
from src.webgui import generate_header
from src.ota_updater import OTAUpdater

try:
    import board
except (ModuleNotFoundError, NotImplementedError):
    # Mocking the unavailable modules in non-embedded environments
    # You can add more according to your needs, these are just placeholders

    class Board:
        def __init__(self):
            self.MTX_R1 = 0
            self.MTX_G1 = 0
            self.MTX_B1 = 0
            self.MTX_R2 = 0
            self.MTX_G2 = 0
            self.MTX_B2 = 0
            self.MTX_ADDRA = 0
            self.MTX_ADDRB = 0
            self.MTX_ADDRC = 0
            self.MTX_ADDRD = 0
            self.MTX_CLK = 0
            self.MTX_LAT = 0
            self.MTX_OE = 0

try:
    import src.wifimgr
except (ModuleNotFoundError, NotImplementedError):
    wifimgr.get_connection.return_value = None

# We don't want autoreload during development, but it
# may be useful in the field to recover after an unanticipated
# error.
import supervisor

supervisor.runtime.autoreload = False

# Display Setup first in case any error messages
# Need to be displayed
displayio.release_displays()
DISPLAY_WIDTH = 64
DISPLAY_HEIGHT = 32
DISPLAY_ROTATION = 0
BIT_DEPTH = 6
AUTO_REFRESH = True

matrix = rgbmatrix.RGBMatrix(
    width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, bit_depth=BIT_DEPTH,
    rgb_pins=[
        board.MTX_R1,
        board.MTX_G1,
        board.MTX_B1,
        board.MTX_R2,
        board.MTX_G2,
        board.MTX_B2],
    addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
    tile=1,
    serpentine=False,
    doublebuffer=True)

# Associate the RGB matrix with a Display so we can use displayio
display_hardware = framebufferio.FramebufferDisplay(
    matrix, auto_refresh=AUTO_REFRESH, rotation=DISPLAY_ROTATION)
display_hardware.refresh(minimum_frames_per_second=0)

# Load settings from JSON file
settings = SettingsManager("../settings.json")

# Params for the next vacation, if set
vacation_date = Vacation()
vacation_date.load_settings(settings)


#
# Scroll the user instructions on how to configure the wifi
# when it fails to connect.  This could be the first time,
# or if they change their wifi password, or move the box
# to a new location.
#
def run_setup_message(setup_text, repeat_count):
    # print("Starting Wifi Configure message")

    local_portal = MatrixPortal(status_neopixel=board.NEOPIXEL, debug=True)
    local_display = MatrixPortalDisplay(local_portal, settings)

    for i in range(repeat_count):
        try:
            local_display.sync_show_scroll_message(setup_text)
            time.sleep(1)
            now = datetime.now()
            # print(f"The current time:  {now.hour}:{now.minute}")

        except RuntimeError:
            traceback.print_exc()


# Setup WI-FI Password
ssid, password = load_credentials()

#
# True when first starting device or the Wifi has been reset
#
if ssid == "" and password == "":
    setup_text = f"Connect your phone to Wifi channel {wifimgr.AP_SSID}, password \"{wifimgr.AP_PASSWORD}\"."
    setup_text += "  Then load page http://192.168.4.1 to configure Wifi"
    run_setup_message(setup_text, 1)

    try:
        if wifimgr.get_connection() is not None:
            wifi.radio.connect(ssid, password)

    except (RuntimeError, ConnectionError, ValueError):
        traceback.print_exc()
    finally:
        supervisor.reload()
#
# The Wifi credentials already existed
#
else:
    try:
        wifi.radio.connect(ssid, password)
    except (RuntimeError, ConnectionError, ValueError):
        while wifi.radio.connected is not True:
            setup_message = "Press the Reboot Button and then hold down Reset Wifi Button until the LED lights up"
            run_setup_message(setup_message, 100000)

# print(f"Connected to Wifi: {ssid} at {wifi.radio.ipv4_address}")

# The messages class contains a list of function calls
# to the local Display class, which in turn uses the displayio Display
display = AsyncScrollingDisplay(display_hardware, settings)
display.set_colors(settings)
SCROLL_DELAY = 4
messages = MessageQueue(display, SCROLL_DELAY, regen_flag=True)

# Setup Global Sockets and Server
socket_pool = socketpool.SocketPool(wifi.radio)
http_requests = adafruit_requests.Session(socket_pool, ssl.create_default_context())
web_server = adafruit_httpserver.Server(socket_pool, "/static", debug=False)

# Configure DNS so that users can configure at http://themeparkwaits.local
mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = settings.settings["domain_name"]
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)


async def update_live_wait_time():
    if park_list.current_park.id <= 0:
        return
    print(f"Updating Park {park_list.current_park.name}:{park_list.current_park.id}")
    local_url = park_list.current_park.get_url()
    print(f"From URL: {url}")
    # print(f"Updating Park from URL: {url}")
    local_response = http_requests.get(local_url)
    json_response = local_response.json()
    park_list.current_park.update(json_response)


def generate_main_page():
    page = generate_header()
    page += "<br>"
    page += "<h2>Choose a Park</h2>"
    page += "<div>"
    page += "<form action=\"/\" method=\"GET\">"
    page += "<p><select name=\"park-id\" id=\"park-id\">\n"
    for park in park_list.park_list:
        park_name = park.name

        if park.id == park_list.current_park.id:
            page += f"<option value=\"{park.id}\" selected>{park_name}</option>\n"
        else:
            page += f"<option value=\"{park.id}\">{park_name}</option>\n"
    page += "</select></p>"

    page += "<p><label for=\"Name\"></label></p>"
    page += "</div>"

    # page += "<div style=\"display: flex; align-items: center;\">"
    page += "<div class=\"myCheckbox\">\n"
    if settings.settings["skip_meet"] is True:
        page += "<label><input class=\"myCheckbox\" type=\"checkbox\" id=\"skip_meet\" name=\"skip_meet\" Checked>Skip Character Meets</label>\n"
    else:
        page += "<label><input class=\"myCheckbox\" type=\"checkbox\" id=\"skip_meet\" name=\"skip_meet\">Skip Character Meets</label>\n"
    page += "</div>\n"

    page += "<div class=\"myCheckbox\">\n"
    print(f"skip_closed is {settings.settings["skip_closed"]}")
    if settings.settings["skip_closed"] is True:
        page += "<label><input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\" Checked>Skip Closed Rides</label>"
    else:
        page += "<label><input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\">Skip Closed Rides</label>"
    # page += "<label for=\"skip_closed\">Skip Closed Rides</label>\n"
    page += "</div>\n"

    page += "<h2>Configure Vacation</h2>"
    page += "<div>"
    page += "<p>"
    page += "<label for=\"Name\">Park:</label>"
    page += f"<input type=\"text\" name=\"Name\" style=\"text-align: left;\" value=\"{vacation_date.name}\">"
    page += "</p>"

    page += "<p>"
    page += "<label for=\"Date\">Date:</label>"
    page += "<select id=\"Year\" name=\"Year\">"
    year_now = datetime.now().year
    for year in range(year_now, 2044):
        if vacation_date.is_set() is True and year == vacation_date.year:
            page += f"<option value=\"{year}\" selected>{year}</option>\n"
        else:
            page += f"<option value=\"{year}\">{year}</option>\n"
    page += "</select>"

    page += "<select id=\"Month\" name=\"Month\">"
    for month in range(1, 13):
        if vacation_date.is_set() is True and month == vacation_date.month:
            page += f"<option value=\"{month}\" selected>{month}</option>\n"
        else:
            page += f"<option value=\"{month}\">{month}</option>\n"
    page += "</select>"

    page += "<select id=\"Day\" name=\"Day\">"
    for day in range(1, 32):
        if vacation_date.is_set() is True and day == vacation_date.day:
            page += f"<option value=\"{day}\" selected>{day}</option>\n"
        else:
            page += f"<option value=\"{day}\">{day}</option>\n"
    page += "</select>"
    page += "</p>"

    page += "<p>"
    page += "</p>"

    page += "<p>"
    page += "<label for=\"Submit\"></label>"
    page += "<input type=\"submit\">"
    page += "</p>"
    page += "</form>"
    page += "</div>"
    page += "<body>"
    return page


@web_server.route("/style.css")
def base(request: Request):
    f = open("src/style.css")
    data = f.read()
    f.close()
    return adafruit_httpserver.Response(request, data, content_type="text/html")


@web_server.route("/upgrade.html", [POST])
def base(request: Request):
    ss, pp = load_credentials()
    #   #ota_updater.install_update_if_available_after_boot(ss,pp)
    ota_updater.check_for_update_to_install_during_next_reboot()

    # Reboot device
    supervisor.reload()


@web_server.route("/settings.html", [GET, POST])
def base(request: Request):
    # Parse new settings
    if request.method == POST:
        for name, value in request.form_data.items():
            settings.settings[name] = value
        display.set_colors(settings)
        try:
            # Save the settings to disk
            settings.save_settings()
        except OSError:
            print("Unable to save settings, drive is read only.")

    # If they changed the name of the host, then we'll need to reboot
    if mdns_server.hostname != settings.settings["domain_name"]:
        supervisor.reload()

    page = generate_header()
    page += """
    <h2>Settings</h2>
    <div>
    <form action=\"/settings.html\" method=\"POST\">"""

    for color_setting_name, color_value in settings.settings.items():
        if "color" in color_setting_name:
            page += "<p>"
            page += f"<label for=\"Name\">{SettingsManager.get_pretty_name(color_setting_name)}</label>"
            page += ColorUtils.html_color_chooser(color_setting_name, hex_num_str=color_value)
            page += "</p>"

    page += """<p>
            <label for=\"Name\">Scroll Speed</label>
            <select name=\"scroll_speed\" id=\"scroll_speed\">"""
    for speed in ["Slow", "Medium", "Fast"]:
        if speed == settings.settings.get("scroll_speed"):
            page += f"<option value=\"{speed}\" selected>{speed}</option>\n"
        else:
            page += f"<option value=\"{speed}\">{speed}</option>\n"
        page += "</p>"
    page += "</select>"

    page += """<p>
            <label for=\"Name\">Brightness</label>
            <select name=\"brightness_scale\" id=\"brightness_scale\">"""
    for scale in ["1.0", "0.9", "0.8", "0.7", "0.6", "0.5", "0.4","0.3", "0.2"]:
        print(f"Scale value is {float(scale) * 10}")
        scale_display = round(float(scale) * 10)
        if scale == settings.settings.get("brightness_scale"):
            page += f"<option value=\"{scale}\" selected>{scale_display}</option>\n"
        else:
            page += f"<option value=\"{scale}\">{scale_display}</option>\n"
        page += "</p>"
    page += "</select>"

    #page += "<h2>Configure </h2>"
    #page += "<div>"
    page += "<p>"
    page += "<label for=\"Name\">Hostname:</label>"
    page += f"<input type=\"text\" name=\"domain_name\" style=\"text-align: left;\" value=\"{settings.settings["domain_name"]}\">"
    page += "</p>"

    page += """<p>
        <label for=\"Submit\"></label>
        <input type=\"submit\">
        </p>
        </form>"""

    try:
        release = ota_updater.get_version("src")
        latest = ota_updater.get_latest_version()
        if latest == release:
            page += f"<p>The current installed version {release} is up to date.</p>"
        else:
            page += f"<p>The latest release \'{latest}\' is newer than the currently installed release \'{release}\'</p>"
            page += """<p><ol>
            <li>Click on the upgrade button below to download the latest release and install it.</br></li>  
            <br>
            <li>The LED will be unresponsive for 3-10 minutes. The screen will flash several times with random characters, do not be alarmed.</li>
            <br>
            <li><b>Do not turn the device off during the upgrade process.</b></li>
            <br>
            </ol>
            <br>
            <form action=\"/upgrade.html\" method=\"POST\">
            <p><button type="submit">Upgrade</button></p>
            </form>
            """


    except ValueError as e:
        page += "<p>Unable to find latest software release on git code server.</p>"

    page += "</div><body>"
    return adafruit_httpserver.Response(request, page, content_type="text/html")


@web_server.route("/", [GET])
def base(request: Request):
    if len(request.query_params) > 0:
        vacation_date.parse(str(request.query_params))
        park_list.parse(str(request.query_params))
        park_list.store_settings(settings)

        if vacation_date.is_set() is True:
            vacation_date.store_settings(settings)

        # This # triggers the messages to reload with new info.
        messages.regenerate_flag = True

        try:
            # Save the settings to disk
            settings.save_settings()
        except OSError:
            print("Unable to save settings, drive is read only.")

        request.query_params = ({})
        head = Headers({"Location": "/"})
        response = Response(request, "", headers=head, status=Status(302, "Moved temporarily"),
                            content_type="text/html")
        return response

    return adafruit_httpserver.Response(request, generate_main_page(), content_type="text/html")


def start_web_server(wserver):
    print("starting server..")
    # startup the server
    try:
        wserver.start(str(wifi.radio.ipv4_address), 80)
        print("Listening on http://%s:80" % wifi.radio.ipv4_address)
    except OSError:
        time.sleep(5)
        print("restarting device..")
        supervisor.reload()




TOKEN = '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'
# TOKEN='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'
GITHUBREPO = 'https://github.com/Czeiszperger/themeparkwaits.release'
ota_updater = OTAUpdater(http_requests, GITHUBREPO, main_dir="src", headers={'Authorization': 'TOKEN {}'.format(TOKEN)})
print(f"Release version is {ota_updater.get_version("src")}")


def download_and_install_update_if_available():
    if ota_updater.update_available_at_boot() is True:
        # run_setup_message(f"Updating software. Do not unplug! 10  9  8  7  6  5  4  3  2  1", 1)
        ss, pp = src.theme_park_api.load_credentials()
        if ota_updater.install_update_if_available_after_boot(ss, pp) is True:
            print("Updated software, rebooting now...")
            supervisor.reload()


async def run_web_server():
    while True:
        try:
            # Process any waiting requests
            pool_result = web_server.poll()
            await asyncio.sleep(.2)
            if pool_result == REQUEST_HANDLED_RESPONSE_SENT:
                # Do something only after handling a request
                pass

        # If you want you can stop the server by calling server.stop() anywhere in your code
        except OSError as error:
            print(error)
            traceback.print_exc()
            continue


async def run_display():
    while True:
        try:
            # print(f"Messages regen_flag is {messages.regenerate_flag}")
            # print(f"Park valid flag is {current_park.is_valid()}")
            if park_list.current_park.is_valid() is False:
                messages.init()
                messages.add_scroll_message(f"Configure at: http://{settings.settings["domain_name"]}.local")
            elif messages.regenerate_flag is True and park_list.current_park.is_valid() is True:
                messages.init()
                await update_live_wait_time()
                messages.add_scroll_message(f"Configure at: http://{settings.settings["domain_name"]}.local")
                await messages.add_rides(park_list)
                await messages.add_vacation(vacation_date)
                messages.regenerate_flag = False

            await messages.show()
            await asyncio.sleep(0)  # let other tasks run

        except RuntimeError:
            traceback.print_exc()


async def update_ride_times():
    """
    If the user has selected a park, update the ride values ever so often.
    :return:
    """
    while True:
        try:
            if park_list.current_park.is_open is True:
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(3600)

            if len(park_list.current_park.rides) > 0:
                await update_live_wait_time()
                messages.init()
                await messages.add_vacation(vacation_date)
                await messages.add_rides(park_list)

        except OSError as e:
            print("Caught exception OSError:", e)
            messages.init()
            messages.add_scroll_message("Unable to contact wait time server.  Will try again in 5 minutes.")
        except RuntimeError:
            traceback.print_exc()


try:
    # A list of all ~80 supported parks
    url = "https://queue-times.com/parks.json"
    response = http_requests.get(url)
    json_response = response.json()
    park_list = ThemeParkList(json_response)
    park_list.load_settings(settings)
except OSError as e:
    print("Caught exception OSError:", e)
    messages.init()
    messages.add_scroll_message("Unable to contact queue-times.com.  Will try again in 5 minutes.")

# Set device time from the internet
try:
    set_system_clock(http_requests)
except OSError as e:
    print("Caught exception OSError:", e)
    messages.add_scroll_message("Unable to contact time server.")

# Should only work if the user had previously called
# ota_updater.check_for_update_to_install_during_next_reboot()
download_and_install_update_if_available()

# Start the web server GUI
start_web_server(web_server)

asyncio.run(asyncio.gather(
    run_display(),
    run_web_server(),
    update_ride_times()
))
