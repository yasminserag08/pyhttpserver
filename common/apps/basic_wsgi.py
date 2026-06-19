# Absolute baseline wsgi app 
def app(environ, start_response):
    status = '200 OK'
    headers = [('Content-Type', 'text/plain'), ('Server', 'YasminEngine')]
    start_response(status, headers)
    return [b"Hello from the absolute baseline WSGI app"]