import socket
import os

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
def parse_request(request):
    try:
        request_text = request.decode('utf-8')
        request_lines = request_text.splitlines()
        if not request_lines:
            return None, None, None
        parts = request_lines[0].split(' ')
        if len(parts) == 3:
            method, path, version = parts
            return method, path, version
    except Exception:
        return None, None, None

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
        # Read some data
        request = conn.recv(1024)

        # Get the method, path, and version from the first line of the request
        if request:
            method, path, version = parse_request(request)
            if not method or not path or not version:
                continue
            print("Method: ", method)
            print("Route: ", path)
            print("Version: ", version)
        else:
            continue

        # Send a response
        # Clean up the path by removing the leading slash
        clean_path = path.lstrip('/')
        if path == '/' or path == '/index.html':
            filename = os.path.join("public", "index.html")
        # Browser specific requests for stylesheets, images, etc.
        elif '.' in clean_path:
            filename = os.path.join("public", clean_path)
        # For other paths, try to serve an HTML file with the same name
        else:
            filename = os.path.join("public", f"{clean_path}.html")
        try:
            with open(filename, 'rb') as f:
                body_bytes = f.read()
            _, ext = os.path.splitext(filename) # extract file extension
            content_type = MIME_TYPES.get(ext, 'text/plain') # default to text/plain if unknown
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