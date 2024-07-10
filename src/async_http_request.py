import asyncio
import ssl
import socket


async def async_read_url(domain, path):
    """
    :param domain: www.host.com
    :param path:  Example:  /data.json
    :return: The header:str and body:byte
    """
    request = f"GET {path} HTTP/1.1\r\nHost: {domain}\r\n\r\n"
    print(f"Getting URL {request}")
    reader, writer = await asyncio.open_connection(domain, 443, ssl=ssl.create_default_context())
    # reader, writer = await asyncio.open_connection(domain, 443)
    writer.write(request.encode('latin-1'))
    header = await read_http_header(reader)
    body = ""
    if parse_http_content_length(header) > 0:
        body = await read_http_body(reader, header)
    else:
        body = await read_http_chunked_body(reader)

    writer.close()
    await writer.wait_closed()
    return header, body


async def read_http_body(reader, header):
    size = parse_http_content_length(header)
    print(f"Body Size={size}")
    body = await reader.readexactly(size)
    return body


async def read_http_chunked_body(reader):
    data = b''
    while True:
        # read size of chunk
        chunk_size_line = await reader.readline()
        chunk_size = int(chunk_size_line.strip(), 16)

        if chunk_size == 0:
            break  # we read all the data

        # read chunk of data
        chunk = await reader.readexactly(chunk_size)
        data += chunk

        # read end of chunk CRLF
        await reader.readexactly(2)
    return data


def parse_http_content_length(header_str):
    lines = header_str.split('\n')
    for line in lines:
        if line.lower().startswith("content-length"):
            return int(line.split(": ")[1])
    return 0


async def read_http_header(reader):
    header = ""
    while True:
        line = await reader.readline()
        header += line.decode("utf-8")
        if not line:
            break
        if "\r\n\r\n" in header:
            break
    return header


async def old_read_http_header(sock):
    headers = ""
    while True:
        # Receive data from the socket
        data = sock.recv(1)

        # Convert byte to string
        data = data.decode("utf-8")
        headers += data

        # Check for double newline (empty line in HTTP protocol signifies end of headers)
        if "\r\n\r\n" in headers:
            break

    return headers


def get_domain_from_url(url):
    start = url.find("://")
    if start == -1:  # If the URL does not contain a protocol
        start = 0
    else:
        start += 3  # Skip over :// in http:// or https://

    # Find end of domain
    end = url.find("/", start)
    if end == -1:  # If the URL does not contain a path
        end = len(url)

    return url[start:end]


def get_path_from_url(url):
    protocol_end_index = url.find('://')  # Find the protocol separator
    if protocol_end_index != -1:
        domain_start_index = protocol_end_index + 3  # Shift to the end of '://'
    else:
        domain_start_index = 0  # If no protocol is given, we assume the URL starts with the domain

    path_start_index = url.find('/', domain_start_index)  # Find the start of the path
    if path_start_index != -1:
        return url[path_start_index:]  # If we have a path, return that
    else:
        return '/'  # If no path was found, we return '/' to signify the root
