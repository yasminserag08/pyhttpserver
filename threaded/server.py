import socket 
import io
import os
import sys
import time
import threading
from common.request import HTTPRequest

class HTTPServer:
    def __init__(self, host='', port=8888, app=None):
        self.host = host
        self.port = port
        self.app = app
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind((self.host, self.port))
        self.listen_socket.listen()

    def serve_forever(self):
        i = 0
        while True:
            conn, addr = self.listen_socket.accept()
            t = threading.Thread(target=self.handle_one_request, args=(conn,), name=f"thread{i}")
            t.start()
            i += 1

    def handle_one_request(self, conn):
        response_status = []
        response_headers = []

        def start_response(status, headers, exc_info=None):
            response_status.append(status)
            response_headers.extend(headers)

        print(f"Handling connection in thread: {threading.current_thread().name}")

        # Parse the HTTP request
        request = self.parse_request(conn)
        if not request:
            return None
        
        # Build the WSGI environ
        environ = self.build_environ(request)

        try:
            # Call the WSGI application 
            result = self.app(environ, start_response)
        except Exception as e:
            print(f"Internal Server Error: {e}", file=sys.stderr)
            response_status = ['500 INTERNAL SERVER ERROR']
            response_headers = [('Content-Type', 'text/plain')]
            result = [b'Internal Server Error: The application crashed.'] 
        response = self.finish_response(result, response_status, response_headers)
        conn.sendall(response)
        time.sleep(60)
        conn.close()

    # Helper function to parse HTTP requests
    def parse_request(self, conn):
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
    
    # Build the WSGI environ dictionary from the HTTP request
    def build_environ(self, request):
        environ = {
            'REQUEST_METHOD': request.method,
            'PATH_INFO': request.path,
            'QUERY_STRING': '&'.join(f'{k}={v}' for k, v in request.query_params.items()),
            'CONTENT_TYPE': request.headers.get('content-type', ''),
            'CONTENT_LENGTH': request.headers.get('content-length', ''),
            'SERVER_NAME': self.host or 'localhost',
            'SERVER_PORT': str(self.port),
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.input': io.BytesIO(request.body_bytes),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.url_scheme': 'http',
        }

        for key, value in request.headers.items():
            key = 'HTTP_' + key.upper().replace('-', '_')
            environ[key] = value

        return environ     
    
        
    # Helper function to finish the WSGI response
    def finish_response(self, result, response_status, response_headers):
        status = response_status[0]
        body = b''.join(result)
        response = f'HTTP/1.1 {status}\r\n'
        for header in response_headers:
            response += '{0}: {1}\r\n'.format(*header)
        response += '\r\n'
        response = response.encode('utf-8') + body
        return response

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Tell Python it's allowed to look for modules directly inside the root folder
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # Get callable from command line
    if len(sys.argv) < 2:
        print("Usage: python3 server.py <module_name>:<variable_name>")
        sys.exit(1)

    app_path = sys.argv[1]

    if ":" in app_path:
        module_name, variable_name = app_path.split(":", 1)
    else:
        module_name = f"apps.{app_path}"
        variable_name = "app"

    # dynamically import whatever was requested
    imported_module = __import__(module_name, fromlist=[variable_name])
    wsgi_callable = getattr(imported_module, variable_name)

    server = HTTPServer(host='', port=8888, app=wsgi_callable)
    server.serve_forever()