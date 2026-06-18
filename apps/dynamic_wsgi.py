# WSGI apps that serves different routes

def app(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')
    clean_path = path.strip('/')
    
    if clean_path == '':
        status = '200 OK'
        headers = [('Content-Type', 'text/html')]
        body = [b"<h1>Welcome to the Dynamic WSGI App!</h1><p>Try going to /secret or /error</p>\n"]
    elif clean_path == 'secret':
        status = '403 FORBIDDEN'
        headers = [('Content-Type', 'text/plain')]
        body = [b"Forbidden: You do not have permission to access this area.\n"]
    elif clean_path == 'submit' and method == 'POST':
        status = '201 CREATED'
        headers = [('Content-Type', 'application/json')]
        body = [b'{"message": "Data processed successfully via POST request"}\n']
    else:
        status = '404 NOT FOUND'
        headers = [('Content-Type', 'text/html')]
        body = [b"<h1>404 Not Found</h1><p>This dynamic route doesn't exist.</p>\n"]

    start_response(status, headers)
    return body