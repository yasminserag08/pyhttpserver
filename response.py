class HTTPResponse:
    def __init__(self, status_code=200, status_text="OK", content_type="text/html", body=b""):
        self._status_code = status_code
        self._status_text = status_text
        self._body = body
        self._headers = {
            "content-type": content_type,
            "content-length": str(len(body))
        }

    def set_header(self, name, value):
        self._headers[name] = str(value)


    def serialize(self):
            self._headers["Content-Length"] = str(len(self._body))
            
            headers_string = f"HTTP/1.1 {self._status_code} {self._status_text}\r\n"
            
            for key, value in self._headers.items():
                headers_string += f"{key}: {value}\r\n"
                
            headers_string += "\r\n"
            
            return headers_string.encode('utf-8') + self._body