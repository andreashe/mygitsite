#!/usr/bin/python
"""
**********************************************************************/
COPYRIGHT: (c) 2007 by struktur AG
DATE     : 26ARP2007
REVISION : $Revision: 5364 $
VERSION  : $Id: vnc2spreed.py 5364 2009-04-01 08:39:18Z longsleep $

struktur AG            Phone: +49 711 8966560
Kronenstr. 22a         Fax:   +49 711 89665610
70173 Stuttgart        email: info@struktur.de
GERMANY

http://www.struktur.de
http://www.strukturag.com

**********************************************************************/
"""
__version__='$Revision: 5364 $'[11:-2]

import sys, os, socket, urlparse, time, signal
from threading import Thread

from vncsupport.movie import SWFInfo
from vncsupport.output import FLVVideoStream, MovieOutputStream
from vncsupport.rfb import RFBError, RFBNetworkClient, RFBStreamConverter
from vncsupport.image import IMG_SOLID, IMG_RAW, IMG_LOSSLESS, IMG_VIDEOPACKET

stderr = sys.stderr

try:
    from flvcodec import CaptureSource, UploadThread, NetworkSettings, Publisher, COLORS_RGB, COLORS_BGR, COLORS_XRGB, COLORS_RGBX            
except ImportError:    
    # get python version
    PYTHON_VERSION = sys.version_info[:2]
    if PYTHON_VERSION in ((2, 5), (2, 6)):
        from flvcodec25.flvcodec import CaptureSource, UploadThread, NetworkSettings, Publisher, COLORS_RGB, COLORS_BGR, COLORS_XRGB, COLORS_RGBX
    elif PYTHON_VERSION == (2, 4):
        from flvcodec24.flvcodec import CaptureSource, UploadThread, NetworkSettings, Publisher, COLORS_RGB, COLORS_BGR, COLORS_XRGB, COLORS_RGBX    
    else:
        raise   

def vnc2spreed(host='localhost', port=5900, uri=None, ticket=None,
               preferred_encoding=(0,), pwdfile=None, statusfile=None,
               debug=0):

    info = SWFInfo()

    stream = FLVVideoStreamToSpreed(info, statusfile=statusfile)
    converter = RFBStreamConverter(info, stream)
    networksettings = SpreedNetworkSettings()
    conferenceconnection = SpreedConferenceConnection(uri, ticket)

    client = RFBSpreedClient(host, port, converter, networksettings, conferenceconnection, pwdfile=pwdfile, preferred_encoding=preferred_encoding, debug=debug)

    # Register SIGTERM handler
    signal.signal(signal.SIGTERM, client.term)

    try:
        client.init().auth().start()
        try:
            try:
                client.loop()
            except KeyboardInterrupt:
                pass
        finally:
            client.close()
            stream.close()
    except socket.error, e:
        print >>stderr, 'Socket error:', e
    except RFBError, e:
        print >>stderr, 'RFB error:', e

    return

def rgbimage(w, h, (format, data)):
    """
    Returns image data and colors type from input data.
    """

    img = None

    if format == IMG_SOLID:
        # fill color
        raise NotImplementedError, "IMG_SOLID not supported yet."
    if format == IMG_RAW:
        # raw buffer (RGB or RGBX)
        if len(data) == (w*h*3):
            return data, COLORS_RGB
        elif len(data) == (w*h*4):
            return data, COLORS_RGBX
        else:
            raise NotImplementedError, "Unknown RAW format."
    elif format == IMG_LOSSLESS:
        # image defined by DefineBitsLossless (XRGB)
        data = zlib.decompress(data)
        assert len(data) == (w*h*4)
        return data, COLORS_XRGB
    elif format == IMG_VIDEOPACKET:
        # image defined by SCREENVIDEOPACKET (BGR)
        data = zlib.decompress(data)
        assert len(data) == (w*h*3)
        return data, COLORS_BGR
    else:
        raise NotImplementedError, 'Illegal image format: %d' % format

class RFBCaptureSource:

    stream = None
    client = None

    def __init__(self, converter=None, client=None):
        self.stream = converter.stream
        self.client = client

    def Capturing(self):
        return client.enabled and True or False

    def CaptureRect(self):
        return (0,0,0,0)

    def CaptureWidth(self):
        return self.stream.info.get_size()[0]

    def CaptureHeight(self):
        return self.stream.info.get_size()[1]

    def IsWindowVisible(self):
        return True

    def CaptureFullscreen(self):
        return False

    def Flush(self):
        pass

    def MousePosition(self):
        return self.stream.cursor_pos

    def CaptureMouse(self):
        return False

    def MouseCursor(self):
        return 1

class SpreedConferenceConnection:

    uri = None
    ticket = None

    host = port = path = ticket = conferenceid = None
    
    def __init__(self, uri, ticket):

        self.uri = uri
        self.ticket = ticket

        assert self.ticket
        assert self.uri

        if not uri.startswith("http://") and not uri.startswith("https://"):
            url = "http://%s" % uri
        else:
            url = uri

        url = urlparse.urlparse(url)

        # Get host and port.
        if url[1].find(":") != -1:
            self.host, self.port = url[1].split(":")
            self.port = int(self.port)
        else:
            self.host = url[1]
            if url[0] == "https":
                self.port = 443
            elif url[0] == "http":
                self.port = 80

        # Get path and conference id.
        self.path, self.conferenceid = os.path.split(url[2])

        assert self.path
        assert self.conferenceid
        assert self.host
        assert self.port

class SpreedNetworkSettings:

    useproxy = None
    useproxyauth = None
   
    proxyserver = None
    proxyport = None
    
    proxyusername = None
    proxypassword = None
    
    updateurl = None

    def __init__(self, proxyserver=None, proxyport=None, proxyusername=None, proxypassword=None, updateurl=None):
        
        self.proxyserver = proxyserver
        try:
            self.proxyport = int(proxyport)
        except TypeError:
            self.proxyport = 443
        
        self.proxyusername = proxyusername
        self.proxypassword = proxypassword
        
        if self.proxyserver is not None and self.proxyport is not None:
            self.useproxy = True
        else:
            self.useproxy = False
        
        if not self.useproxy:
            # Support environment variable.    
            # Example: https_proxy="https://user:qwerty@myproxy.mydomain.com:3128"
            https_proxy = os.environ.get("https_proxy", None)
            if https_proxy is not None:
                if https_proxy.startswith("https://"):
                    https_proxy = urlparse.urlsplit(https_proxy)[1]
                else:
                    pass
                    
                # Parse username and password.
                if https_proxy.find("@") != -1:
                    # Authentication
                    up, phpp = https_proxy.split("@",1)
                else:
                    up = ""
                    phpp = https_proxy
                
                # Split port.
                if phpp.find(":") != -1:
                    ph, pp = phpp.split(":",1)
                else:
                    ph = phpp
                    pp = 443
                   
                # Split passwd. 
                if up.find(":") != -1:
                    u, p = up.split(":",1)
                else:
                    u = up
                    p = ""

                # Set to configuration.
                if ph:
                    self.proxyserver = ph
                    self.useproxy = True
                if pp:
                    self.proxyport = int(pp)
                if u:
                    self.proxyusername = u
                if p is not None:
                    self.proxypassword = p
            
        if self.proxyusername:
            self.useproxyauth = True
        else:
            self.useproxyauth = False

        #print self.proxyserver
        #print self.proxyport
        #print self.proxyusername
        #print self.proxypassword
        #print self.useproxyauth
        #print self.useproxy

    def UseProxy(self):
        return self.useproxy

    def ProxyServer(self):
        return self.proxyserver

    def ProxyPort(self):
        return self.proxyport

    def UseProxyAuthentication(self):
        return self.useproxyauth

    def ProxyUsername(self):
        return self.proxyusername

    def ProxyPassword(self):
        return self.proxypassword

    def UpdateUrl(self):
        return self.updateurl

class PublisherUpdateThread(Thread):
    
    def __init__(self, publisher, statusfile, *args, **kw):
        Thread.__init__(self, *args, **kw)
        self.publisher = publisher
        self.statusfile = statusfile
        self.setDaemon(1)
        self.setName("PublisherUpdateThread")
        self.running = False
    
    def start(self):
        self.running = True
        Thread.start(self)

    def stop(self):
        self.running = False

    def run(self):
        frame=0
        while self.running:
            if self.publisher.NextFrameReady:
                #file("/tmp/frame-debug-%.4d.raw" % frame, "wb").write(self.publisher.Data) # enable for data debugging
                frame+=1L
                self.publisher.TriggerVideoUpdate()

            # Write out status file if given
            if self.statusfile:
                if self.publisher.FramesSent > 0:
                    # First frame sent successfully.
                    fp = file(self.statusfile, "wb")
                    fp.write("\x01")
                    fp.close()
                    self.statusfile = None

            # give some CPU to other processes
            time.sleep(0.01)
    
class RFBSpreedClient(RFBNetworkClient):
    """
    Connect to spreed.
    """

    networksettings = None
    conferenceconnection = None
    uploadthread = None
    publisher = None

    enabled = False

    def __init__(self, host, port, fb=None, networksettings=None, conferenceconnection=None, pwdfile=None, preferred_encoding=(0,5), debug=0):
        RFBNetworkClient.__init__(self, host=host, port=port, fb=fb, pwdfile=pwdfile, preferred_encoding=preferred_encoding, debug=debug)

        self.networksettings = NetworkSettings(networksettings)
        self.conferenceconnection = conferenceconnection

    def init(self):

        # Create server capture source.
        capturesource = CaptureSource(RFBCaptureSource(converter=self.fb, client=self))

        # Start publishing thread.
        self.uploadthread = UploadThread()
        
        # Set data.
        self.uploadthread.SetVersion("%s-%s" % (__version__, sys.platform))
        self.uploadthread.SetSource(capturesource)
        self.uploadthread.SetNetworkSettings(self.networksettings)

        # Configure spreed connection.
        self.uploadthread.UpdateConfiguration(self.conferenceconnection.host, self.conferenceconnection.port, self.conferenceconnection.path, self.conferenceconnection.ticket, self.conferenceconnection.conferenceid)

        # Create publisher
        self.publisher = Publisher(capturesource, self.uploadthread, 3)

        # Publish publisher to framebuffer
        self.fb.stream.set_publisher(self.publisher)

        # Start VNC connection.
        return RFBNetworkClient.init(self)

    def start(self):
        # Start to receive data.
        RFBNetworkClient.start(self)
        self.enabled = True

        # All metadata and streams initialized. Propagate to publisher.
        self.publisher.UpdateCaptureSize()

        return self
    
    def close(self):
        RFBNetworkClient.close(self)
        self.enabled = False

    def term(self, sig, *args, **kw):
        print >>stderr, "vnc2spreed caught signal: %s" % sig
        self.close()

    def loop(self):
        while self.loop1():
            pass
        self.finish_update()
        return self

class FLVVideoStreamToSpreed(FLVVideoStream):
    """
    Feed data to spreed.
    """
    publisher = None
    statusfile = None
    publisherupdatethread = None

    frame = None

    def __init__(self, info, statusfile=None, debug=0):
        MovieOutputStream.__init__(self, info, debug)
        self.statusfile = statusfile
        return

    def set_publisher(self, publisher):
        self.publisher = publisher

    def open(self):
        x,y,w,h = self.info.clipping
        self.painted = False
        self.frame=1
        return

    def paint_frame(self, (images, othertags, cursor_info)):
        #print "-> Paint Frame ", self.frame
        count = 0
        for ((x0,y0), (w,h,data)) in images:
            count += 1
            self.painted = True
            img, colors = rgbimage(w, h, data)
            self.publisher.UpdateRectangle(x0,y0,w,h,img, True, colors)
            if self.debug:
                print >>stderr, 'paint:', (x0,y0), (w,h), repr(data[0]), len(img)
        if cursor_info:
            (cursor_image, cursor_pos) = cursor_info
            self.cursor_image = cursor_image or self.cursor_image
            self.cursor_pos = cursor_pos or self.cursor_pos
            #print "   cursor update", self.cursor_pos

        return

    def change_size(self, width, height):
        #print ">> changed size", width, height
        self.publisher.UpdateCaptureSize()
        #print ">> notified publisher"
        pass

    def set_keyframe(self):
        return

    def next_frame(self):
        self.frame += 1

        if self.painted:
            #print "-> Next frame (painted)"
            self.painted = False

        if self.publisherupdatethread is None:
            self.publisherupdatethread = PublisherUpdateThread(self.publisher, self.statusfile)
            self.publisherupdatethread.start()

        return MovieOutputStream.next_frame(self)

    def close(self):
        if self.publisherupdatethread is not None:
            self.publisherupdatethread.stop()
            del self.publisherupdatethread
        
        return MovieOutputStream.close(self)

def main(args):
    import getopt

    try:
        (opts, args) = getopt.getopt(sys.argv[1:], 'dno:t:e:NC:r:S:P:zma')
    except getopt.GetoptError:
        usage()

    # Defaults.
    debug, subprocess, pwdfile = 0, None, None
    host, port = 'localhost', 5900
    uri = ticket = ""
    statusfile = None

    preferred_encoding=(0,)
    preferred_encoding += (-232,-239) # This enables transmission of cursor position.
    preferred_encoding += (-223,)     # Enable desktop size changes.

    for (k, v) in opts:
        if k == '-d': debug += 1
        elif k == '-P': pwdfile = v

    if len(args) >= 1:
        if ':' in args[0]:
            i = args[0].index(':')
            host = args[0][:i] or 'localhost'
            port = int(args[0][i+1:])
        else:
            host = args[0]

    if len(args) >= 3:
        uri = args[1]
        ticket = args[2]
        
    if len(args) >= 4:
        statusfile = args[3]

    if not uri or not ticket or not host or not port:
        print >>sys.stdout, "Usage: %s hostname:port spreeduri spreedticket [statusfile]" % sys.argv[0]
        sys.exit(1)

    # Reset stderr when not in debug mode.
    if debug == 0:
        global stderr
        from StringIO import StringIO
        stderr = StringIO()
        from vncsupport import movie
        from vncsupport import rfb
        movie.stderr = stderr
        rfb.stderr = stderr

    vnc2spreed(host, port, uri=uri, ticket=ticket, preferred_encoding=preferred_encoding, pwdfile=pwdfile, statusfile=statusfile, debug=debug)

if __name__ == "__main__":
    main(sys.argv[1:])
