""" Support HTTP Proxy CONNECT method with urllib2.
"""

import urllib
import urllib2
import socket, httplib

class ProxyHTTPConnection(httplib.HTTPConnection):
    """
    CONNECT proxy support for urllib2.
    """
    
    _ports = {'http' : 80, 'https' : 443}

    def request(self, method, url, body=None, headers={}):
        """
        Make CONNECT request to proxy.
        """
            
        proto, rest = urllib.splittype(url)
        if proto is None:
            raise ValueError, "unknown URL type: %s" % url
            
        # Get hostname.
        host = urllib.splithost(rest)[0]
        
        # Get port of one
        host, port = urllib.splitport(host)
        
        # When no port use hardcoded.
        if port is None:
            try:
                port = self._ports[proto]
            except KeyError:
                raise ValueError, "unknown protocol for: %s" % url
        
        # Remember.        
        self._real_host = host
        self._real_port = port
        
        # Remember auth if there.
        if headers.has_key("Proxy-Authorization"):
            self._proxy_authorization = headers["Proxy-Authorization"]
            del headers["Proxy-Authorization"]
        else:
            self._proxy_authorization = None
        
        httplib.HTTPConnection.request(self, method, url, body, headers)

    def connect(self):
        """
        Send CONNECT request.
        """

        # Build up connection.
        httplib.HTTPConnection.connect(self)

        newline = "\r\n" # CRLF

        # Send proxy CONNECT request.
        msg = "CONNECT %s:%d HTTP/1.0" % (self._real_host, self._real_port)
        
        # Support headers.
        headers = []
        if self._proxy_authorization:
            headers.append("Proxy-Authorization: %s" % self._proxy_authorization)
            
        # Assemble headers
        headers = newline.join(headers)
        if headers:
            headers = headers + newline
            
        # Assemble complete HTTP message.
        msg = msg + newline + headers + newline

        self.send(msg)
        
        # When success, we get status 200.
        response = self.response_class(self.sock, strict=self.strict, method=self._method)
        version, code, message = response._read_status()

        if code not in (200,):
            # Proxy returned and error, abort connection, and raise exception.
            self.close()
            raise socket.error, "Proxy connection failed: %d %s" % (code, message.strip())
            
        # Read and discard trailer up to the CRLF terminator.
        while True:
            # Directly read from response data.
            line = response.fp.readline()
            if line == newline: 
                break

class ProxyHTTPSConnection(ProxyHTTPConnection):
    
    default_port = 443

    def __init__(self, host, port = None, key_file = None, cert_file = None, strict = None):
        ProxyHTTPConnection.__init__(self, host, port)
        self.key_file = key_file
        self.cert_file = cert_file
    
    def connect(self):
        ProxyHTTPConnection.connect(self)
        # Wrap socket through SSL.
        ssl = socket.ssl(self.sock, self.key_file, self.cert_file)
        self.sock = httplib.FakeSocket(self.sock, ssl)
                                             
class ConnectHTTPHandler(urllib2.HTTPHandler):

    def do_open(self, http_class, req):
        return urllib2.HTTPHandler.do_open(self, ProxyHTTPConnection, req)

class ConnectHTTPSHandler(urllib2.HTTPSHandler):

    def do_open(self, http_class, req):
        return urllib2.HTTPSHandler.do_open(self, ProxyHTTPSConnection, req)
        
        
