import urllib.parse

class HTTPRequest:
    def __init__(self, method, raw_path, headers, body_bytes):
        self.method = method
        self.raw_path = raw_path      
        self.headers = headers       
        self.body_bytes = body_bytes   # raw payload bytes, can be empty (if GET request for example)
        
        # Parse query params immediately on object creation
        self._raw_query_dict = self._parse_query_string_raw()

    @property
    def path(self):
        # Returns a clean routing path stripped of slashes and query parameters
        base_path = self.raw_path.split('?')[0]
        return base_path.strip('/')

    def _parse_query_string_raw(self):
        # Extracts query parameters from the raw_path
        if '?' not in self.raw_path:
            return {}
        
        try:
            _, query_string = self.raw_path.split('?', 1)
            # urllib.parse.parse_qs handles complex URL decoding automatically (eg %20 for spaces)
            parsed = urllib.parse.parse_qs(query_string)
            return parsed
        except Exception:
            return {}
        
    @property
    def query_params(self):
        # Returns a convenient, flat dictionary (first item of a list, since most params won't be multivalued for now)
        return {k: v[0] for k, v in self._raw_query_dict.items()}

    def getlist(self, key):
        # Explicitly fetches all values for a key as a list
        return self._raw_query_dict.get(key, [])