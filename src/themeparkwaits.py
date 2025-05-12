#
# Theme Park Waits
# View information about ride wait times at any theme park
# Copyright 2024 3DUPFitters LLC
#
import sys
sys.path.append('/src/lib')
# import board
import gc
import asyncio
import mdns
import time
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
from src.color_utils import ColorUtils
from src.theme_park_api import set_system_clock_ntp
from src.theme_park_api import ThemeParkList
from src.theme_park_api import ThemePark
from src.theme_park_api import Vacation
from src.ErrorHandler import ErrorHandler
from src.theme_park_display import AsyncScrollingDisplay
from src.theme_park_api import MessageQueue
from src.theme_park_api import SettingsManager
from src.theme_park_api import load_credentials
from src.theme_park_api import url_decode
from src.webgui import generate_header
from src.theme_park_api import Timer
from src.ota_updater import OTAUpdater
from src.memory_tracker import MemoryTracker
import src.shopify_connect

logger = ErrorHandler("error_log")

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
BIT_DEPTH = 4
AUTO_REFRESH = True
#TIME_BETWEEN_UPDATES = 10 * 60
TIME_BETWEEN_UPDATES = 5 * 60

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

# Associate the RGB matrix with a Display
display_hardware = framebufferio.FramebufferDisplay(
    matrix, auto_refresh=AUTO_REFRESH, rotation=DISPLAY_ROTATION)
display_hardware.refresh(minimum_frames_per_second=0)

# Load settings from JSON file
settings = SettingsManager("../settings.json")

# Params for the next vacation, if set
vacation_date = Vacation()
vacation_date.load_settings(settings)

# The messages class contains a list of function calls
# to the local Display class, which in turn uses the displayio Display
display = AsyncScrollingDisplay(display_hardware, settings)
display.set_colors(settings)
SCROLL_DELAY = 4
messages = MessageQueue(display, SCROLL_DELAY, regen_flag=True)


def start_web_server(server, address):
    logger.debug("starting web server..")
    # startup the server
    try:
        #server.start(str(wifi.radio.ipv4_address), 80)
        server.start(str(address), 80)
        logger.debug("Listening on http://%s:80" % address)
    except OSError as e:
        time.sleep(5)
        logger.error(e, "Error starting web server, restarting device..")
        supervisor.reload()


#
# Scroll the user instructions on how to configure the wifi
# when it fails to connect.  This could be the first time,
# or if they change their wifi password, or move the box
# to a new location.
#
def run_setup_message(setup_text, repeat_count):
    #    local_portal = MatrixPortal(status_neopixel=board.NEOPIXEL, debug=True)
    #    local_display = SimpleScrollingDisplay(local_portal, settings)

    for i in range(repeat_count):
        try:
            display.show_scroll_message(setup_text)

            time.sleep(1)
            now = datetime.now()

        #except RuntimeError as e:
        except OSError as e:
            logger.error(e, "Error running setup message" )


async def try_wifi_until_connected():
    ssid, password = load_credentials()

    # Try to connect 3 times before giving up in
    # case the Wifi is unstable.
    attempts = 1
    if wifi.radio.connected is True:
        logger.debug(f"Already connected to wifi {ssid}: at {wifi.radio.ipv4_address}")
        return
    else:
        logger.debug(f"Connecting to wifi {ssid}: at {wifi.radio.ipv4_address}")

    while wifi.radio.connected is not True:
        try:
            setup_text1 = f"Connecting to Wifi:"
            setup_text2 = f"{ssid}"
            await display.show_centered(setup_text1, setup_text2, 2)
            wifi.radio.connect(ssid, password)
        except (RuntimeError) as e:
            logger.error(e,f"Wifi runtime error: {str(e)} at {wifi.radio.ipv4_address}")
            await display.show_scroll_message(f"Wifi runtime error: {str(e)}")
        except (ConnectionError) as e:
            logger.error(e, f"Wifi connection error: {str(e)} at {wifi.radio.ipv4_address}")
            if "Authentication" in str(e):
                await display.show_scroll_message(f"Bad password.  Please reset the LED scroller using the INIT button as described in the instructions.")
            else:
                await display.show_scroll_message(f"Wifi connection error: {str(e)}")
        except (ValueError) as e:
            logger.error(e, "Wifi value error")
            # logger.error(f"Wifi value error: {str(e)} at {wifi.radio.ipv4_address}")
            await display.show_scroll_message(f"Wifi value error: {str(e)}")

        except OSError as e:
            logger.error(e, "Unknown error connecting to Wifi")
#             #  Give it a couple of attempts to connect before reporting an error
#             # After that, delete the file containing the bad password and
#             # reset the box so the user can try the setup sequence again.
#             if attempts > 2:
#                 await display.show_centered("Bad password", "Resetting...", 3)
#                 try:
#                     os.remove("/secrets.py")
#                     supervisor.reload()
#                 except OSError:
#                     logger.critical("Wifi file secrets.py could not be deleted.")
#                     break
#             attempts = attempts + 1

#         if wifi.radio.connected is True:
#             logger.info(f"Connected to Wifi: {ssid} at {wifi.radio.ipv4_address}")
#         else:
#             logger.critical(f"Could not connect to Wifi: {ssid} at {wifi.radio.ipv4_address}")
#         display.off()


def configure_wifi():
    # Load Current Wifi Password
    ssid, password = load_credentials()

    #
    # True when first starting device or the Wifi has been reset
    #
    if ssid == "" and password == "":
        # Have to configure Wi-FI before the network will work
        # Run the Wifi configure GUI and the configure message at the same time
        try:
            wifimgr.start_access_point()
            wifimgr.start_web_server(settings)
            #wifimgr.web_server.serve_forever(str(wifi.radio.ipv4_address_ap))

            asyncio.run(asyncio.gather(
                wifimgr.run_web_server(is_wifi_password_configured),
                run_configure_wifi_message()
            ))

            wifimgr.web_server.stop()
            wifimgr.stop_access_point()

        except OSError as e:
            logger.error(e,"Exception starting wifi access point and web server: {e}")

    # Now that we've got an ssid and password, time to connect to
    # the network.
    asyncio.run(asyncio.gather(try_wifi_until_connected()))

# //TODO - Implement retries on updating the times
# import time
#
# def safe_get(requests, url, retries=3, delay=5):
#     for attempt in range(retries):
#         try:
#             response = requests.get(url)
#             return response
#         except OSError as e:
#             print(f"Request failed: {e}, retrying in {delay} seconds...")
#             time.sleep(delay)
#     return None
#
# if not wifi.radio.connected:
#     wifi.radio.connect(ssid, password)
#

async def run_configure_wifi_message():
    while is_wifi_password_configured() is False:
        setup_text1 = f"Connect your phone to Wifi channel {wifimgr.AP_SSID}, password \"{wifimgr.AP_PASSWORD}\"."
        setup_text2 = "  Then load page http://192.168.4.1"
        await display.show_centered(setup_text1, setup_text2, 1)


# Setup Global Sockets and Server
socket_pool = socketpool.SocketPool(wifi.radio)


def is_wifi_password_configured() -> bool:
    ssid, password = load_credentials()
    # logger.debug(f"SSID: {ssid} Password: {password}")
    is_configured = ssid != "" and password != ""
    return is_configured


# Create the HTTP session function to ensure proper context management
def create_http_session():
    """Create and return a new HTTP session with SSL context"""
    return adafruit_requests.Session(socket_pool, ssl.create_default_context())


# Initialize the global session
http_requests = create_http_session()
web_server = adafruit_httpserver.Server(socket_pool, "/static", debug=False)

# Prompt for wifi configure if not exists, and then configure
# wifi connection.
configure_wifi()

# Configure DNS so that users can configure at http://themeparkwaits.local
mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = settings.settings["domain_name"]
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)


# Function to check for DNS resolution issues
def check_internet_connectivity():
    """
    Checks if the device can resolve domain names. Returns True if able to resolve,
    False if not.
    """
    try:
        # Try to resolve a well-known domain using socket_pool instead of wifi.radio
        socket_pool.getaddrinfo("queue-times.com", 443)
        return True
    except OSError as e:
        # DNS resolution failed
        logger.error(e, "DNS resolution failed for queue-times.com")
        return False


# Function to reconnect wifi if needed
async def ensure_network_connectivity():
    """
    Ensures network connectivity is available, reconnecting if needed.
    Returns True if connectivity is restored, False otherwise.
    """
    # First check if we're already connected
    if wifi.radio.connected:
        # Test if DNS resolution works
        if check_internet_connectivity():
            return True

        # If we're connected but can't resolve DNS, try to reconnect
        logger.info("Connected to WiFi but DNS resolution failed, reconnecting...")
        try:
            wifi.radio.enabled = False
            await asyncio.sleep(2)
            wifi.radio.enabled = True
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(e, "Error cycling WiFi radio")

    # Try to reconnect to WiFi
    await try_wifi_until_connected()

    # Test connectivity again after reconnection attempt
    await asyncio.sleep(5)  # Give it time to establish DNS
    return check_internet_connectivity()


# Define function to recreate HTTP session
def recreate_http_session():
    """Recreate the HTTP session and return it"""
    global http_requests
    http_requests = create_http_session()
    logger.info("HTTP session recreated")
    return http_requests


# @TODO Convert to non-blocking
# https://docs.circuitpython.org/en/latest/shared-bindings/socketpool/index.html
#
async def update_live_wait_time():
    """Update live wait times for the current park, with proper error handling and session management"""
    if park_list.current_park.id <= 0:
        return

    # Max retries for connection errors
    max_retries = 3
    retry_count = 0

    while retry_count <= max_retries:
        # Ensure we have network connectivity before attempting HTTP requests
        network_ok = await ensure_network_connectivity()
        if not network_ok:
            logger.error("Network connectivity check failed, waiting before retry...")
            await display.show_scroll_message("Network DNS issues - trying to reconnect...")
            retry_count += 1
            if retry_count <= max_retries:
                await asyncio.sleep(5)  # Wait before retry
                continue
            else:
                logger.error("Max retries reached for network connectivity, giving up")
                return

        try:
            logger.info(f"About to start HTTP GET for Park {park_list.current_park.name}:{park_list.current_park.id}")
            local_url = park_list.current_park.get_url()
            logger.info(f"From URL: {local_url}")
            is_updated = False

            # Use the global session with proper context management
            with http_requests.get(local_url) as local_response:
                logger.info(f"Finished HTTP GET from {park_list.current_park.name}:{park_list.current_park.id}")
                logger.info(f"HTTP status code: {local_response.status_code}")
                if local_response.status_code is not 200:
                    logger.error(f"HTTP GET code {local_response.status_code} failed for {park_list.current_park.name}:{park_list.current_park.id}")
                else:
                    park_list.current_park.update(local_response.json())
                    is_updated = True
                    # Force garbage collection after JSON processing
                    run_garbage_collector()

            if is_updated is False:
                logger.error(f"HTTP GET failed for {park_list.current_park.name}:{park_list.current_park.id}")
            else:
                # Success, exit the retry loop
                break

        except (RuntimeError, OSError) as e:
            # Log the error
            error_type = "RuntimeError" if isinstance(e, RuntimeError) else "OSError"
            error_message = str(e)
            logger.error(e, f"{error_type}: Unable to update ride times: {error_message}")

            # Special handling for DNS resolution errors
            if "Name or service not known" in error_message or "gaierror" in error_message:
                logger.info("DNS resolution error detected, will attempt to reconnect network")
                await display.show_scroll_message("DNS error - reconnecting network...")
                # Don't recreate the session yet, first try to fix network connectivity
                await asyncio.sleep(2)
            else:
                # Close and recreate the session for other types of errors
                try:
                    # Create a new session (old one will be garbage collected)
                    recreate_http_session()
                except Exception as session_error:
                    logger.error(session_error, "Error recreating HTTP session")

            retry_count += 1
            if retry_count <= max_retries:
                logger.info(f"Retrying connection {retry_count}/{max_retries}...")
                await asyncio.sleep(3 * retry_count)  # Increasing backoff time
            else:
                logger.error("Max retries reached, giving up on update")
                await display.show_scroll_message("Unable to update ride times - network issues")

    # Force garbage collection after all network operations
    run_garbage_collector()


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
    logger.info(f"skip_closed is {settings.settings["skip_closed"]}")
    if settings.settings["skip_closed"] is True:
        page += "<label><input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\" Checked>Skip Closed Rides</label>"
    else:
        page += "<label><input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\">Skip Closed Rides</label>"
    # page += "<label for=\"skip_closed\">Skip Closed Rides</label>\n"
    page += "</div>\n"

    page += "<h2>Configure Countdown</h2>"
    page += "<div>"
    page += "<p>"
    page += "<label for=\"Name\">Event:</label>"
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

    # page += "<h2>Subscription</h2>"
    # page += "<div>"
    # page += "<p>"
    # page += "<label for=\"Name\">Email:</label>"
    # page += f"<input type=\"text\" name=\"email\" style=\"text-align: left;\" value=\"{settings.settings["email"]}\">"
    # page += "</p>"
    # page += "<p>"
    # page += "<label for=\"Status\">Status:</label>"
    # page += f"{settings.settings["subscription_status"]}"

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
            logger.debug(f"Name = {name} Value={value}")
            settings.settings[name] = value
        display.set_colors(settings)
        try:
            # Save the settings to disk
            settings.save_settings()
        # except OSError as e:
        except OSError as e:
            # logger.critical("Unable to save settings, drive is read only.")
            logger.error(e, "Unable to save settings, drive is read only.")

    # If they changed the name of the host, then we'll need to reboot
    if mdns_server.hostname != settings.settings["domain_name"]:
        web_server.stop()
        time.sleep(60)
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
    for scale in ["1.0", "0.9", "0.8", "0.7", "0.6", "0.5", "0.4", "0.3", "0.2"]:
        scale_display = round(float(scale) * 10)
        if scale == settings.settings.get("brightness_scale"):
            page += f"<option value=\"{scale}\" selected>{scale_display}</option>\n"
        else:
            page += f"<option value=\"{scale}\">{scale_display}</option>\n"
        page += "</p>"
    page += "</select>"

    page += "<p>"
    page += "<label for=\"Name\">Hostname:</label>"
    page += f"<input type=\"text\" name=\"domain_name\" style=\"text-align: left;\" value=\"{settings.settings["domain_name"]}\">.local"
    page += "</p>"
    page += """<p>
        <label for=\"Submit\"></label>
        <input type=\"submit\">
        </p>
        </form></div>"""
    page += "<p>Note: Changing the hostname can take up to five minutes to take effect. During this process the display will appear to be broken and non-responsive. <b>Please be patient and do not touch it until it comes back to life.</b></p>"

    page += """<p>
            <h2>Software</h2>
            </div>"""
    try:
        release = ota_updater.get_version("src")
        latest = ota_updater.get_latest_version()
        if latest == release:
            page += f"<p>The current installed version {release} is up to date.</p>"
        else:
            page += f"<p>The latest release \'{latest}\' is newer than the currently installed release \'{release}\'</p>"
            page += """<p><ol>
            <li>Click on the upgrade button below to download the latest release and install it.</li>
            <br>
            <li>The web GUI will immediately stop working.<li>
            <li>The LED will be unresponsive for 3-10 minutes. The screen will flash several times with random characters and <b>may go blank for up to 10 minutes</b>.</li>
            <br>
            <li><b>Do not turn the device off during the upgrade process.</b></li>
            <br>
            </ol>
            <br>
            <form action=\"/upgrade.html\" method=\"POST\">
            <p><button type="submit">Upgrade</button></p>
            </form>
            </div>
            """


    except ValueError as e:
        page += "<p>Unable to find latest software release on git code server.</p>"

    page += "</div><body>"

    run_garbage_collector()
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

        # See if the user set the email and update settings
        src.shopify_connect.parse_form_params(settings, str(request.query_params))

        # Get the subscription status
        # update_subscription_status(settings, http_requests)
        # Save the settings to disk
        try:
            settings.save_settings()
        except OSError as e:
            logger.error(e, "Unable to save settings, drive is read only.")

        request.query_params = ({})
        head = Headers({"Location": "/"})
        response = Response(request, "", headers=head, status=Status(302, "Moved temporarily"),
                            content_type="text/html")
        return response

    return adafruit_httpserver.Response(request, generate_main_page(), content_type="text/html")


TOKEN = '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'
# TOKEN='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'
GITHUBREPO = 'https://github.com/Czeiszperger/themeparkwaits.release'
ota_updater = OTAUpdater(http_requests, GITHUBREPO, main_dir="src", headers={'Authorization': 'TOKEN {}'.format(TOKEN)})
logger.debug(f"Release version is {ota_updater.get_version("src")}")


async def download_and_install_update_if_available():
    if ota_updater.update_available_at_boot() is True:
        # run_setup_message(f"Updating software. Do not unplug! 10  9  8  7  6  5  4  3  2  1", 1)
        ss, pp = src.theme_park_api.load_credentials()
        if ota_updater.install_update_if_available_after_boot(ss, pp) is True:
            await display.show_scroll_message("Updating software, the LED will be blank for 10 minutes or more.  Do not unplug!")
            logger.debug("Updated software, rebooting now...")
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
        except OSError as e:
            logger.error(e, "Problem in run_web_server")
            continue


async def network_monitor():
    """Periodically checks network connectivity and attempts to fix DNS issues"""
    last_check_time = 0
    check_interval = 60 * 30  # 30 minutes
    global web_server

    while True:
        current_time = time.monotonic()
        # Only check periodically to avoid unnecessary overhead
        if current_time - last_check_time > check_interval:
            last_check_time = current_time

            # Check connectivity only if connected to WiFi
            if wifi.radio.connected:
                network_ok = check_internet_connectivity()
                if not network_ok:
                    logger.info("Periodic network check: DNS resolution failed, attempting to recover")
                    # Attempt to fix network connectivity
                    try:
                        # Reset WiFi radio
                        wifi.radio.enabled = False
                        await asyncio.sleep(2)
                        wifi.radio.enabled = True
                        await asyncio.sleep(5)  # Wait for reconnection

                        # Recreate the HTTP session
                        recreate_http_session()
                        logger.info("Network recovery: WiFi reset and HTTP session recreated")
                        
                        # Reset the web server
                        if web_server is not None:
                            try:
                                web_server.stop()
                                web_server = adafruit_httpserver.Server(socket_pool, "/static", debug=False)
                            except Exception as e:
                                logger.error(e, "Error stopping web server")

                    except Exception as e:
                        logger.error(e, "Error during network recovery")

        await asyncio.sleep(5)  # Light sleep before checking conditions again


async def run_display():
    update_wait_time_timer = Timer(TIME_BETWEEN_UPDATES)
    while True:
        try:
            # The first time booting the app force the user to configure
            # a park and learn about the GUI.
            while park_list.current_park.is_valid() is False:
                logger.debug("Current park is invalid")
                messages.init()
                await display.show_scroll_message(f"Configure at: http://{settings.settings["domain_name"]}.local")

            # If the user has updated their settings the regenerate_flag will be true
            # and we need to redo the message queue.  The times also need to be updated
            # if the timer has gone off.
            if messages.regenerate_flag is True or update_wait_time_timer.finished() is True:
                update_wait_time_timer.reset()
                logger.debug(
                    f"regen_flag is {messages.regenerate_flag}, updating ride times for {park_list.current_park.name}")
                await update_ride_times_wrapper()

            mem_free = run_garbage_collector()
            if mem_free < 200000:
                logger.error(f"Low memory: {mem_free}")

            # Show the next message in the queue
            await messages.show()
            await asyncio.sleep(0)  # let other tasks run

        # except RuntimeError as e:
        except OSError as e:
            logger.error(e, "Exception in run_display()")


async def update_ride_times_wrapper():
    start_time = time.monotonic()
    messages.init()
    await display.show_splash(True)
    await display.show_update(True)
    await asyncio.sleep(4)
    await display.show_update(False)
    await display.show_required(True)
    await asyncio.sleep(4)

    # This could take up to 2 minutes depending on the
    # network and server load
    await update_live_wait_time()
    messages.regenerate_flag = False
    await asyncio.sleep(0)  # let other tasks run

    # sub_status = settings.settings["subscription_status"]
    # if sub_status is "Subscribed":
    #     await messages.add_rides(park_list)
    # else:
    #     messages.add_scroll_message(f"No subscription for email {settings.settings['email']}.")
    #     messages.add_scroll_message("Check subscription at themeparkwaits.com")

    await messages.add_rides(park_list)
    await messages.add_vacation(vacation_date)
    messages.add_scroll_message(f"Configure at: http://{settings.settings["domain_name"]}.local")
    await messages.add_splash(2)
    await display.show_required(False)
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    if elapsed_time > 120:
        logger.error(f"Updating wait times took {elapsed_time} seconds")
    await asyncio.sleep(1)  # let other tasks run


# Initialize the memory tracker at module level
memory_tracker = MemoryTracker("error_log")

def run_garbage_collector():
    """
    Run garbage collection and monitor memory usage using MemoryTracker.
    Returns the current free memory amount.
    """
    start_time = time.monotonic()
    
    # Use the memory tracker to collect garbage and check memory status
    memory_stats = memory_tracker.collect_and_check()
    mem_free = memory_stats["current_free"]
    
    end_time = time.monotonic()
    logger.info(f"Memory available: {mem_free} ({memory_stats['percent_free']:.1f}% of initial)")
    
    elapsed_time = end_time - start_time
    if elapsed_time > 2:
        logger.error(f"GC took {elapsed_time} seconds")
        
    return mem_free

async def periodically_update_ride_times():
    """
    If the user has selected a park, update the ride values ever so often.
    :return:
    """
   
    # See if the network is still working.  If not, reset everything 
    await network_monitor()
    
    while True:
        try:
            if park_list.current_park.is_open is True:
                await asyncio.sleep(600)
            else:
                await asyncio.sleep(3600)

            if len(park_list.current_park.rides) > 0:
                await update_ride_times_wrapper()


        except OSError as e:
            messages.init()
            messages.add_scroll_message("Unable to contact wait time server.  Will try again in 5 minutes.")
            logger.error(e, "OSError: Unable to contact wait time server")
        except RuntimeError as e:
            # logger.error(str(e))
            logger.error(e, "RuntimeError: Unable to contact wait time server")

try:
    # A list of all ~100 supported parks
    logger.debug("Preparing to update the park list from queue-times.com")
    url = "https://queue-times.com/parks.json"
    # response = http_requests.get(url)
    with http_requests.get(url) as response:
        park_list = ThemeParkList(response.json())
        logger.debug("Finished updating park list from queue-times.com")
        park_list.load_settings(settings)

except adafruit_requests.OutOfRetries as e:
    logger.error(e, "Caught exception OutOfRetries connecting to queue-times.com")
    asyncio.run(display.show_scroll_message("Unable to contact queue-times.com. Please verify Wifi network access."))
except OSError as e:
    logger.error(e, "Caught exception OSError connecting to queue-times.com")
    while True:
        asyncio.run(display.show_scroll_message("Unable to contact queue-times.com. Please verify Wifi network access and then restart the LED display."))

# Set device time from the internet
try:
    set_system_clock_ntp(socket_pool)
except OSError as e:
    logger.error(e, "Unable to contact time server")
    messages.add_scroll_message("Unable to contact time server.")

# Should only work if the user had previously called
# ota_updater.check_for_update_to_install_during_next_reboot()
asyncio.run(asyncio.gather(download_and_install_update_if_available()))

# Run garbage collection to get an early baseline of memory usage
run_garbage_collector()

# check to see if the user has paid for a subscription
# update_subscription_status(settings, http_requests)

# Start the web server GUI
start_web_server(web_server, wifi.radio.ipv4_address)

asyncio.run(asyncio.gather(
    run_display(),
    run_web_server(),
))

# Removed because updating ride times was blocking the display from running
# asyncio.run(asyncio.gather(
#     run_display(),
#     run_web_server(),
#     periodically_update_ride_times()
# ))
