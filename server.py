import socket

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
    request_text = request.decode('utf-8')
    request_lines = request_text.splitlines()
    method, path, version = request_lines[0].split(' ')
    return method, path, version

# Helper function to build HTTP responses
def build_response(status_line, body):
    body_bytes = body.encode('utf-8')
    headers = (
        f"{status_line}\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"\r\n"
    )
    return headers.encode('utf-8') + body_bytes

while True:
    # Accept
    conn, addr = listen_socket.accept()
    print("Connected to ", addr)
    
    # Read some data
    request = conn.recv(1024)

    # Get the method, path, and version from the first line of the request
    if request:
        method, path, version = parse_request(request)
        print("Method: ", method)
        print("Route: ", path)
        print("Version: ", version)
    else:
        conn.close()
        continue

    # Send a response
    if path == '/':
        response = build_response("HTTP/1.1 200 OK", "Welcome!")
    elif path == '/about':
        response = build_response("HTTP/1.1 200 OK", "About Page")
    elif path == '/hello':
        response = build_response("HTTP/1.1 200 OK", "Hello, World!")
    else:
        response = build_response("HTTP/1.1 404 Not Found", "Page Not Found")

    conn.sendall(response)
    conn.close()