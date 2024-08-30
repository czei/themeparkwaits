import asyncio
import re
import socketpool
import storage
import time
import wifi
import adafruit_logging as logging
import adafruit_httpserver
from adafruit_httpserver import (
    Status,
    REQUEST_HANDLED_RESPONSE_SENT,
    Request,
    Response,
    Headers,
    GET,
    POST,
    Server
)

logger = logging.getLogger('Test')
logger.setLevel(logging.ERROR)
#logger.setLevel(logging.DEBUG)
try:
   logger.addHandler(logging.FileHandler("error_log"))
except OSError:
   print("Read-only file system")


# extract access point mac address
mac_ap = ' '.join([hex(i) for i in wifi.radio.mac_address_ap])
mac_ap = mac_ap.replace('0x', '').replace(' ', '').upper()

# access point settings
AP_SSID = "WifiManager_" + mac_ap[5:10] + mac_ap[1:2]
AP_PASSWORD = "password"
# AP_AUTHMODES = [wifi.AuthMode.OPEN]
AP_AUTHMODES = [wifi.AuthMode.WPA2, wifi.AuthMode.PSK]

FILE_NETWORK_PROFILES = "../secrets.py"
ap_enabled = False
server_socket = None
web_server = Server(socketpool.SocketPool(wifi.radio), "/static", debug=False)


# Fixed a bug where SSIDs and passwords couldn't have spaces or non-alpha
# characters.
def url_decode(input_string):
    output_string = input_string.replace('+', ' ')
    hex_chars = "0123456789abcdef"
    result = ""
    i = 0
    while i < len(output_string):
        if output_string[i] == "%" and i < len(output_string) - 2:
            hex_value = output_string[i + 1:i + 3].lower()
            if all(c in hex_chars for c in hex_value):
                result += chr(int(hex_value, 16))
                i += 3
                continue
        result += output_string[i]
        i += 1
    return result


def do_connect(ssid, password):
    wifi.radio.enabled = True
    if wifi.radio.ap_info is not None:
        return None
    # print('Trying to connect to "%s"...' % ssid)
    try:
        wifi.radio.connect(ssid, password)
    except Exception as e:
        logger.error(f"Wifi connection error: {str(e)}")
        return False
    for retry in range(200):
        connected = wifi.radio.ap_info is not None
        if connected:
            break
        time.sleep(0.1)
        # print('.', end='')
    if connected:
        t = []
        t.append(str(wifi.radio.ipv4_address))
        t.append(str(wifi.radio.ipv4_subnet))
        t.append(str(wifi.radio.ipv4_gateway))
        t.append(str(wifi.radio.ipv4_dns))
        # print('\nConnected. Network config: IP: ', end='')
        # print('%s, subnet: %s, gateway: %s, DNS: %s' % tuple(t))

    # else:
    # print('\nFailed. Not Connected to: ' + ssid)
    return connected


def get_connection():
    """return a working wifi.radio connection or None"""

    while wifi.radio.ap_info is None:
        # first check if there already is any connection:
        if wifi.radio.ap_info is not None:
            # print('WiFi connection detected')
            return wifi.radio

        connected = False
        # connecting takes time, wait and retry
        time.sleep(3)
        if wifi.radio.ap_info is not None:
            # print('WiFi connection detected')
            return wifi.radio

        # read known network profiles from file
        # profiles = read_profiles()
        profiles = ""

        # search networks in range
        wifi.radio.enabled = True

        # networks are configured
        if (len(profiles)):
            networks = []
            for n in wifi.radio.start_scanning_networks():
                networks.append([n.ssid, n.bssid, n.channel, n.rssi, n.authmode])
            wifi.radio.stop_scanning_networks()

            for ssid, bssid, channel, rssi, authmodes in sorted(networks, key=lambda x: x[3], reverse=True):
                encrypted = 0
                authmodes_text = []
                for authmode in authmodes:
                    if (authmode == wifi.AuthMode.OPEN):
                        authmodes_text.append('Open')
                    elif (authmode == wifi.AuthMode.WEP):
                        authmodes_text.append('WEP')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.WEP):
                        authmodes_text.append('WPA')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.WPA):
                        authmodes_text.append('WPA')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.WPA2):
                        authmodes_text.append('WPA2')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.WPA3):
                        authmodes_text.append('WPA3')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.PSK):
                        authmodes_text.append('PSK')
                        encrypted = 1
                    elif (authmode == wifi.AuthMode.ENTERPRISE):
                        authmodes_text.append('ENTERPRISE')
                        encrypted = 1
                authmodes_text = ', '.join(authmodes_text)
                # print("Found \"%s\", #%d, %d dB, %s" % (ssid, channel, rssi, authmodes_text), end='')
                if ssid in profiles:
                    # print(", known")
                    if encrypted:
                        password = profiles[ssid]
                        connected = do_connect(ssid, password)
                    else:  # open
                        # print(", open")
                        connected = do_connect(ssid, None)
                # else:
                # print(", unknown")
                if connected:
                    break
        # no networks configured
        else:
            connected = start_ap()

    if connected:
        return wifi.radio


def start_web_server(settings):
    global web_server
    logger.debug("starting web server..")
    web_server.start(str(wifi.radio.ipv4_address_ap), 80)
    logger.debug("Listening on http://%s:80" % str(wifi.radio.ipv4_address_ap))


async def run_web_server(termination_func):
    global web_server
    logger.debug(f"Termination function is {termination_func()}")
    # If you want you can stop the server by calling server.stop() anywhere in your code
    while termination_func() is False and web_server.stopped is False:
        try:
            # Process any waiting HTTP requests
            web_server.poll()
            await asyncio.sleep(1)
        except OSError as error:
            logger.error(f"Web server loop stopped with error: {str(error)}")
            # traceback.print_exc()
            continue
    logger.debug(f"Exiting wifimgr:run_web_server()")


def handle_configure(client, request):
    global ap_enabled
    logger.debug('Handle configure start')
    # logger.debug("Request:", request.strip())
    match = re.search("ssid=([^&]*)", request)

    if match is None:
        response = construct_html_page()
        response = construct_html_page("You didn't select a wifi channel.  Please hit the back button and try again.")
        send_response(client, response, status_code=400)
        logger.error(f"handle_configure: missing password or wifi channel")
        return False

    match = re.search("&password=(.*)", request)
    if match is None:
        response = construct_html_page()
        response = construct_html_page("You didn't enter a password.  Please hit the back button and try again.")
        send_response(client, response, status_code=400)
        logger.error(f"handle_configure: missing password or wifi channel")
        return False

    # Fixed a bug where SSIDs and passwords couldn't have spaces or non alpha
    # characters.

    ssid = url_decode(match.group(1))
    password = url_decode(match.group(2))

    logger.info(f'Handling configure {ssid} : {password}')

    if len(ssid) == 0:
        send_response(client, "Please pick a wifi channel!", status_code=400)
        logger.error('Handling configure aborted, no wifi channel selected')
        return False

    write_result = write_profiles(ssid, password)
    if write_result is False:
        logger.error('Failed to write wifi settings to file.')

    if do_connect(ssid, password):
        try:
            profiles = read_profiles()
        except OSError:
            profiles = {}
        write_result = write_profiles(ssid, password)
        response = get_new_html_head() + """\
      <p>
            """
        response = response + """\
       Successfully connected to the WiFi network "%(ssid)s".
            """ % dict(ssid=ssid)

    if write_result is False:
        logger.error('Failed to write wifi settings to file.')
        response = response + """\
    <br><br>
    Failed to save changes.
            """
        response = response + """\
      </p>
            """
        response = response + get_html_footer()
        send_response(client, response)
        time.sleep(30)
        if write_result:
            if ap_enabled:
                wifi.radio.stop_ap()
                ap_enabled = False
                # print('Access point stopped')
            time.sleep(5)
            # print('Handle configure end, connected')
        # to require write success:
        # else:
        #   wifi.radio.stop_station()
        #   print('Handle configure end, connected and disconnected')
        # return write_result
    else:

        response = get_new_html_head()
        response = response + """\
        <h1>Could not connect to the WiFi network "%(ssid)s", probably because the password is incorrect.</h1>
         <form>
          <div>
           <input type="button" value="Go back" onclick="history.back()">
         </div>
        </form>
            """ % dict(ssid=ssid)
        response = response + get_html_footer()
        send_response(client, response)
        # print('Handle configure ended, no connection')
        return False


def handle_not_found(client, url):
    send_response(client, "Path not found: {}".format(url), status_code=404)


def get_html_footer():
    return """\
     <p class="footer">
     Inspired by this library: 
      <a href="https://github.com/dotpointer/circuitpython_wifimanager"
       target="_blank" rel="noopener">dotpointer/circuitpython_wifimanager</a>
      <p>
    </body>
    </html>
        """


def get_new_html_head():
    data = """\
    <!DOCTYPE html>
    <html>
    <head>
    <title>TPW Wi-Fi Setup</title>
    <style>
    """
    f = open("src/wifi_style.css")
    data = data + f.read()
    f.close()
    data = data + """\
    </style>
    </head>
    <body>
    <h1>Wi-Fi Client Setup</h1>
    <hr>
    """
    return data


@web_server.route("/", [POST])
def base(request: Request):
    logger.debug("Wifi GUI webserver handing POST to /")

    ssid = ""
    password = ""
    for name, value in request.form_data.items():
        if name is "network":
            ssid = url_decode(value)
        if name is "password":
            password = url_decode(value)

    logger.debug(f"Network = {ssid} Password={password}")
    if ssid != "" and password != "":
        write_profiles(ssid,password)

    response = get_new_html_head()
    response += """
    <div><p>Network configuration accepted.  Attempting to connect to Wifi Network.</p></div>
    """
    response = response + get_html_footer()
    return adafruit_httpserver.Response(request, response, content_type="text/html")

@web_server.route("/", [GET])
def base(request: Request):
    logger.debug("Wifi GUI webserver handing GET call to /")

    wifi.radio.enabled = True
    networks = []
    for n in wifi.radio.start_scanning_networks():
        # logger.debug("Found \"%s\", #%s" % (n.ssid, n.channel))
        networks.append([n.ssid, n.channel])

    wifi.radio.stop_scanning_networks()
    response = get_new_html_head()
    response = response + """\
          <form action="/" method="post">
           <div class="network">
           <label for="network">Choose Wifi Network:</label>
           <br>
           <select class="dropdown" id="network" name="network">"""

    while len(networks):
        network = networks.pop(0)
        response = response + """
                <option value="{0}">{0}</option>
                """.format(network[0])

    response = response + """\
            </select>
            <div class="password"><label>Password:</label> <input class="text" name="password" type="password" ></div>
            <div class=button_container>
            <p><button>Connect</button></p></div>
            </div>
            <br>
            </form>
            """

    if storage.getmount('/').readonly:
        response = response + """\
          <p>Warning, the file system is in read-only mode, settings will not be saved.</p>
                """
    response = response + get_html_footer()
    return adafruit_httpserver.Response(request, response, content_type="text/html")


def sendall(client, data):
    data = data.replace('  ', ' ')
    while len(data):
        # split data in chunks to avoid EAGAIN exception
        part = data[0:512]
        data = data[len(part):len(data)]
        # print('Sending: ' + str(len(part)) + 'b')
        # EAGAIN too much data exception catcher
        while True:
            try:
                client.sendall(part)
            except OSError as e:
                logger.error(f"Wifi error: {str(e)} in sendall()")
                time.sleep(0.25)
                pass
            break


def handle_root(client):
    # print('Handle / start')
    wifi.radio.enabled = True

    networks = []
    for n in wifi.radio.start_scanning_networks():
        # print("Found \"%s\", #%s" % (n.ssid, n.channel))
        networks.append([n.ssid, n.channel])
    wifi.radio.stop_scanning_networks()
    send_header(client)
    sendall(client, get_new_html_head())
    sendall(client, """\
      <form action="configure" method="post">
       <div class="network">
       <label for="network">Choose Wifi Network:</label>
       <br>
       <select class="dropdown" id=network" name=network">
        """)
    while len(networks):
        network = networks.pop(0)
        sendall(client, """\
            <option value="{0}">{0}</option>
            """.format(network[0]))

    sendall(client, """\
            </select>
            <div class="password"><label>Password:</label> <input class="text" name="password" type="password" ></div>
            <div class=button_container>
            <p><button>Connect</button></p></div>
            </div>
            <br>
            </form>
            """)

    if storage.getmount('/').readonly:
        sendall(client, """\
      <p>Warning, the file system is in read-only mode, settings will not be saved.</p>
            """)
    else:
        sendall(client, """\
      <p>
       The SSID and password will be saved in the
       "%(filename)s" on the device.
      </p>
            """ % dict(filename=FILE_NETWORK_PROFILES))
    sendall(client, get_html_footer())
    client.close()
    # print('Handle / end')


def read_profiles():
    profiles = {}
    import secrets
    print(secrets.secrets['password'])
    try:
        profiles[secrets.secrets['ssid']] = secrets.secrets['password']
        # profiles[ssid] = password
    except OSError as e:
        logger.error(f"Error: {str(e)} reading secrets file.")
        profiles = {}
    return profiles


def send_header(client, status_code=200, content_length=None):
    sendall(client, "HTTP/1.0 {} OK\r\n".format(status_code))
    sendall(client, "Content-Type: text/html\r\n")
    if content_length is not None:
        sendall(client, "Content-Length: {}\r\n".format(content_length))
    sendall(client, "\r\n")


def send_response(client, payload, status_code=200):
    content_length = len(payload)
    send_header(client, status_code, content_length)
    if content_length > 0:
        sendall(client, payload)
    client.close()


def start_access_point(port=80):
    global ap_enabled, server_socket, AP_AUTHMODES

    wifi.radio.enabled = True
    if ap_enabled is False:
        # to use encrypted AP, use authmode=[wifi.AuthMode.WPA2, wifi.AuthMode.PSK]
        if (AP_AUTHMODES[0] == wifi.AuthMode.OPEN):
            wifi.radio.start_ap(ssid=AP_SSID, authmode=AP_AUTHMODES)
        else:
            wifi.radio.start_ap(ssid=AP_SSID, password=AP_PASSWORD, authmode=AP_AUTHMODES)
        ap_enabled = True


def stop_access_point():
    global ap_enabled
    wifi.radio.stop_ap()
    ap_enabled = False


def start_ap(port=80):
    global ap_enabled, server_socket

    addr = socketpool.SocketPool(wifi.radio).getaddrinfo('0.0.0.0', port)[0][-1]

    if server_socket:
        server_socket.close()
        server_socket = None

    wifi.radio.enabled = True

    if ap_enabled is False:
        # to use encrypted AP, use authmode=[wifi.AuthMode.WPA2, wifi.AuthMode.PSK]
        if (AP_AUTHMODES[0] == wifi.AuthMode.OPEN):
            wifi.radio.start_ap(ssid=AP_SSID, authmode=AP_AUTHMODES)
        else:
            wifi.radio.start_ap(ssid=AP_SSID, password=AP_PASSWORD, authmode=AP_AUTHMODES)
        ap_enabled = True

    server_socket = socketpool.SocketPool(wifi.radio).socket()
    server_socket.bind(addr)
    server_socket.listen(1)
    if storage.getmount('/').readonly:
        logger.debug('File system is read only')
    else:
        logger.debug('File system is writeable')
    # print('Access point started, connect to WiFi "' + AP_SSID + '"', end='')
    # if (AP_AUTHMODES[0] != wifi.AuthMode.OPEN):
    # print(', the password is "' + AP_PASSWORD + '"')
    # else:
    # print('')
    logger.debug('Visit http://' + str(wifi.radio.ipv4_address_ap) + '/ in your web browser')

    while True:
        if wifi.radio.ap_info is not None:
            # print('WiFi connection detected')
            if ap_enabled:
                wifi.radio.stop_ap()
                ap_enabled = False
                # print('Access point stopped')
            return True

        # EAGAIN exception catcher
        while True:
            try:
                client, addr = server_socket.accept()
            except OSError as e:
                logger.error(f"Wifi error: {str(e)} at {wifi.radio.ipv4_address}")
                time.sleep(0.25)
            break

        logger.debug('Client connected - %s:%s' % addr)
        try:
            client.settimeout(5)

            request = b""
            try:
                while "\r\n\r\n" not in request:
                    buffer = bytearray(512)
                    client.recv_into(buffer, 512)
                    request += buffer
                    logger.debug('Received data')
            except OSError as e:
                logger.error(f"Web server http error: {str(e)}")

            # Handle form data from Safari on macOS and iOS; it sends \r\n\r\nssid=<ssid>&password=<password>
            try:
                buffer = bytearray(1024)
                client.recv_into(buffer, 1024)
                request += buffer
                logger.debug("Received form data after \\r\\n\\r\\n(i.e. from Safari on macOS or iOS)")
            except OSError as e:
                logger.error(f"Web server http error: {str(e)}")

            request = request.decode().strip("\x00").replace('%23', '#')

            # print("Request is: {}".format(request))
            if "HTTP" not in request:  # skip invalid requests
                continue

            url = re.search("(?:GET|POST) (.*?)(?:\\?.*?)? HTTP", request).group(1)
            # print("URL is {}".format(url))

            if url == "/":
                handle_root(client)
            elif url == "/configure":
                handle_configure(client, request)
            else:
                handle_not_found(client, url)

        finally:
            client.close()

    # Make sure other people can run a web server on the same
    # machine.
    server_socket.close()
    client.close()

def write_profiles(ssid, password):
    logger.debug('Write profiles start')
    logger.debug('Preparing line for "' + ssid + '"')
    lines = []
    lines.append("secrets = {\n")
    lines.append(f"\'ssid' : \'{ssid}\',\n")
    lines.append(f"\'password' : \'{password}\',\n")
    lines.append("}\n")
    try:
        logger.debug('Writing ' + FILE_NETWORK_PROFILES)
        with open(FILE_NETWORK_PROFILES, "w") as f:
            f.write(''.join(lines))
            f.close()
        return True
    except OSError as e:
        logger.error(f"Error writing secrets.py to disk: {str(e)}")
        return False


def construct_html_page(message):
    response = get_new_html_head() + "<p>"
    response = response + message
    response = response + "</p>"
    response = response + get_html_footer()
    return response
