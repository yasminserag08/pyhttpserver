import socket
import os
from request import HTTPRequest

MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.txt': 'text/plain'
}

# Create a socket IPv4 and TCP
listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Bind
HOST, PORT = '', 8888
listen_socket.bind((HOST, PORT))

# Listen
listen_socket.listen()

# Helper function to parse HTTP requests
def parse_request(conn):
    # Pass 1
    initial_request = conn.recv(1024).decode('utf-8')

    if not initial_request: 
        return None 
    
    raw_headers, raw_body = initial_request.split("\r\n\r\n")
    lines = raw_headers.splitlines()
    method, path, _ = lines[0].split(' ')
    
    headers_dict = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers_dict[key.strip().lower()] = value.strip()

    body_bytes = raw_body.encode('utf-8')
    # Pass 2 (make sure entire body is scanned)
    content_length = int(headers_dict.get('content-length', 0))    
    while len(body_bytes) < content_length:
        remaining_length = content_length - len(body_bytes)
        chunk = conn.recv(min(remaining_length, 4096))
        body_bytes += chunk
    request = HTTPRequest(method, path, headers_dict, body_bytes)
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Headers: {request.headers}")
    print(f"Body length: {len(request.body_bytes)}")
    print(f"Query params: {request.query_params}")
    print(f"Body bytes: {request.body_bytes}")
    return request


# Helper function to build HTTP responses
def build_response(status_line, body_bytes, content_type):
    headers = (
        f"{status_line}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"\r\n"
    )
    return headers.encode('utf-8') + body_bytes

while True:
    # Accept
    conn, addr = listen_socket.accept()
    print("Connected to ", addr)

    try: 
        request = parse_request(conn)
        if not request:
            continue

        if request.path == '' or request.path == 'index.html':
            filename = os.path.join("public", "index.html")
        elif '.' in request.path: # eg .png, .css, etc
            filename = os.path.join("public", request.path)
        else:
            filename = os.path.join("public", f"{request.path}.html")
            
        try:
            with open(filename, 'rb') as f:
                body_bytes = f.read()
                
            _, ext = os.path.splitext(filename)
            content_type = MIME_TYPES.get(ext, 'text/plain')
            
            response = build_response("HTTP/1.1 200 OK", body_bytes, content_type)
            
        except FileNotFoundError:
            with open("public/404.html", 'rb') as f:
                body_bytes = f.read() 
            response = build_response("HTTP/1.1 404 Not Found", body_bytes, "text/html")
            
        conn.sendall(response)
    except Exception as e:
        print("Error handling request: ", e)
    finally:
        conn.close()