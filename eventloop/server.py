import socket
import selectors
import io
import sys
import os
import time
from common.request import HTTPRequest
from common.config_loader import load_server_config

class HTTPServer:
    def __init__(self, host='', port=8888, timeout_seconds=15.0, max_read_chunk=1024, app=None):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_read_chunk = max_read_chunk
        self.app = app
        self.sel = selectors.DefaultSelector() # pick selector based on OS
        self.client_buffers = {}
        self.responses = {}
        self.parsed_requests = {}
        self.keep_alive = {}
        self.last_active = {} # can't settimeout on non-blocking sockets

        # Initialize listening socket & register it
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setblocking(False)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind((self.host, self.port))
        self.listen_socket.listen()
        self.sel.register(self.listen_socket, selectors.EVENT_READ, self.accept_connection)

    def serve_forever(self):
        while True:
            # run house-cleaning regularly
            events = self.sel.select(timeout=5.0)
                            
            for key, mask in events:
                callback = key.data
                callback(key.fileobj)

            now = time.time()
            timed_out_connections = []

            for conn, last_seen in self.last_active.items():
                if now - last_seen > self.timeout_seconds:
                    timed_out_connections.append(conn)
            
            for conn in timed_out_connections:
                self.close(conn)

    def accept_connection(self, sock):
        conn, addr = sock.accept()
        conn.setblocking(False)
        self.client_buffers[conn] = b'' # initialize buffer
        self.parsed_requests[conn] = None
        self.last_active[conn] = time.time()
        self.sel.register(conn, selectors.EVENT_READ, self.handle_read)

    def try_process(self, conn):
        client_buffer = self.client_buffers[conn]

        if self.parsed_requests[conn] is None:
            if b"\r\n\r\n" not in client_buffer:
                return None # need to recv more data to complete the headers
            headers, method, path = self.parse_request(client_buffer)
            header_end = client_buffer.index(b"\r\n\r\n") + 4
            self.parsed_requests[conn] = (headers, method, path, header_end)

        headers, method, path, header_end = self.parsed_requests[conn]
        content_length = int(headers.get('content-length', 0))
        body = client_buffer[header_end:]

        if content_length > len(body):
            return None # need to recv more data to complete the body

        body = body[:content_length]
        self.client_buffers[conn] = client_buffer[header_end + content_length:]
        self.parsed_requests[conn] = None
        return HTTPRequest(method, path, headers, body)

    # Handles everything related to WSGI
    def dispatch(self, conn, request):
        environ = self.build_environ(request)
        response_status = []
        response_headers = []

        def start_response(status, headers, exc_info=None):
            response_status.append(status)
            response_headers.extend(headers)

        try:
            result = self.app(environ, start_response)
        except Exception as e:
            print(f"Internal Server Error: {e}", file=sys.stderr)
            response_status = ['500 INTERNAL SERVER ERROR']
            response_headers = [('Content-Type', 'text/plain')]
            result = [b'Internal Server Error: The application crashed.']

        self.responses[conn] = self.finish_response(result, response_status, response_headers)

        keep_alive = request.headers.get('connection')
        self.keep_alive[conn] = (keep_alive is None or keep_alive == 'keep-alive')

        self.sel.modify(conn, selectors.EVENT_WRITE, self.handle_write)

    def handle_read(self, conn):
        self.last_active[conn] = time.time()
        try:
            data = conn.recv(self.max_read_chunk)
            if not data:
                self.close(conn)
                return
            self.client_buffers[conn] += data
        except BlockingIOError:
            return
        
        request = self.try_process(conn)
        if request is None:
            return
        self.dispatch(conn, request)


    def handle_write(self, conn):
        self.last_active[conn] = time.time()

        while self.responses[conn] != b'':
            try:
                sent = conn.send(self.responses[conn])
                self.responses[conn] = self.responses[conn][sent:]
            except BlockingIOError:
                return

        if not self.keep_alive[conn]:
            self.close(conn)
        else:
            self.sel.modify(conn, selectors.EVENT_READ, self.handle_read)

            request = self.try_process(conn)                        
            if request is None:
                return
            self.dispatch(conn, request)

    # Helper method to parse HTTP requests
    def parse_request(self, buf):
        parts = buf.split(b"\r\n\r\n", 1)
        raw_headers = parts[0].decode('utf-8')
        lines = raw_headers.splitlines()
        method, path, _ = lines[0].split(' ')
        headers_dict = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers_dict[key.strip().lower()] = value.strip()
        return headers_dict, method, path
  
    
    # Build the WSGI environ dictionary from the HTTP request
    def build_environ(self, request):
        environ = {
            'REQUEST_METHOD': request.method,
            'PATH_INFO': request.path,
            'QUERY_STRING': request.query_string,
            'CONTENT_TYPE': request.headers.get('content-type', ''),
            'CONTENT_LENGTH': request.headers.get('content-length', ''),
            'SERVER_NAME': self.host or 'localhost',
            'SERVER_PORT': str(self.port),
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.input': io.BytesIO(request.body_bytes),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.url_scheme': 'http',
        }

        for key, value in request.headers.items():
            key = 'HTTP_' + key.upper().replace('-', '_')
            environ[key] = value

        return environ    

    def finish_response(self, result, response_status, response_headers):
        status = response_status[0]
        body = b''.join(result)
        if not any(h[0].lower() == 'content-length' for h in response_headers):
            response_headers.append(('Content-Length', str(len(body))))
        if hasattr(result, 'close'): result.close()
        response = f'HTTP/1.1 {status}\r\n'
        for header in response_headers:
            response += '{0}: {1}\r\n'.format(*header)
        response += '\r\n'
        response = response.encode('utf-8') + body
        return response
    

    def close(self, conn):
        try:
            self.sel.unregister(conn)
        except KeyError:
            pass # Already unregistered
        self.responses.pop(conn, None)
        self.client_buffers.pop(conn, None)
        self.parsed_requests.pop(conn, None)
        self.last_active.pop(conn, None)
        self.keep_alive.pop(conn, None)
        try:
            conn.close()
        except OSError: 
            pass # Already closed at the OS level


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

    config = load_server_config()
    server = HTTPServer(
        config["host"], 
        config["port"], 
        config["timeout_seconds"], 
        config["max_read_chunk"], 
        app=wsgi_callable
    )
    server.serve_forever()