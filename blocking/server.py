import argparse
import socket 
import io
import os
import sys
from common.request import HTTPRequest
from common.config_loader import load_server_config
from common.logger import get_logger

class HTTPServer:
    def __init__(self, host='', port=8888, timeout_seconds=15.0, max_read_chunk=1024, app=None):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_read_chunk = max_read_chunk
        self.app = app

        self.logger = get_logger(__name__)

        self.peers = {}
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind((self.host, self.port))
        self.listen_socket.listen()
        self.logger.info("Starting blocking HTTP server on %s:%s", self.host or '0.0.0.0', self.port)

    def serve_forever(self):
        while True:
            conn, addr = self.listen_socket.accept()
            self.peers[conn] = addr
            self.logger.info("Connected to %s", addr)
            self.handle_one_request(conn)

    def handle_one_request(self, conn):
        peer = self.peers.get(conn, '<unknown>')
        conn.settimeout(self.timeout_seconds)
        connection_buffer = b""
        while True:
            # Parse the HTTP request
            try:
                result = self.parse_request(conn, connection_buffer)
            except socket.timeout:
                self.logger.warning("Connection timed out for %s", peer)
                break

            if not result:
                break

            request, connection_buffer = result

            # keep-alive by default
            conn_header = request.headers.get('connection', '').lower()
            keep_alive = (conn_header != 'close')

            response_status = []
            response_headers = []

            def start_response(status, headers, exc_info=None):
                response_status.append(status)
                response_headers.extend(headers)
            
            self.logger.info("Handling request %s %s from %s", request.method, request.path, peer)
            # Build the WSGI environ
            environ = self.build_environ(request)

            try:
                # Call the WSGI application 
                wsgi_result = self.app(environ, start_response)
            except Exception as e:
                self.logger.exception("Internal Server Error")
                response_status = ['500 INTERNAL SERVER ERROR']
                response_headers = [('Content-Type', 'text/plain')]
                wsgi_result = [b'Internal Server Error: The application crashed.'] 
            response = self.finish_response(wsgi_result, response_status, response_headers, keep_alive)
            self.logger.info("Sending response %s for %s (%d bytes), keep_alive=%s", response_status[0], peer, len(response), keep_alive)
            conn.sendall(response)
            if not keep_alive: 
                self.logger.info("Closing connection %s because client requested close", peer)
                self.peers.pop(conn, None)
                conn.close()
                return 
        self.logger.info("Closing connection %s", peer)
        self.peers.pop(conn, None)
        conn.close()

    # Helper function to parse HTTP requests 
    def parse_request(self, conn, connection_buffer):
        peer = self.peers.get(conn, '<unknown>')
        while b"\r\n\r\n" not in connection_buffer:
            try:
                chunk = conn.recv(self.max_read_chunk)
            except ConnectionResetError:
                return None
            if not chunk: 
                return None  # client closed connection 
            connection_buffer += chunk
        
        parts = connection_buffer.split(b"\r\n\r\n", 1)
        try:
            raw_headers = parts[0].decode('utf-8')
        except UnicodeDecodeError:
            self.logger.warning("Non-UTF-8 headers from %s", peer)
            return None
        body_bytes = parts[1] if len(parts) > 1 else b""
        
        lines = raw_headers.splitlines()
        if not lines or not lines[0]:
            return None
            
        try:
            method, path, _ = lines[0].split(' ')
        except ValueError:
            self.logger.warning("Malformed request line from %s: %s", peer, lines[0])
            return None        
        
        headers_dict = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers_dict[key.strip().lower()] = value.strip()

        content_length = int(headers_dict.get('content-length', 0))    
        
        # Keep fetching data until body is done
        while len(body_bytes) < content_length:
            remaining_length = content_length - len(body_bytes)
            chunk = conn.recv(min(remaining_length, 4096))
            if not chunk:
                return None
            body_bytes += chunk

        # Slice off to match content_length
        actual_body = body_bytes[:content_length]
        
        # keep leftover data (in case of 2 requests in a row)
        leftover_buffer = body_bytes[content_length:]
        
        request = HTTPRequest(method, path, headers_dict, actual_body)
        return request, leftover_buffer
    
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
    
        
    # Helper function to finish the WSGI response
    def finish_response(self, result, response_status, response_headers, keep_alive):
        status = response_status[0]
        body = b''.join(result)
        body_len = len(body)
        if hasattr(result, 'close'): result.close()
        response = f'HTTP/1.1 {status}\r\n'

        # Check if Content-Length & Connection were already returned by wsgi app
        has_content_length = any(h[0].lower() == 'content-length' for h in response_headers)
        has_connection = any(h[0].lower() == 'connection' for h in response_headers)
        
        if not has_content_length:
            response += f"Content-Length: {body_len}\r\n"
            
        if not has_connection:
            if keep_alive:
                response += f"Connection: keep-alive\r\n"
            else:
                response += f"Connection: close\r\n"

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
    config = load_server_config()

    parser = argparse.ArgumentParser(
        description="Start the blocking WSGI server."
    )
    parser.add_argument("app_path", help="WSGI app in the form module:callable or apps.<name> if no module prefix is provided")
    parser.add_argument("--port", type=int, default=config["port"],
                        help=f"Port to bind. Defaults to config.json value {config['port']}")
    parser.add_argument("--timeout", type=float, default=config["timeout_seconds"],
                help=f"Connection timeout in seconds. Defaults to config.json value {config['timeout_seconds']}")
    args = parser.parse_args()

    app_path = args.app_path

    if ":" in app_path:
        module_name, variable_name = app_path.split(":", 1)
    else:
        module_name = f"apps.{app_path}"
        variable_name = "app"

    # dynamically import whatever was requested
    imported_module = __import__(module_name, fromlist=[variable_name])
    wsgi_callable = getattr(imported_module, variable_name)
    server = HTTPServer(
        config["host"], 
        args.port, 
        args.timeout, 
        config["max_read_chunk"], 
        app=wsgi_callable
    )
    server.serve_forever()