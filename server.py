import socket
import os
from request import HTTPRequest
from response import HTTPResponse

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
    
    parts = initial_request.split("\r\n\r\n", 1)
    raw_headers = parts[0]
    raw_body = parts[1] if len(parts) > 1 else ""
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

    body_bytes = body_bytes[:content_length]  # Slice body_bytes to match exactly what the headers claimed

    request = HTTPRequest(method, path, headers_dict, body_bytes)
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Headers: {request.headers}")
    print(f"Body length: {len(request.body_bytes)}")
    print(f"Query params: {request.query_params}")
    print(f"Body bytes: {request.body_bytes}")
    return request

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
            status_code = 200
            status_text = "OK"            
        except FileNotFoundError:
            with open("public/404.html", 'rb') as f:
                body_bytes = f.read() 
                status_code = 404
                status_text = "Not Found"   
                content_type = "text/html"

        response = HTTPResponse(
            status_code=status_code,
            status_text=status_text,
            content_type=content_type,
            body=body_bytes
        ).serialize()

        conn.sendall(response)
    except Exception as e:
        print("Error handling request: ", e)
    finally:
        conn.close()