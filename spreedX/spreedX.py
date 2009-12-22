#!/usr/bin/env python
"""
**********************************************************************/
COPYRIGHT: (c) 2007-2009 by struktur AG
DATE     : 26ARP2007
REVISION : $Revision: 31611 $
VERSION  : $Id: spreedX.py 31611 2009-10-29 22:28:38Z longsleep $

struktur AG            Phone: +49 711 8966560
Kronenstr. 22a         Fax:   +49 711 89665610
70173 Stuttgart        email: info@struktur.de
GERMANY

http://www.struktur.de
http://www.strukturag.com

**********************************************************************/
"""
__version__='$Revision: 31611 $'[11:-2]

import os, sys, signal, tempfile, glob, time
import datetime, random, string
import traceback
import socket, base64

from fnmatch import fnmatch
from struct import unpack, pack
from StringIO import StringIO

import vncdes

from threading import Thread

# We require python-gtk >= 2.8 and glade.
try:
    import pygtk
    pygtk.require('2.0')
    import gtk
    import gobject
    import gtk.glade
    NOPYGTK = False
except (ImportError, AssertionError, KeyError), msg:
    NOPYGTK = (True, repr(msg))

# We require python-xml.
try:
    from xml.dom import minidom
    NOPYXML = False
except ImportError:
    NOPYXML = True

GTKTRAY = EGGTRAY = False
try:
    from gtk import StatusIcon
    GTKTRAY = True
except ImportError:
    try:
        import egg.trayicon
        EGGTRAY=True
    except ImportError:
        pass

PYNOTIFY = False
try:
    import pynotify
    PYNOTIFY = pynotify.init("spreedX") and True or False
except ImportError:
    pass

if not NOPYGTK:
    # Initializing the gtk's thread engine.
    gtk.gdk.threads_init()

try:
    # Import inotify support when available.
    from pyinotify import WatchManager, ThreadedNotifier, EventsCodes, ProcessEvent
    try:
        EventsCodes.ALL_FLAGS["IN_CREATE"]
    except (AttributeError, KeyError):
        raise ImportError, "incompatible"
    INOTIFY_WM = WatchManager()
except ImportError:
    INOTIFY_WM = None
    class ProcessEvent:
        def __init__(self):
            pass
        
# Set default socket timeout.
import socket
socket.setdefaulttimeout(10) 

import urllib2, urlparse
import proxysupport

XWININFO=os.environ.get("SPREEDX_XWININFO", "xwininfo")
X11VNC=os.environ.get("SPREEDX_X11VNC", "x11vnc")
FIND=os.environ.get("SPREEDX_FIND", "find")
VNC2SPREED=os.environ.get("SPREEDX_VNC2SPREED", None)

LSOBASE=os.path.expanduser("~/.macromedia")
LSOBASENAME="spreedShareData"
SPREEDXBASE=os.path.expanduser("~/.spreedx")
VNCSERVERPORTBASE=32741
UID=os.geteuid()

DEBUG=10 # Level from 0 to 10.
DEBUGDST = None
DEBUGLOG = None
DEBUGTMP = None

ISLOCALDISPLAY = os.environ.get("DISPLAY", "").startswith(":") or os.environ.get("DISPLAY", "").startswith("localhost:")

X11VNCVERSION=0.8 # This is the default.

STATUS_ERROR        = 0
STATUS_DISCONNECTED = 10
STATUS_WAITING      = 20
STATUS_STOPPED      = 30
STATUS_USERINPUT    = 35
STATUS_CONNECTING   = 50
STATUS_RUNNING      = 60

DESKTOP_UNKNOWN = 0
DESKTOP_KDE = 1
DESKTOP_GNOME = 2

DEFAULTCONFIGURATION = """\
<spreedconnectionconfig version="1.3">
    <general>
        <local value="true" />
        <localauto value="true" />
        <localport>5900</localport>
        <remoteaddr />
        <remotepassword />
    </general>
    <connection>
        <direct value="true" />
        <proxyaddr />
        <proxyusername />
        <proxypassword />
    </connection>
    <log>
        <file>spreedx.log</file>
        <level>10</level>
    </log>
</spreedconnectionconfig>
"""

# Get base path.
BASEPATH = os.path.abspath(os.path.split(globals()['__file__'])[0])

# Compute tools path which are shipped with us.
if not VNC2SPREED:
    VNC2SPREED=os.path.join(BASEPATH, "tools", "vnc2spreed", "vnc2spreed")

def INITIALIZELOG(f, level=10):
    global DEBUGLOG, DEBUG
    if DEBUGLOG is None:
        DEBUGLOG = file(f, "ab")
    DEBUG = level

def LOG(msg, level, exc=None, iserror=False, reraise=False):
    if level > DEBUG:
        # Avoid logging stuff we ignore.
        return
    if level < 0 and level <= DEBUG*-1:
        # Avoid logging stuff we ignore in error case.
        return

    if (reraise or iserror) and not exc:
        exc=sys.exc_info()
    
    if exc is None:
        exc = ''
    else:
        if DEBUG < 5:
            exc = repr(traceback.format_exception_only(exc[0], exc[1]))
        else:
            exc = repr(traceback.format_exception(exc[0], exc[1], exc[2]))
    
    # Get current time.
    now = datetime.datetime.now()
    
    logline = "%s - %2d - %s %s" % (now.isoformat(), level, msg, exc)
    
    global DEBUGTMP, DEBUGLOG
    
    dst = DEBUGLOG
    tmp = None
    if not dst:
        dst = DEBUGDST
        tmp = DEBUGTMP
        if not tmp:
            DEBUGTMP = StringIO()
            tmp = DEBUGTMP
    else:
        if DEBUGTMP:
            DEBUGTMP.seek(0)
            tmp = DEBUGTMP.readlines()
            DEBUGTMP = None
            
            for l in tmp:
                print >>dst, l
                
            tmp = None
        
    if dst is not None:
        try:
            print >>dst, logline
        finally:
            if hasattr(dst, "flush"): dst.flush()
            
    if tmp is not None: 
        print >>tmp, logline
    
    if exc and reraise:
        raise   

def ERROR(msg, level, reraise=False):
    return LOG(msg, level, iserror=True, reraise=reraise)

def check4tools(errors=[]):
    """
    Checks if all required tools are available.
    Modifies the given error list.
    """
    
    PATH = os.environ.get('PATH', '').split(':')
    for name, exe in (('xwininfo', XWININFO), ('x11vnc', X11VNC), ('vnc2spreed', VNC2SPREED)):
    
        found = None
        if exe.find(os.sep) != -1:       
            # Full path given.
            if os.path.exists(exe):
                found = exe
                LOG("%s at %s found" % (name, exe), 10)
            else:
                LOG("%s not found at %s" % (name, exe), 5)

        if not found:
            # Search inside PATH.
            realexe = None
            for p in PATH:
                f = os.path.join(p, os.path.split(exe)[1])
                if os.path.exists(f):
                    realexe = f
                    found = realexe
                    LOG("%s at %s found" % (name, realexe), 10)
                    break
            if not realexe:
                errors.append((name, ':'.join(PATH)))
                LOG("%s not found in PATH" % (name), 5)

        # Check version requirements.
        if found and name == "x11vnc":
            LOG("Checking x11vnc version", 10)
            
            version = 0
            
            cmd = [found, "--version"]
            fp = os.popen(" ".join(cmd), "r")
            data = fp.read().strip()
            res = fp.close()
            
            if res != None:
                errors.append((name, found))
                LOG("%s failed to get version with status (%s)" % (name, res), 0)
            else:
                if data.startswith("x11vnc: "):
                    # Data has to be like x11vnc: 0.8.2 lastmod: 2006-07-12
                    version = float(data[9:11])

            # Check if version is good.
            LOG("Detected x11vnc version %s" % version, 5)
            if version < 0.8:
                LOG("WARNING: old x11vnc detected (at least 0.8 is required for all features)", 0)
            global X11VNCVERSION
            X11VNCVERSION = version
                
    return errors

def detectde():
    """
    Detects which desktop environment is run.
    """
    
    if os.environ.get("KDE_FULL_SESSION", None) == "true":
        return DESKTOP_KDE
    elif os.environ.get("GNOME_DESKTOP_SESSION_ID", None) is not None:
        return DESKTOP_GNOME
    else:
        return DESKTOP_UNKNOWN

def getcurrentscreenwindowid():
    """
    Returns the current screen x window id as hex.
    """
    
    # Get root window.
    w = gtk.gdk.get_default_root_window()

    if w is not None:
        return hex(w.xid)
        
    return None
    
def getlsodata(maxage=datetime.timedelta(hours=2), ignore={}, init=False):
    """
    Tries to find lso and returns its data as mapping.
    When init is True, it returns all matching lsos, else only newest one.
    See http://sourceforge.net/docman/display_doc.php?docid=27130&group_id=131628.
    Returns list of tuples containing lso meta data and data dicts.
    """
    
    lsos = []
    
    name = LSOBASENAME
    maxage = maxage.seconds
    
    for path in (os.path.join(LSOBASE, "Flash_Player", "#SharedObjects"), os.path.join(LSOBASE, "Macromedia", "Flash Player", "#SharedObjects")):
    
        # Find matching .sol files.
        if os.path.isdir(path):
        
            # Write new file to get current fs timestamp.
            timecheckfile = os.path.join(path, '.spreed-time-check.dat')
            try:
                fp = file(timecheckfile, 'wb')
                fp.write('\x01')
                fp.close()
                # Get timestamp from check file.
                now = os.stat(timecheckfile)[8]
                # Set time to maxage.
                then = now - maxage
                os.utime(timecheckfile, (then, then))
            except (OSError, IOError):
                # Ignore all file access errors.
                # NOTE: This might be not in sync with the fs time (eg. nfs).
                ERROR("Error while writing timecheckfile %s" % (timecheckfile), -1)
                now = time.time()
                timecheckfile = None        
            
            # Easy mode find usage.
            cmd = [FIND, '"%s"' % path, '-mindepth 3 -maxdepth 10 -type f', '-name "%s.sol"' % name]
                        
            # Add timecheck if available.
            if timecheckfile:
                cmd.append('-newer "%s"' % timecheckfile)
            
            fp = os.popen(' '.join(cmd), 'r')
            lso_files = fp.readlines()
            status = fp.close()

            for f in lso_files:
                f = f.strip()
                # Get last modification.
                try:
                    modified = os.stat(f)[8]
                except (IOError, OSError):
                    ERROR("Error getting modified time from %s", -10)
                    # Ignore all file access errors.
                    continue
                if (now - maxage < modified):
                    if not ignore.has_key((modified, f)):
                        lsos.append((modified,f))
                        LOG("Found new LSO %s" % f, 8)
                    else:
                        # Already got this file.
                        pass
                else:
                    LOG("Found expired LSO %s (%s < %s)" % (f, repr(now-maxage), repr(modified)), 101)
                    pass

            if timecheckfile:
                try:
                    # Remove time check file.
                    os.unlink(timecheckfile)
                except (OSError, IOError):
                    # Ignore all file access errors.
                    ERROR("Error cleaning up timecheckfile %s" % (timecheckfile), -1)
                    pass

    # Sort. -> newest first.
    lsos.sort()
    lsos.reverse()

    res = []
    # Parse found objects.
    for lso in lsos:
        #print "Parsing lso", lso
        try:
            fp = file(lso[1], "rb")
            try:
                try:
                    n, d = parselso(fp)
                except (RuntimeError, NotImplementedError, AssertionError), msg:
                    ERROR("Parse error in LSO %s" % lso[1], -5)
                    continue
            finally:
                fp.close()
        except (IOError, OSError):
            # Ignore all file access errors.
            ERROR("Error while reading LSO %s" % lso[1], -20)
            continue

        # Found matching lso.
        if n == name:
            # Add meta data.
            d['__file__'] = lso[1]
            d['__modified__'] = lso[0]
            res.append((lso, d))
            if not init:
                break

    return res
        
def parselso(fp):
    """
    Parse lso raw data. Give file like object.
    Returns lso name, lso data dict.
    """
    
    parser = LSOParser()
    parser.parse(fp)
    
    return parser.name, parser.getData()

# VNC DES authentication:
# http://www.vidarholen.net/contents/junk/vnc.html
# See also: vnc/common/rfb/Password.cxx
VNCFIXEDKEY = pack("BBBBBBBB", *(23,82,107,6,35,78,88,7))

def getx11vncserver(windowid, localport=None, passwordfile=None):
    """
    Starts x11vnc session in new process environment.
    Returns pid, flagfile, logfile.
    """
    
    if localport is None:
        # Compute port number.
        # Make sure port is inside valid range.
        port = VNCSERVERPORTBASE + UID
        if port >= 65535:
            # too high
            port = 65535 - UID
        if port <= 10001:
            # too low
            port = 10001 + UID
        if port >= 65535:
            # o_O .. user id is very high??
            if UID < 65535:
                port = UID
            else:
                port = 15000 + int(UID/3)
    else:
        port = localport    
        LOG("using configured local x11vnc port %s" % port, 5)
    
    port=str(int(port))
    
    # Create flag file where to write port number.
    tmpdir = tempfile.gettempdir()
    flagfile = os.path.join(tmpdir, ".spreed-x11vnc-%s.dat" % port)
    logfile = os.path.join(tmpdir, ".spreed-x11vnc-%s.log" % port)
    
    # Remove eventually existing files.
    for f in (flagfile, logfile):
        if os.path.exists(f):
            try:
                os.unlink(f)
            except (IOError, OSError):
                # Well try to ignore errors here.
                ERROR("Unable to remove existing file %s" % f, -2)
                pass
    
    cmd = X11VNC
    args = [X11VNC]
    args.extend(["-id", windowid])
    args.extend(['-rfbport', port]) 
    args.append("-viewonly")
    if DEBUG < 5:
        # Set quiet mode to x11vnc. 
        args.append("-q")
    args.append("-once")
    args.append("-localhost")
    args.append("-norc")
    args.append("-nobell")
    args.append("-noremote")
    args.extend(["-timeout", "20"])
    args.extend(["-o", logfile])
    
    # Add password file.
    if passwordfile is not None:
        if not isinstance(passwordfile, basestring):
            # TempFile instance.
            passwordfile = passwordfile.name
        args.extend(["-rfbauth", passwordfile])
    
    if X11VNCVERSION == 0.8:
        args.append("-nofilexfer") # Not supported for x11vnc 0.7 and default for 0.9
    
    if X11VNCVERSION >= 0.8:
        # Add parameters only support by x11vnc 0.8 and up
        args.extend(['-flag', flagfile]) # Not supported on x11vnc 0.7
        args.append("-nocmds")     # Not supported for x11vnc 0.7
        #args.append("-noxdamage")  # XXX: find out why xdamage is so fucking slow, disable for now
        
    if X11VNCVERSION < 0.8:
        # We have to parse the logfile for anything older than 0.8.
        flagfile = None     

    if X11VNCVERSION < 0.7:
        # Show warning.
        LOG("WARNING: x11vnc version %s is very old and thus unsupported" % X11VNCVERSION, 0)
    
    # Check if we can use xshm extension.
    if not ISLOCALDISPLAY:
        LOG("WARNING: this is a remote display. Connection might be slow.", 0)
        args.append("-noshm")
    
    # Launch x11vnc.
    pid = os.spawnvpe(os.P_NOWAIT, cmd, args, os.environ)

    return pid, flagfile, logfile

def getwindowidandname():
    """
    Starts x11 window selection.
    Returns windowid, windowname.
    """

    cmd = [XWININFO]

    fp = os.popen(" ".join(cmd), "r")
    xwininfo = fp.read()
    res = fp.close()

    assert res == None, "xwininfo failed with status %s" % res

    res = xwininfo.split("\n")
    windowid = None
    windowname = None
    for l in res:
        l = l.strip()
        if not l.startswith("xwininfo:"): continue
        if l.find("Window id:") > 0:
            windowinfos = l.split(":", 1)[-1].strip()
            if windowinfos.startswith("Window id: "):
                windowinfos = windowinfos[11:]
                windowid, windowname = windowinfos.split(" ", 1)
                break

    try:
        assert windowid != None and windowname != None
    except AssertionError:
        ERROR("unable to parse xwininfo output", -1)

    LOG("Window %s, %s selected" % (windowid, repr(windowname)), 10)

    return windowid, windowname

def connectvnc2spreed(connection, conference, passwordfile=None, https_proxy=None):
    """
    Starts vnc2spreed.
    Returns pid.
    """
    
    if conference is None:
        # Oops. Called without conference data.
        return None, None

    # Create flag file where to write port number.
    tmpdir = tempfile.gettempdir()
    flagfile = os.path.join(tmpdir, ".spreed-vnc2spreed-%s.dat" % UID)
    
    # Remove eventually existing flag file.
    if os.path.exists(flagfile):
        try:
            os.unlink(flagfile)
        except (IOError, OSError):
            # Well try to ignore errors here.
            ERROR("Unable to remove existing file %s" % f, -2)
            pass

    cmd = VNC2SPREED
    args = [VNC2SPREED]
    
    # Password support.
    if passwordfile is not None:
        if not isinstance(passwordfile, basestring):
            # TempFile instance.
            passwordfile = passwordfile.name
        args.extend(["-P", passwordfile])
    else:
        # Avoid getting a password prompt anytime.
        args.extend(["-P", "/tmp/novncpasswordgiven"])

    # Connection data.        
    args.append(connection) # URL
    args.append(conference[0])
    args.append(conference[2])
    args.append(flagfile)
    
    # Get environment copy.
    env = os.environ.copy()
    
    # Set eventually configured proxy.
    if https_proxy:
        env["https_proxy"] = https_proxy
    
    pid = os.spawnvpe(os.P_NOWAIT, cmd, args, env)

    return pid, flagfile

def makepasswordfile(pw=None, encoded=False):
    """
    Creates a new file containg the bitflipped AES encrypted password.
    This file is returned as NamedTemporaryFile object.
    """

    password = None

    # Use given password (already encrypted).
    if pw is not None:
        password = pw
        if encoded:
            # Base64 encoded.
            password = base64.decodestring(password)
    else:
        # Generate random password.
        pw = ''.join([random.choice(string.ascii_letters+string.digits) for x in xrange(8)])
        
    if password is None:
        # Encrypt if not already done.
        d = vncdes.DesCipher(VNCFIXEDKEY)
        password = d.encrypt((pw+'\x00'*8)[:8]) # Note that only first 8 bytes are used.

    # Create file.
    fp = tempfile.NamedTemporaryFile()
    fp.write(password)
    fp.flush()
    
    return fp

def startuperrordialog(msg1, msg2=""):
    """
    Display a simple error dialog.
    """

    # Create new dialog.
    dialog = gtk.MessageDialog(None,
        gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
        gtk.MESSAGE_ERROR,
        gtk.BUTTONS_CLOSE)

    # Dialog defaults.
    dialog.set_title("spreed")
    dialog.set_icon_from_file(os.path.join(BASEPATH, "data", "spreed.png"))
    dialog.set_modal(True)
    dialog.set_position(gtk.WIN_POS_CENTER)
    dialog.set_border_width(5)
    dialog.set_has_separator(False)
    dialog.set_resizable(False) 
    
    # Set text.
    dialog.set_markup("<b>%s</b>\n%s" % (msg1, msg2))
    
    # Run dialog / This blocks!
    res = dialog.run()

    # Cleanup.    
    dialog.destroy() 
    
    return res
           
class GetwindowidandnameThread(Thread):
    """
    Simple thread which launches the window id getter.
    """
    
    callback = None

    def __init__(self, callback=None):
    
        self.callback = callback
        Thread.__init__(self)
        
    def run(self):
    
        LOG("Running selector threaded (%s)" % self.getName(), 10)
    
        # Start selector.
        windowid, windowname = getwindowidandname()
        
        if self.callback is not None:
            self.callback(windowid, windowname)

class NoTrayIcon:
    """
    Dummy class.
    """
    
    trayicon = None
    
    def __init__(self):
        pass

    def set_from_file(self, fn):
        pass

    def get_blinking(self):
        return False

    def set_blinking(self, value):
        return value

    def set_tooltip(self, msg):
        pass
        
    def set_visible(self, value):
        return value

    def connect(self, handler, callback):
        pass
        
    def get_position_in_tray(self):
        return 0, 0

class GtkTrayIcon:
    """
    Tray icon support for gtk >= 2.10.
    """

    trayicon = None

    def __init__(self):
        self.trayicon = StatusIcon()

    def set_from_file(self, fn):
        return self.trayicon.set_from_file(fn)

    def get_blinking(self):
        return self.trayicon.get_blinking()

    def set_blinking(self, value):
        return self.trayicon.set_blinking(value)

    def set_tooltip(self, msg):
        return self.trayicon.set_tooltip(msg)
        
    def set_visible(self, value):
        return self.trayicon.set_visible(value)

    def connect(self, handler, callback):
        return self.trayicon.connect(handler, callback)

    def get_position_in_tray(self):
        screen, area, orientation = self.trayicon.get_geometry()
        x, y = area.x, area.y
        if orientation is gtk.ORIENTATION_HORIZONTAL:
            y = y+12
        elif orientation is gtk.ORIENTATION_VERTICAL:
            y = y+12
        return x, y

class EggTrayIcon(GtkTrayIcon):
    """
    Tray icon support for gtk < 2.10.
    This requires python-gnome-extras and has limited features.
    """
    
    trayimage = None
    trayeb = None
    
    tooltip = None
    tooltip_data = ""
    
    on_press1_handler = None
    on_press2_handler = None    
    on_press3_handler = None
    
    blinking = None
    blinking_timeout = 800
    blinking_timeout_handler = None
    blinking_state = False
        
    def __init__(self):
        self.trayicon = egg.trayicon.TrayIcon('spreedX')
        
        # Create containers.
        self.trayeb = gtk.EventBox()
        self.trayimage = gtk.Image()
        
        # Initial states.
        self.trayeb.set_visible_window(False)
        self.trayeb.set_events(gtk.gdk.POINTER_MOTION_MASK)

        # Add stuff.    
        self.trayeb.add(self.trayimage)
        self.trayicon.add(self.trayeb)

        # Create tooltip.
        self.tooltip = EggToolTip()

        # Connect events
        self.trayeb.connect("button-press-event", self.on_button_press)
        self.trayeb.connect('motion-notify-event', self.on_motion_notify)
        self.trayeb.connect('leave-notify-event', self.on_leave_notify)
    
        # Connect blink callback.
        #self.blinking_timeout_handler = gobject.timeout_add(self.blinking_timeout, self.blink)
        
    def set_from_file(self, fn):
        # Create Image instance and add to tray.
        self.trayimage.set_from_file(fn)

    def blink(self, reset=False):
        """
        Called periodically.
        """
        if reset:
            self.blinking = False
            self.trayimage.show()
            return
        
        #print "blink", self.blinking, self.blinking_state
        
        if self.blinking:
            self.blinking_state = not self.blinking_state
            if self.blinking_state:
                # XXX: find way to hide only without freeing space!!
                self.trayimage.hide()
            else:
                self.trayimage.show()
        
        return True

    def get_blinking(self):
        """
        Returns if blinkin is currently enabled.
        """
        return self.blinking and True or False

    def set_blinking(self, value):
        """
        Configure blinking.
        """
        self.blink(reset=True)        
        self.blinking = value
        
    def set_tooltip(self, msg):
        """
        Set tooltip text.
        """
        self.tooltip_data = msg
        
    def set_visible(self, value):
        if value:
            self.trayicon.show_all()
        else:
            self.trayicon.hide_all()

    def connect(self, handler, callback):
        """
        Map connect to own handler names and methods.
        """
    
        if handler in ("destroy",):
            ob = self.trayicon
        else:
            ob = self.trayeb
            
        if handler == "activate": 
            self.on_press1_handler = callback
            return
        elif handler == "popup-menu":
            self.on_press3_handler = callback
            return
            
        return ob.connect(handler, callback)

    def on_button_press(self, widget, event):
        """
        Generic button press handler.
        """        
        self.on_leave_notify(widget, None)
        handler = getattr(self, 'on_press%s_handler' %  event.button)

        if handler is not None:
            return handler(widget, event.button, event.time)        

    def show_tooltip(self, widget):
        """
        Show current tooltip.
        """
        position = widget.window.get_origin()
        if self.tooltip.tid == position:
            # Position changed.
            size = widget.window.get_size()
            self.tooltip.show(self.tooltip_data, size[1], position[1])

    def on_motion_notify(self, widget, event):
        position = widget.window.get_origin()
        if self.tooltip.timeout > 0:
            if self.tooltip.tid != position:
                self.tooltip.hide_tooltip()
        if self.tooltip.timeout == 0 and self.tooltip.tid != position:
            self.tooltip.tid = position
            self.tooltip.timeout = gobject.timeout_add(500, self.show_tooltip, widget)

    def on_leave_notify(self, widget, event):
        position = widget.window.get_origin()
        if self.tooltip.timeout > 0 and self.tooltip.tid == position:
            self.tooltip.hide()

    def get_position_in_tray(self):
        coordinates=self.trayicon.window.get_origin()
        size=self.trayicon.window.get_size()
        return coordinates[0], coordinates[1]+12

class EggToolTip:
    """
    Simple tooltip class, used for tooltips when gtk is not
    cabable of handle it internally.
    """
    
    win = None
    position = None
    widget_height = None # We have to remember this to place on top.

    tid = None # Used to remember.
    timeout = None

    def __init__(self):
        self.position = [0, 0]
        self.timeout = 0
        self.tid = None
        self.win = None        
    
    def create(self):
        """
        Create new popup every time we want to show the tooltip.
        """    
    
        self.win = gtk.Window(gtk.WINDOW_POPUP)
        self.win.set_border_width(3)
        self.win.set_resizable(False)
        self.win.set_name('gtk-tooltips') # Use fixed id for tooltips to get correct color.
        
        self.win.set_events(gtk.gdk.POINTER_MOTION_MASK)
        self.win.connect_after('expose_event', self.on_expose)
        self.win.connect('size-request', self.on_size_request)
        self.win.connect('motion-notify-event', self.on_motion_notify)
        self.screen = self.win.get_screen()
        
    def on_motion_notify(self, widget, event):
        self.hide()
        
    def on_size_request(self, widget, requisition):
        """
        Compute size based on position and screen.
        """
        half_width = requisition.width / 2 + 1
        if self.position[0] < half_width: 
            self.position[0] = 0
        elif self.position[0]  + requisition.width > self.screen.get_width() + half_width:
            self.position[0] = self.screen.get_width() - requisition.width
        else:
            self.position[0] -= half_width 
            self.screen.get_height()
        if self.position[1] + requisition.height > self.screen.get_height():
            # Position on top.
            self.position[1] -= requisition.height  + self.widget_height + 8
        if self.position[1] < 0:
            self.position[1] = 0
        self.win.move(*self.position)                       

    def on_expose(self, widget, event):
        style = self.win.get_style()
        size = self.win.get_size()
        style.paint_flat_box(self.win.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT,
            None, self.win, 'tooltip', 0, 0, -1, 1)
        style.paint_flat_box(self.win.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT,
            None, self.win, 'tooltip', 0, size[1] - 1, -1, 1)
        style.paint_flat_box(self.win.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT,
            None, self.win, 'tooltip', 0, 0, 1, -1)
        style.paint_flat_box(self.win.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT,
            None, self.win, 'tooltip', size[0] - 1, 0, 1, -1)
        return True

    def add(self, data):
        """
        Add widget data. We use text label here.
        """
        self.create()
        self.win.add(gtk.Label(data))

    def show(self, data, widget_height, widget_y_position):
        """
        Show the tooltip for widget.
        Give widget height and the widget vertical position.
        """
        # Add data to tooltip.
        self.add(data)
        
        # Get the X position of mouse pointer.
        x = self.screen.get_display().get_pointer()[1]
        
        # Compute preffered y position.
        y = widget_y_position + widget_height + 4
        
        self.position = [x, y]
        self.widget_height = widget_height
        self.win.ensure_style()
        self.win.show_all()

    def hide(self):
        if self.timeout > 0:
            gobject.source_remove(self.timeout)
            self.timeout = 0
        if self.win:
            self.win.destroy()
            self.win = None
        self.tid = None

# Set Tray Icon implementation.
if GTKTRAY:
    BaseTrayIcon = GtkTrayIcon
elif EGGTRAY:
    BaseTrayIcon = EggTrayIcon
else:
    BaseTrayIcon = NoTrayIcon

class TimeoutThread(Thread):
    """
    Simple thread which launches the window id getter.
    """
    
    callback = None
    _stopped = True

    def __init__(self, timeout, callback=None):
    
        self.timeout = float(timeout)/1000.0
        if self.timeout < 1: self.timeout = 1
        self.callback = callback
        Thread.__init__(self)

    def stop(self):
        self._stopped = True
        
    def run(self):
    
        LOG("Running thread (%s)" % self.getName(), 10)
        self._stopped = False
    
        while not self._stopped:
            time.sleep(self.timeout)
            
            if self.callback is not None and not self._stopped:
                self.callback()

        LOG("Stopping thread (%s)" % self.getName(), 10)

class InotifyEventProcessor(ProcessEvent):
    """
    Parse inotify events and pass them to the application.
    """

    def __init__(self, callback):
        self.callback = callback
        ProcessEvent.__init__(self)

    def process(self, event):
    
        #print "event", os.path.join(event.path, event.name), event.event_name
        LOG("Inotify debug: %s %s/%s" % (repr(event), event.path, event.name), 99)
        
        if event.name == "%s.sol" % LSOBASENAME:

            LOG("Inotify event matched", 10)    
            lso = (datetime.datetime.utcnow(), os.path.join(event.path, event.name))
            
            try:
                fp = file(lso[1], "rb")
                try:
                    try:
                        n, d = parselso(fp)
                    except (RuntimeError, NotImplementedError, AssertionError), msg:
                        ERROR("Parse error in LSO %s" % lso[1], -5)
                        return
                finally:
                    fp.close()
            except (IOError, OSError):
                # Ignore all file access errors.
                ERROR("Error while reading LSO %s" % lso[1], -20)
                return

            # Add meta data.
            d['__file__'] = lso[1]
            d['__modified__'] = lso[0]
            
            data = {'inotify': True, 'lso': (lso, d)}
            self.callback(event=data)
        
    process_IN_CREATE = process
    process_IN_MODIFY = process
    process_IN_MOVED_TO = process

class SpreedApp(BaseTrayIcon):
    """
    Basic spreed application status icon.
    """
    
    TIMEOUT = 100 # Milliseconds.
    LSOSCAN = 1500 # Milliseconds.
    HEARTBEAT = 2000 # Milliseconds.

    window = None    
    selectorthread = None
    x11vnc = None
    vnc2spreed = None
    conference = None
    
    x11vncinuse = False
    vnc2spreedinuse = False
    
    passwordfile = None
    
    conference_from_init = None
    
    windowdisplayname = ""
    
    remoteconnection = None
    
    STATUS = STATUS_WAITING
    OLDSTATUS = STATUS_DISCONNECTED
    OLDERSTATUS = STATUS_DISCONNECTED
    
    DESKTOP_ENVIRONMENT = None
    
    LSOCACHE = None
    
    FIRSTHEARTBEAT = True
    
    # Open widgets.
    tree = None
    preferences = None
    startdlg = None
    currentdialog = None
    
    # Configuration.
    configuration = None
    configurationfile = None
    
    def __init__(self, conf=None):
    
        BaseTrayIcon.__init__(self)

        self.LSOCACHE = {}

        # Set desktop environment.
        self.DESKTOP_ENVIRONMENT = detectde()
        LOG("detected desktop environment %s" % self.DESKTOP_ENVIRONMENT, 5)

        # Get configuration data.
        self.readconfiguration(conf)

        # Get logdata from configuration.
        logfile = self.getconfiguration("log", "file")
        loglevel = int(self.getconfiguration("log", "level"))
            
        # Initialize log.
        if logfile: 
            if logfile.find(os.sep) == -1:
                logfile = os.path.join(SPREEDXBASE, logfile)
            LOG("initializing log file %s with debug level %s" % (logfile, loglevel), 10)
            INITIALIZELOG(logfile, level=loglevel)
            LOG("log file initialized", 10)

        # Context menu tree.
        menu = """
            <ui>
                <menubar name="Menubar">
                    <menu action="Menu">
                        <menuitem action="info" />
                        <!--<menuitem action="updates" />-->
                        <menuitem action="preferences"/>        
                        <separator/>                                        
                        <menuitem action="start"/>
                        <menuitem action="stop"/>
                        <separator/>
                        <menuitem action="exit"/>
                    </menu>
                </menubar>
            </ui>
        """

        # Build basic actions as group.
        actions = [
            ('Menu', None, 'Menu'),
            ('preferences', gtk.STOCK_PREFERENCES, '_Preferences', None, 'Change settings', self.on_preferences),
            ('exit', gtk.STOCK_QUIT, '_Exit', None, 'Exit application', self.on_exit),
            ('info', gtk.STOCK_ABOUT, '_Info', None, 'About', self.on_info),
            #('updates', None, 'Check for _update', None, 'Search for new version of spreed client for X', self.on_updates),            
            ('start', gtk.STOCK_MEDIA_RECORD, '_Share screen', None, 'Start to share the screen or a window', self.on_start),
            ('stop', gtk.STOCK_MEDIA_STOP, 'St_op screensharing', None, 'Stop screensharing', self.on_stop),
            ]

        # Add basic actions.
        ag = gtk.ActionGroup('Actions')
        ag.add_actions(actions)

        # Create manager.
        self.manager = gtk.UIManager()
        self.manager.insert_action_group(ag, 0)
        self.manager.add_ui_from_string(menu)
        self.menu = self.manager.get_widget('/Menubar/Menu/exit').props.parent

        # Get start stop references
        self.start = self.manager.get_widget('/Menubar/Menu/start')
        self.stop = self.manager.get_widget('/Menubar/Menu/stop')
        
        # Disable updates menu for now.
        #self.manager.get_widget('/Menubar/Menu/updates').set_sensitive(False)

        # Initialize status.
        self.status(threaded=False)        
        self.set_status(STATUS_DISCONNECTED)
        
        # Show us.
        self.set_visible(True)

        # Connect first actions.
        self.connect('activate', self.on_activate)
        self.connect('popup-menu', self.on_popup_menu)
        
    def dialog(self, title, msg, type=gtk.MESSAGE_INFO, buttons=gtk.BUTTONS_OK, callback=None):
        """
        Display a dialog and wait for user input.
        """
        
        if self.currentdialog is not None:
            # Kill existing open dialog (without calling the callback).
            try:
                self.currentdialog.destroy()
            except (AttributeError, KeyError):
                pass
            self.currentdialog = None
            
        # Create new dialog.
        self.currentdialog = dialog = gtk.MessageDialog(parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, type=type, buttons=buttons)
        
        # Set parameters.
        dialog.set_title(title)
        dialog.set_icon_from_file(os.path.join(BASEPATH, "data", "spreed.png"))
        dialog.set_modal(True)
        dialog.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
        dialog.set_border_width(5)
        dialog.set_resizable(False)

        # Set text.
        dialog.set_markup("%s" % msg)
        
        # Connect response.
        dialog.connect('response', self.on_dialog_result, callback)
        dialog.connect('close', self.on_dialog_result, None, callback)        
        
        # Show it.
        dialog.show()
        dialog.present()
        
        # Urgency.
        if hasattr(dialog, "set_urgency_hint"):
            dialog.set_urgency_hint(True)

    def notify(self, title=None, message="", timeout=2000, icon=True, stock_icon=None, stock_icon_size=gtk.ICON_SIZE_DIALOG):
        """
        Display a notification tooltip.
        """
    
        if PYNOTIFY and title:
            x,y = self.get_position_in_tray()
            if stock_icon is None and icon:
                uri = "file://%s" % os.path.join(BASEPATH, "data", "spreed-big.png")
            else:
                uri = None
            n = pynotify.Notification(title, message, uri)
            n.set_hint("x", x)
            n.set_hint("y", y)
            n.set_timeout(timeout) # milliseconds
            if stock_icon is not None:
                helper = gtk.Button()
                icon = helper.render_icon(stock_icon, stock_icon_size)
                n.set_icon_from_pixbuf(icon)
                
            n.show()        

    def on_dialog_result(self, dialog, result, callback=None):
        
        # Reset reference.
        if dialog == self.currentdialog:
            self.currentdialog = None
        
        # Hide dialog window.
        dialog.hide()

        try:
            if callback is not None:
                return callback(dialog, result)
        finally:
            # Destroy it.
            dialog.destroy()   

    def readconfiguration(self, conf=None):
        """
        Reads configuration file.
        """
        
        if conf is not None:
            # Read configuration.
            LOG("Reading configuration from %s" % conf, 10)
            fp = file(conf, "rb")
            xml = fp.read()
            fp.close()
            
            # Remember filename.
            self.configurationfile = conf
            
        else:
            xml = DEFAULTCONFIGURATION

        # Parse configuration.
        try:
            self.configuration = minidom.parseString(xml).getElementsByTagName("spreedconnectionconfig")[0]
        except KeyboardInterrupt:
            raise
        except Exception:
            ERROR("Error in configuration.", -1)
            raise
        
        # Parse default configuration.
        defaultconfiguration = minidom.parseString(DEFAULTCONFIGURATION).getElementsByTagName("spreedconnectionconfig")[0]
        
        # Get configuration version.
        version = self.configuration.getAttribute("version")
        currentversion = defaultconfiguration.getAttribute("version").split(".")
        
        if not version:
            version = "0.0"
            
        # Strip whitespace.
        version = version.strip()
        
        LOG("Configuration version %s found" % version, 10)
        version = version.split(".")
        
        if version < currentversion:
            # Update configuration.
            LOG("outdated configuration version found (%s < %s)" % (".".join(version), ".".join(currentversion)), 1)

            write = None            
            for c in defaultconfiguration.childNodes:
                if c.nodeType not in (defaultconfiguration.ELEMENT_NODE,):
                    continue
                
                f = self.configuration.getElementsByTagName(c.tagName)
                if not len(f):
                    # Clone and insert this node from default.
                    n = c.cloneNode(100)
                    self.configuration.appendChild(n)
                    write = True

            # Update version.
            self.configuration.setAttribute("version", ".".join(currentversion))
                    
            # Write it.
            LOG("configuration was updated to version %s" % ".".join(currentversion), 1)
            self.writeconfiguration(conf)

    def writeconfiguration(self, conf=None):
        """
        Write configuration file.
        """

        if conf is None:
            conf = self.configurationfile

        assert self.configuration is not None, "configuration not available"
        
        # Generate xml string.
        xml = self.configuration.toxml()
        
        # Write into file.
        fp = file(conf, "wb")
        fp.write(xml)
        fp.close()
        
    def getconfiguration(self, group, name, astext=False, decrypt=False, key=VNCFIXEDKEY, default=[]):
        """
        Get configuration parameter with default support.
        """
        
        try:
            return self._getconfiguration(group=group, name=name, astext=astext, decrypt=decrypt, key=key)
        except IndexError:
            if default != []:
                return default
            else:
                raise
        
    def _getconfiguration(self, group, name, astext=False, decrypt=False, key=VNCFIXEDKEY):
        """
        Get configuration parameter.
        """
        
        g = group
        n = name
        
        try:
            group = self.configuration.getElementsByTagName(group)[0]
        except IndexError:
            ERROR("Configuration has no group %s." % group, -5)
            raise
        
        try:
            name = group.getElementsByTagName(name)[0]
        except IndexError:
            ERROR("Configuration group %s has no entry %s." % (group, name), -5)
            raise
            
        # Either use value attribute value or text content.
        value = None
        if name.hasAttribute("value"):
            value = name.getAttribute("value")
        elif name.hasChildNodes():
            # Get textnode value.
            value = name.firstChild.nodeValue

        # Strip.
        if isinstance(value, basestring):
            value = value.strip()

        # Decryption support.
        if decrypt and value:
            value = base64.decodestring(value)
            d = vncdes.DesCipher(key)
            value = d.decrypt(value)
            value = value.replace("\x00", "") # Remove eventually added null bytes.

        if astext:
            return value

        # Boolean support.
        if value is None:
            pass
        elif value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
            
        return value
        
    def setconfiguration(self, group, name, value, cdata=False, encrypt=False, key=VNCFIXEDKEY):
        """
        Set configuration parameter.
        """

        # Boolean support.
        if isinstance(value, bool):
            if value: 
                value = "true"
            else: 
                value = "false"

        # Encryption support.
        if encrypt:
            d = vncdes.DesCipher(key)
            value = d.encrypt(value)
            value = base64.encodestring(value).strip()
            cdata = True # Always CDATA.

        group = self.configuration.getElementsByTagName(group)[0]
        
        try:
            element = group.getElementsByTagName(name)[0]
        except IndexError:
            # Not yet there -> create new element.
            element = None

        if element is None:
            # Create new node.
            element = group.ownerDocument.createElement(name)
            group.appendChild(element)

        if element is not None:
            # Modifiy existing.
            if element.hasAttribute("value") and not cdata:
                element.setAttribute("value", value)
            else:
                if element.hasChildNodes():
                    # Remove existing subnode.                
                    element.removeChild(element.firstChild)
                if cdata:
                    # Add new node as CDATA.
                    element.appendChild(element.ownerDocument.createCDATASection(value))
                else:
                    # Add new one as text node.
                    element.appendChild(element.ownerDocument.createTextNode(value))

        self.writeconfiguration()

    def on_activate(self, data, *args, **kw):
        #print "activate", data
        
        if self.STATUS in (STATUS_WAITING, STATUS_DISCONNECTED):
            return
        elif self.STATUS in (STATUS_RUNNING, STATUS_USERINPUT, STATUS_CONNECTING):
            self.on_stop(data)
        elif self.STATUS in (STATUS_STOPPED,):
            self.on_start(data)
        else:
            # Ignore all other states.
            return

    def on_dialog_closed(self, dialog, status):
        """
        General closed handler example for dialogs.
        """
        pass

    def on_popup_menu(self, status, button=None, time=None):
        if button is None: button = 3
        if time is None: time = 0
        self.menu.popup(None, None, None, button, time)

    def on_info(self, data):
        # print "info", data
        return self.on_preferences(data, starttab=2)
        
    def on_updates(self, data):
        # print "update", data
        pass

    def on_preferences(self, data, starttab=0):
        #print "preferences", data
        
        preferences = self.preferences

        if preferences is None:        
            self.preferences = preferences = self.get_widget("preferences-window")

        # Always begin with correct tab.
        self.get_widget("preferences-notebook").set_current_page(starttab)

        # Show it.
        preferences.show()
        preferences.present()

    def preferences_data_changed(self, widget):
        """
        Changes preferences data.
        """
        group, name = widget.get_name().split("-", 1)
        
        # At first display actions.
        if isinstance(widget, gtk.RadioButton):
            # Display eventually existing details.
            name = "%s-%s-details" % (group, name)
            details = self.get_widget(name)

            if details is not None:
                details.set_sensitive(widget.get_active())
                
        elif isinstance(widget, gtk.CheckButton):

            invert = False
            if name.find("-") != -1:        
                n, i = name.split("-", 1)
                if i == "true": invert = True
            
            v = widget.get_active()
            if invert: v = not v
        
            for x in (v, not v):

                # Display eventually existing details.
                n = "%s-%s-%s-details" % (group, name, str(x).lower())
                details = self.get_widget(n)
                
                if details is not None:
                    details.set_sensitive(v)
        
        if isinstance(widget, gtk.Entry):
        
            value = widget.get_text()
            encrypt = False
            
            if name.endswith("password"):
                if value == "NOTCHANGED123spr":
                    # Do nothing.
                    return
                else:
                    if value:
                        # We store passwords encrypted and base64 encoded.
                        value = (value+'\x00'*8)[:8]
                        encrypt = True
                    else:
                        value = ""
        
            self.setconfiguration(group, name, value, encrypt=encrypt)
            
        elif isinstance(widget, gtk.RadioButton):
        
            widgets = widget.get_group()
            
            value = None
            for w in widgets:
                g, n = w.get_name().split("-", 1)
                n = n.split("-",1)
                if len(n) == 2:
                    n, v = n
                    if v == "true":
                        v = True
                    elif v == "false":
                        v = False
                else:
                    n = n[0]
                    v = True
                    name = n
                    
                if w.get_active():
                    value = v

            if value is not None:
                self.setconfiguration(group, name, value)

        elif isinstance(widget, gtk.CheckButton):
           
            invert = False
            if name.find("-") != -1:
                name, i = name.split("-", 1)
                if i == "false": invert = True
                
            value = widget.get_active()
            if invert: value = not value
            
            if value is not None:
                self.setconfiguration(group, name, value)

    def preferences_data_show(self, widget):
        """
        Displays preferences.
        """
        
        group, name = widget.get_name().split("-", 1)
        
        defaults = {"localport": "5900",
                    "localauto": True
                    }
        
        if isinstance(widget, gtk.Entry):
            # Simple to fill text areas.
            try:
                value = self.getconfiguration(group, name)
            except IndexError:
                value = defaults.get(name, None)

            if value is None:
                value = ""
            if value.strip() == "" and defaults.get(name, None):
                value = defaults.get(name)

            if name.endswith("password") and value:
                # Password field support.
                value = "NOTCHANGED123spr"

            # Set to widget.
            widget.set_text(value)
        
        elif isinstance(widget, gtk.RadioButton):
            # Select correct radiobutton stuff.
            
            try:
                value = self.getconfiguration(group, name, astext=True)
            except IndexError:
                value = defaults.get(name, None)
            
            if value is not None:

                widgets = widget.get_group()
                selected_name = "%s-%s-%s" % (group, name, value)
            
                # Use first widget as default.
                selected_widget = widget
            
                # Check if value matches some widget.
                for w in widgets:
                    if w.get_name() == selected_name:
                        selected_widget = w
                
                # Set value.
                selected_widget.set_active(True)

        elif isinstance(widget, gtk.CheckButton):
            
            invert = False
            if name.find("-") != -1:        
                name, i = name.split("-", 1)
                if i == "false": invert = True
                
            try:
                value = self.getconfiguration(group, name)
                if invert: value = not value
            except IndexError:
                value = defaults.get(name, None)
                
            if value is not None:
                widget.set_active(bool(value))

    def on_preferences_close(self, widget, event=None):
        if self.preferences is not None:
            self.preferences.hide()
        
    def on_start_result(self, widget, result=gtk.RESPONSE_OK):
        """
        Called when start button was pressed.
        """

        if self.startdlg is not None:
            self.startdlg.hide()

        # Discover if configured to start VNC on local display.
        local = self.getconfiguration("general", "local")
        
        # Discover if selected to share whole screen.
        desktop = False
        try:
            desktop = self.get_widget("share-desktop").get_active()
        except AttributeError:
            pass

        # Support to share whole screen without selection.
        if desktop:
            LOG("Getting current screen window id", 10)
            
            windowid = getcurrentscreenwindowid()
            if windowid is not None:
                self.window = (windowid, "Current screen", True)
                LOG("Selected current screen window id %s" % windowid, 5)
            else:
                LOG("Unable to get current screen x window id", 1)

        # Either selected a window / or a whole desktop
        if self.window:        
            windowid, windowname, status = self.window
            
            if status:
                if result in (gtk.RESPONSE_OK, gtk.RESPONSE_YES):
                    self.window = (windowid, windowname, False)
                    LOG("Confirmed sharing of window %s" % windowid, 5)
                    self.set_status(STATUS_USERINPUT)
                else:
                    LOG("Abort sharing of window %s by user action (%s)" % (windowid, result), 4)
                    self.set_status(STATUS_WAITING)
                    
        elif not local:

            # Use remote VNC sever.
            
            LOG("remote vnc mode requested", 5)
            remoteaddr = self.getconfiguration("general", "remoteaddr")
            
            if remoteaddr.find(":") != -1:
                # Display given.
                remoteaddr, remotedisplay = remoteaddr.split(":", 1)
            else:
                remotedisplay = 0
            
            # Add VNC base port number to get port from display number.
            remoteport = int(remotedisplay)+5900
            
            # Set as connection data.
            connection = "%s:%s" % (remoteaddr, remoteport)
            LOG("using %s as connection data" % connection, 2)
            self.remoteconnection = connection
            
            # Set status.
            self.set_status(STATUS_USERINPUT)
            
        else:
            LOG("Uhm .. no action taken as there is neither a window id nor a remote server", 1)

    def on_start_selector_result(self, windowid, windowname):
        """
        Called when a window id was recieved.
        """
        
        LOG("window selector returned successfully", 10)
        self.set_status(STATUS_STOPPED)

        if windowid is not None:
            # Notify worker.
            self.window = (windowid, windowname, True)
            LOG("Set to share local window %s, %s" % (windowid, repr(windowname)), 5)
                
        else:
            LOG("did not retrieve a window id ... cannot start", 1)

        # Cleanup thread.
        self.selectorthread = None

    def on_start_selector(self, data):
        """
        Launch start selector.
        """
        
        # Start selector threaded.
        self.set_status(STATUS_USERINPUT)
        self.selectorthread = GetwindowidandnameThread(self.on_start_selector_result)
        self.selectorthread.start()
        LOG("Selector thread started.", 10)
        
    def on_start_close(self, widget, event=None):
        # Reset eventually existing window selection.
        self.window = None
        self.set_status(STATUS_WAITING)
    
        if self.startdlg is not None:
            self.startdlg.hide()

    def start_data_show(self, widget):
        #print "start data show", widget
        
        defaults = {'share': 'single',
                    'share-single-window-title': self.windowdisplayname,
                   }

        if isinstance(widget, gtk.RadioButton):

            name, value = widget.get_name().split("-", 1)
        
            widgets = widget.get_group()
            
            for w in widgets:
                name, value = w.get_name().split("-", 1)        
        
                if defaults.has_key(name) and defaults.get(name) == value:
                    w.set_active(True)
                    break
                    
        elif isinstance(widget, gtk.Entry):
            
            name = widget.get_name()
        
            if defaults.has_key(name):
                widget.set_text(defaults.get(name))
        
    def start_data_changed(self, widget):
        #print "start data changed", widget

        # At first display actions.
        if isinstance(widget, gtk.RadioButton):
        
            # Display eventually existing details.
            name = "%s-details" % (widget.get_name())
            details = self.get_widget(name)

            if details is not None:
                details.set_sensitive(widget.get_active())

        # Check if local is false -> then display further options.
        try:
            local = self.getconfiguration("general", "local")
        except IndexError:
            local = None

        # Get state for start button.
        state = False
        
        if self.get_widget("share-desktop").get_active():
            state = True
        elif self.get_widget("share-single").get_active() and self.window:
            state = True
        elif self.get_widget("share-remote").get_active() and local in (False,):
            state = True
        else:
            pass
            
        # Set state for start button.
        self.get_widget("share-start-button").set_sensitive(state)

    def on_start(self, data):
        #print "start", data
        
        startdlg = self.startdlg
        
        if startdlg is None:        
            self.startdlg = startdlg = self.get_widget("start-window")

        # Urgency.
        if hasattr(startdlg, "set_urgency_hint"):
            startdlg.set_urgency_hint(True)

        # Check if local is false -> then display further options.
        local = self.getconfiguration("general", "local")
        
        try:
            if not local:
                self.get_widget("share-remote-option").show()
            else:
                self.get_widget("share-remote-option").hide()
        except AttributeError:
            pass        

        # Show start dialog window.
        startdlg.show()
        startdlg.present()

    def on_stop(self, data):
        #print "stop", data
        self.set_status(STATUS_WAITING)
        self.stop_all()

    def on_exit(self, data):
        #print "exit", data
        self.on_exit_cleanup()
        gtk.main_quit()

    def on_exit_cleanup(self):
        self.manage_threads("stop")
        self.manage_threads("join")    
        self.set_status(STATUS_WAITING)
        self.stop_all(wait=True)

    def manage_threads(self, method_name):
        """
        Handles commands to threads.
        """
        for t in self.threads.get():
            m = getattr(t, method_name)
            m()

    def create_threads(self):
        """
        Creats the async threads.
        """
        
        class threadcontainer:
            def __init__(self):
                self._t = []
            def add(self, name, thread):
                setattr(self, name, thread)
                self._t.append(name)
            def get(self):
                return [getattr(self, x) for x in self._t]
                
        self.threads = threadcontainer()
        self.threads.add('workthread', TimeoutThread(self.TIMEOUT, self.work))
        self.threads.add('statusthread', TimeoutThread(self.TIMEOUT, self.status))
        if INOTIFY_WM:
            self.threads.add('scanthread', ThreadedNotifier(INOTIFY_WM, InotifyEventProcessor(self.scan)))        
        else:
            self.threads.add('scanthread', TimeoutThread(self.LSOSCAN, self.scan))
        self.threads.add('heartbeatthread', TimeoutThread(self.HEARTBEAT, self.heartbeat))
        
    def main(self):
        """
        Start main loop.
        """
    
        def main_func(self):
    
            # Initialize lso cache.
            self.scan(init=True, threaded=False)
        
            # Start worker threads.
            self.manage_threads("start")
            
            if INOTIFY_WM:
                # Register inotify watches
                LOG("Inotify support enabled. Listening at %s (recursive)." % (LSOBASE), 1)
                INOTIFY_WM.add_watch(LSOBASE, EventsCodes.ALL_FLAGS["IN_CREATE"] | EventsCodes.ALL_FLAGS["IN_MODIFY"] | EventsCodes.ALL_FLAGS["IN_MOVED_TO"], rec=True, auto_add=True)

        # Create worker threads.
        self.create_threads()

        # Call initial stuff threaded.
        t = Thread(target=main_func, name="main_func", args=(self,))
        t.start()
        
        try:
            # Start main loop. (This blocks!)
            gtk.main()
        finally:    
            t.join()

    def get_widget(self, name):
        """
        Returns glade widgets.
        """

        if self.tree is None:
            # Parse glade file.
            self.tree = gtk.glade.XML(os.path.join(BASEPATH, "data", "spreedX.glade"))
            # Widget handlers.
            treehandlers = {
                "preferences_window_delete": self.on_preferences_close,
                "configuration_show": self.preferences_data_show,
                "configuration_changed": self.preferences_data_changed,
                "start_window_delete": self.on_start_close,
                "start_show": self.start_data_show,
                "start_changed": self.start_data_changed,
                "start_selector-button_clicked": self.on_start_selector,
                "start_start-button_clicked": self.on_start_result,
            }
            self.tree.signal_autoconnect(treehandlers)
        
        return self.tree.get_widget(name) 

    def set_status(self, status, nodecrease=False):
        """
        Set new status.
        Returns True if status has changed.
        """
        
        if self.STATUS != status:
        
            if nodecrease and self.STATUS > status:
                # Avoid decreasing status when requested.
                return False
                
            self.STATUS = status
            LOG("switched status to %s" % status, 10)
            return True
        else:
            return False

    def stop_all(self, wait=False):
        """
        Stop started programs (all of them).
        """
        
        for tool in (self.vnc2spreed, self.x11vnc):
            if tool is not None:
                pid = tool[0]
                LOG("Terminating child %s" % pid, 5)
                os.kill(pid, signal.SIGKILL)
                
                if wait:
                    LOG("Waiting for exit of child %s" % pid, 5)
                    try:
                        res = os.waitpid(pid, os.P_WAIT)
                        LOG("Child quit (%s)" % repr(res), 10)
                    except OSError:
                        LOG("Child already gone", 10)

    def scan(self, init=False, threaded=True, event=None):
        """
        Called periodically.
        """
        
        #print "scan", event
        
        if event:
            if event.get('inotify'):
                # Got inotify event.
                if event['lso'][0] in self.LSOCACHE:
                    # This does never happen?! Does it?
                    return
                else:
                    # Fill cache required for inotify?
                    self.LSOCACHE[event['lso'][0]]=True
                    # Take lso from event.
                    lsos = [event['lso']]
            else:
                # What kind of event is this -> ignore.
                return
        
        else:
            # Search for newest matching lso or None. Suboptimal ..
            # This is called at least once, at application startup, even with inotify.
            lsos = getlsodata(ignore=self.LSOCACHE, init=init)
        
            for lso in lsos:
                # Fill cache.
                self.LSOCACHE[lso[0]]=True            
        
        # Use newest lsos.        
        for lso in lsos[:1]:
            #print "NEW LSO", lso[0]
            data = lso[1]
        
            # Build required stuff from lso data.
            try:
                port = int(data["port"])
                host = data["url"]
                path = data["path"]
                ticket = data["ticket"]
                conferenceid = data["conferenceId"]
                action = data["action"]
            except KeyError, msg:
                ERROR("invalid or incomplete lso data", -1)
                continue
            
            # Get protocol.
            if port == 443:
                protocol = "https"
                port = ""
            elif port == 80:
                protocol = "http"
                port = ""
            else:
                protocol = "http"
                port = ":%s" % port
            
            # Make sure there are enough slashes.
            if not path:
                path = '/'
            else:
                if not path.startswith('/'):
                    path = "/%s" % path
                if not path.endswith('/'):
                    path = "%s/" % path
            
            # Build connection url.
            uri = "%s://%s%s%s%s" % (protocol, host, port, path, conferenceid)
            
            LOG("LSO event %s for conference id %s" % (action, conferenceid), 5)
            LOG("LSO URI %s" % uri, 10)
            #print "action", action
            #print "uri", uri
            #print "conferenceid", conferenceid
            #print "ticket", ticket
        
            # Existing conference connection?
            if self.conference is not None:
                if self.conference != (uri, conferenceid, ticket):
                    # o_O different data. Stop existing stuff.
                    self.stop_all()
                    self.set_status(STATUS_DISCONNECTED)
            
            # Get action (known: screensharingVisible,
            #                    screensharing,
            #                    remoteAccess,
            #                    stopScreensharing,
            #                    stopRemoteAccess)
        
            # Remember if from init.
            self.conference_from_init = init

            # Implement actions.
            if action in ("screensharing",):
                # This starts screensharing.
                self.conference = (uri, conferenceid, ticket)
            elif action in ("stopScreensharing", "stopRemoteAccess"):
                # This stops eventually running tools.                
                if self.STATUS in (STATUS_RUNNING,):
                    LOG("Stop streaming by LSO request", -3)                        
                    self.stop_all()
                else:
                    LOG("Disconnect from conference by LSO request", -3) 
                    self.conference = None
            elif action in ("remoteAccess",):
                # This starts remotecontrol.
                if os.environ.get("ENABLE_REMOTECONTROL", False):
                    self.conference = (uri, conferenceid, ticket)
                else:
                    LOG("Unsupported LSO action %s" % action, -1)
                    if threaded: 
                        gtk.gdk.threads_enter()
                    self.dialog("spreed information", "<b>This feature is not yet available</b>\nRemote control is not available for your platform at the moment.", type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
                    if threaded: 
                        gtk.gdk.threads_leave()
            else:
                LOG("Unsupported LSO action %s" % action, -1)
                
        return True

    def heartbeat(self):
        """
        Called periodically and sends heartbeats.
        """
        
        #print "heartbeat"
        
        # Get local variables.
        conference = self.conference
        
        if conference and self.STATUS in (STATUS_WAITING, STATUS_STOPPED, STATUS_RUNNING, STATUS_USERINPUT, STATUS_CONNECTING):
            
            # Get correct subtype.
            if self.STATUS in (STATUS_WAITING, STATUS_USERINPUT, STATUS_STOPPED, STATUS_CONNECTING):
                subtype = "running"
            elif self.STATUS in (STATUS_RUNNING,):
                subtype = "capturing"
            else:
                subtype = None

            # When a subtype is found -> send heartbeat.            
            if subtype is not None:

                # Parse url.
                uri, conferenceid, ticket = conference
                uri = urlparse.urlparse(uri)

                proxy_handler = None
                proxy_auth_handler = None

                handlers = []

                # Check if we have to use proxy.
                if not self.getconfiguration("connection", "direct", default=False):
                    #LOG("Heartbeat proxy configuration detected.", 10)
                    proxyaddr = self.getconfiguration("connection", "proxyaddr", default=None)
                    proxyusername = self.getconfiguration("connection", "proxyusername", default=None)
                    proxypassword = self.getconfiguration("connection", "proxypassword", decrypt=True, default=None)

                    if proxyaddr:
                        #LOG("Using heartbeat proxy at %s" % proxyaddr, 10)
                    
                        if proxyusername is not None and proxypassword:
                            #LOG("Using heartbeat proxy authentication", 10)                                            
                            authority = "%s:%s@%s" % (proxyusername, proxypassword, proxyaddr)
                        else:
                            authority = "%s" % proxyaddr
                    
                        # Use proxy CONNECT handlers.
                        handlers = [urllib2.ProxyHandler(proxies={"http": authority, "https": authority}), proxysupport.ConnectHTTPSHandler, proxysupport.ConnectHTTPHandler]
                
                # Default handlers without proxy.
                if not handlers:
                    handlers = [urllib2.HTTPSHandler, urllib2.HTTPHandler]
                
                # Get opener.                
                opener = urllib2.build_opener(*handlers)
                
                # Build url.
                url = "%s://%s%s" % (uri[0], uri[1], "/".join(uri[2].split("/")[:-1]))
                
                # Build request.
                request = urllib2.Request(url)
                request.add_header("User-agent", "spreedX/%s-%s" % (__version__, sys.platform))
                request.add_header("Content-Type", "application/x-flv-heartbeat;%s" % subtype)
                request.add_header("X-spreed-ticket", "%s" % ticket)
                request.add_header("X-spreed-conference", "%s" % conferenceid)
                request.add_data("\x01")
                
                res = None
                status = None
                msg = None
                
                # Connect.
                try:
                    res = opener.open(request)
                    status = 200
                except urllib2.HTTPError, msg:
                    # Error code.
                    res = False
                    status = msg.code
                    msg = msg.msg
                    pass
                except urllib2.URLError, msg:
                    ERROR("Timeout or error while waiting for heatbeat", -2)
                    self.conference = None
                    gtk.gdk.threads_enter()
                    self.dialog("spreed disconnected", "<b>Connection failed</b>\nThe remote connection could not be established (%s). Please check your internet connection settings." % repr(msg.reason), type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
                    gtk.gdk.threads_leave()                
                
                # No unexpected connection error.
                if res is not None:
                                    
                    if not self.FIRSTHEARTBEAT:
                
                        if status in (200,):
                            # Heartbeat beats.
                            if self.STATUS in (STATUS_WAITING,):
                                # Set status to stopped on first successfull heartbeat.
                                self.set_status(STATUS_STOPPED)
                        elif status in (406,):
                            # Heartbeat reject.
                            if self.STATUS in (STATUS_RUNNING,):
                                LOG("Stop streaming by heartbeat reject (%s)" % msg, -3)                        
                                self.stop_all()
                            else:
                                LOG("Disconnect from conference by heartbeat reject (%s)" % msg, -3) 
                                self.conference = None
                        elif status in (401,):
                            # No access to conference.
                            if self.STATUS in (STATUS_RUNNING,):
                                LOG("Stop streaming by conference auth failure (%s)" % msg, -3)
                                self.stop_all()
                            else:
                                LOG("Disconnect from conference cause auth failed (%s)" % msg, -3)
                                self.conference = None
                        else:
                            # Heartbeat error.
                            LOG("Heartbeat status error (%s) (%s)" % (status, msg), -1)
                            gtk.gdk.threads_enter()
                            self.dialog("spreed connection error", "<b>Connection trouble</b>\nThe remote connection could not be stablished (%s - %s). Please check your internet connection settings." % (status, repr(msg)), type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
                            gtk.gdk.threads_leave()
                            self.conference = None
                            
                    else:
                        # First heartbeat response. Do nothing here cause
                        # server does not know the correct state yet.
                        LOG("Ignoring first hearbeat response %s" % status, 10)
                        self.FIRSTHEARTBEAT = False

                    # Make sure to read.
                    if status not in (200,):
                        LOG("Response %s data %s" % (status, repr(msg)), 10)
                    
        return True

    def status(self, threaded=True):
        """
        Called periodically.
        """
        #print "status"

        # Get to local vars.
        OLDERSTATUS = self.OLDERSTATUS 
        OLDSTATUS = self.OLDSTATUS
        STATUS = self.STATUS
        
        if STATUS in (STATUS_WAITING,):
            if self.vnc2spreed is None:
                pass
            else:
                self.set_status(STATUS_RUNNING)

        # Set window display name.
        if self.window:
            windowname = self.window[1]
        else:
            windowname = None
            
        # Compute displayable name.
        if windowname and not windowname.strip():
            windowname = "(has no name)"
        
        if windowname is None:
            windowname = ""
            
        # Set to us and display widgets.
        if windowname != self.windowdisplayname:
            # Name changed.
            self.windowdisplayname = windowname
            # Update widget.
            gtk.gdk.threads_enter()
            self.get_widget("share-single-window-title").set_text(self.windowdisplayname)
            gtk.gdk.threads_leave()

        def toggle(component, sensitive):
            #if component.get_sensitive() != sensitive:
            component.set_sensitive(sensitive)

        if threaded: 
            gtk.gdk.threads_enter()
        if STATUS in (STATUS_RUNNING, STATUS_CONNECTING):
            toggle(self.start, False)
            toggle(self.stop, True)
        elif STATUS in (STATUS_STOPPED,):
            toggle(self.start, True)
            toggle(self.stop, False)
        else:
            toggle(self.start, False)
            toggle(self.stop, False)
        if threaded:
            gtk.gdk.threads_leave()            
        
        # Update status icon.
        if OLDSTATUS != STATUS:
            # Changed since last loop.
            if STATUS in (STATUS_RUNNING,):
                icon = "spreed-enabled.png"
                msg = "Enabled."
                if self.window:
                    msg = "%s\nSharing: %s" % (msg, repr(self.windowdisplayname))
            elif STATUS in (STATUS_CONNECTING, STATUS_USERINPUT):
                icon = "spreed-waiting.png"
                msg = "Connecting ..."                
            elif STATUS in (STATUS_STOPPED,):
                icon = "spreed.png"
                msg = "Stopped."
            elif STATUS in (STATUS_DISCONNECTED,):
                icon = "spreed-disabled.png"
                msg = "No conference connection!"
            else:
                icon = "spreed-disabled-waiting.png"
                msg = "Please wait ..."

            if threaded:
                gtk.gdk.threads_enter()

            # Set icon. 
            icon = os.path.join(BASEPATH, "data", icon)
            #print "setting icon", icon
            self.set_from_file(icon)

            # Blinking.
            if STATUS in (STATUS_RUNNING, STATUS_CONNECTING):
                if not self.get_blinking():
                    self.set_blinking(True)
            else:
                if self.get_blinking():
                    self.set_blinking(False)

            if self.conference is not None:
                connected = " - connected to meeting"
            else:
                connected = ""

            # Set tooltip.
            self.set_tooltip('spreed%s - %s' % (connected, msg))

            if threaded:
                gtk.gdk.threads_leave()            
            
            # Popup stuff.
            if self.conference is not None:
            
                if STATUS in (STATUS_STOPPED,) and OLDERSTATUS in (STATUS_DISCONNECTED, STATUS_ERROR,):
                    if threaded: 
                        gtk.gdk.threads_enter()                
                    self.notify("Connection established", "Screen sharing can now be started.")
                    if not self.conference_from_init:
                        # Show start popup as user pressed share in flash and client running.
                        self.on_start(None)
                    else:
                        # Show popup when new connection to conference is there and called while start.
                        #self.dialog("spreed notice", "<b>Conference connection established!</b>\nYou can now start screensharing.")
                        pass
                    if threaded: 
                        gtk.gdk.threads_leave()            
            
                elif STATUS in (STATUS_RUNNING,):
                    if threaded: 
                        gtk.gdk.threads_enter()                
                    self.notify("Sharing active", "Screen sharing is enabled and activated. To stop sharing, click on the tray icon.", timeout=4000)
                    if threaded: 
                        gtk.gdk.threads_leave()    

                elif STATUS in (STATUS_CONNECTING,):
                    if threaded: 
                        gtk.gdk.threads_enter()                
                    self.notify("Initializating sharing", "Preparing server connection and data transfer.")
                    if threaded: 
                        gtk.gdk.threads_leave()    
            
            else:
            
                if STATUS in (STATUS_DISCONNECTED,) and OLDERSTATUS in (STATUS_WAITING, STATUS_ERROR, STATUS_STOPPED, STATUS_CONNECTING, STATUS_RUNNING, STATUS_USERINPUT):
                    if threaded: 
                        gtk.gdk.threads_enter()                
                    self.notify("No meeting connection", "Please connect to a meeting by pressing 'share' inside the 'Screen sharing' panel.")
                    if threaded: 
                            gtk.gdk.threads_leave()   
            
            # Remember old status.
            self.OLDERSTATUS = OLDSTATUS
            self.OLDSTATUS = STATUS
            
        return True

    def work(self):
        """
        Called periodically.
        """

        #print "work"

        #print "STATUS", self.STATUS

        connection = None
        
        # Get local variables for this run.
        window = self.window
        conference = self.conference
        x11vnc = self.x11vnc
        vnc2spreed = self.vnc2spreed
        remoteconnection = self.remoteconnection
        passwordfile = self.passwordfile

        # Check conference connection.
        if conference is not None:
            self.set_status(STATUS_WAITING, nodecrease=True)
        else:
            # Disconnect.
            self.stop_all()
            self.set_status(STATUS_DISCONNECTED)

        # Check remoteconnection.
        if remoteconnection is not None:
            
            if vnc2spreed is None:
            
                # Password support.
                self.passwordfile = None # Cleanup existing.
                try:
                    pw = self.getconfiguration("general", "remotepassword")
                except IndexError:
                    pw = None

                if pw is not None:
                    self.passwordfile = makepasswordfile(pw, encoded=True)
            
                # Try to connect once.
                connection = remoteconnection
                self.remoteconnection = None

        # Check window setting and launch x11vnc when available.
        elif window is not None:
            windowid, windowname, windowstarted = window
            if not windowstarted:
            
                # Get local port from configuration.
                localport = None
                try:
                    localauto = self.getconfiguration("general", "localauto")
                    if not localauto:
                        localport = self.getconfiguration("general", "localport")
                except IndexError:
                    pass

                # Password support.
                self.passwordfile = None # Cleanup existing.
                self.passwordfile = makepasswordfile() # Create new random pw.
                    
                # Launch x11vnc.
                try:
                    self.x11vnc = getx11vncserver(windowid, localport=localport, passwordfile=self.passwordfile)
                    LOG("started x11vnc %s" % repr(self.x11vnc), 5)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    ERROR("error while starting x11vnc", -1)
    
                # Remember start.
                self.window = (windowid, windowname, True)

        # Check x11vnc.
        if x11vnc is not None:
            pid, flagfile, logfile = x11vnc
            x11vncinuse = self.x11vncinuse
            
            try:
                res = os.waitpid(pid, os.WNOHANG)
            except OSError:
                ERROR("x11vnc no child process", -5)
                res = (None, None)
            if res != (0, 0):
                # x11vnc quit.
                self.x11vnc = x11vnc = None
                self.x11vncinuse = x11vncinuse = False
                self.window = None
                LOG("x11vnc exit with status %s" % repr(res[1]), 5)
                
                #if self.STATUS in (STATUS_RUNNING, STATUS_CONNECTING):
                #    gtk.gdk.threads_enter()
                #    self.notify("Error", "Sharing terminated unexpectedly. %s [1]." % repr(res), timeout=5000, stock_icon=gtk.STOCK_DIALOG_ERROR)
                #    gtk.gdk.threads_leave()
                
                self.stop_all()

                # Write last 5 lines of log into our log.
                if logfile is not None:
                    try:
                        # Read logfile.
                        if os.path.exists(logfile):
                            fp = file(logfile, "rb")
                            c = fp.readlines()
                            fp.close()
                            x11vnclog = ", ".join([x.strip() for x in c[-5:]])
                            LOG("x11vnc protocol: <snip>%s</snip>" % x11vnclog, 5)
                    except (IOError, OSError):
                        pass
                
                # Cleanup state.
                connection = None
                self.set_status(STATUS_WAITING)
            
            # Running x11vnc found.
            if not x11vncinuse and x11vnc is not None and vnc2spreed is None:
            
                if flagfile is not None:
                    # Read / wait flag file.
                    if os.path.exists(flagfile):
                        LOG("x11vnc flagfile %s appeared" % flagfile, 5)
                        fp = file(flagfile, "rb")
                        c = fp.read().strip()
                        fp.close()
                        
                        if c.startswith('PORT='):
                            # Make connection with x11vnc
                            connection = "localhost:%s" % c[5:]
                            
                elif logfile is not None:
                    # Read / wait for logfile.
                    if os.path.exists(logfile):
                        #LOG("Parsing x11vnc logfile %s" % logfile, 5)
                        fp = file(logfile, "rb")
                        c = fp.readlines()
                        fp.close()
                        
                        for l in c:
                            l = l.strip().lower()
                            if l.find("The VNC desktop is".lower()) != -1:
                                idx = l.find("localhost:")
                                l = l[idx:]
                                port = int(l.split(":",1)[-1])+5900
                                LOG("Parsed x11vnc port %s from logfile %s" % (port, logfile), 5)
                                connection = "localhost:%s" % port

                if connection:
                    self.x11vncinuse = True

        # Check vnc2spreed.
        if vnc2spreed is not None:
            pid, flagfile, currentconn = vnc2spreed
            vnc2spreedinuse = self.vnc2spreedinuse
            
            if pid is not None:
                try:
                    res = os.waitpid(pid, os.WNOHANG)
                except OSError:
                    ERROR("vnc2spreed no child process", -5)
                    res = (None, None)
                if res != (0, 0):
                    # vnc2spreed quit.
                    self.vnc2spreed = vnc2spreed = None
                    self.vnc2spreedinuse = vnc2spreedinuse = False
                    self.passwordfile = None
                    LOG("vnc2spreed exit with status %s" % repr(res[1]), 5)
                    
                    if self.STATUS in (STATUS_CONNECTING,):
                        gtk.gdk.threads_enter()                
                        self.notify("Error", "Sharing failed to initialize. %s [2]." % repr(res), timeout=5000, stock_icon=gtk.STOCK_DIALOG_ERROR)
                        gtk.gdk.threads_leave()    
                    
                    self.stop_all()
                    
                    # Uhm connection broke.
                    # Do not reconnect for now.
                    connection = None
                    self.set_status(STATUS_WAITING)
                    
                if not vnc2spreedinuse and vnc2spreed is not None:
                    if flagfile:
                        # Read / wait flag file.
                        if os.path.exists(flagfile):
                            self.vnc2spreedinuse = True
                            LOG("vnc2spreed flagfile %s appeared" % flagfile, 5)
                            # This means that vnc2spreed sent first frame.
                            self.set_status(STATUS_RUNNING)
                            
                            try:
                                self.vnc2spreed = (self.vnc2spreed[0], None, self.vnc2spreed[2])
                            except TypeError:
                                # Changed in the meantime.
                                ERROR("Error while resetting vnc2spreed flagfile status", -2)
                                pass
                    
        # Maybe start new one?
        if connection:
            
            # Check if we have to use https proxy.
            https_proxy = None
            if not self.getconfiguration("connection", "direct", default=False):
                LOG("Proxy configuration detected.", 10)
                proxyaddr = self.getconfiguration("connection", "proxyaddr", default=None)
                proxyusername = self.getconfiguration("connection", "proxyusername", default=None)
                proxypassword = self.getconfiguration("connection", "proxypassword", decrypt=True, default="")

                up = []
                if proxyusername: up.append(proxyusername)
                if proxypassword: 
                    # Decrypt.
                    
                    up.append(proxypassword)
                up = ":".join(up)
                
                if proxyaddr:
                    LOG("Using proxy at %s" % proxyaddr, 10)
                    if up:
                        LOG("Using proxy authentication", 10)
                        proxyaddr = "%s@%s" % (up, proxyaddr)

                # Set var.                    
                https_proxy = "https://%s" % proxyaddr
        
            LOG("New connection, beginning to stream.", 5)
            pid, flagfile = connectvnc2spreed(connection, self.conference, self.passwordfile, https_proxy)
            if pid is not None:
                self.vnc2spreed = (pid, flagfile, connection)
                LOG("started vnc2spreed %s" % repr(self.vnc2spreed), 5)
                self.set_status(STATUS_CONNECTING)
            else:
                # Conference data changed / removed?
                LOG("vnc2spreed did not return a valid pid", -1)
            
        return True
        
class LSOParser:
    """
    Simple parser for flash cookies (local shared objects *.sol).
    """

    TYPES_MAP = {
        '\x00' : 'NUMBER',  # implemented
        '\x01' : 'BOOLEAN', # implemented
        '\x02' : 'STRING',  # implemented
        '\x03' : 'OBJOBJ',
        '\x05' : 'NULL',
        '\x06' : 'UNDEF',
        '\x08' : 'OBJARR',
        '\x0A' : 'RAWARR',
        '\x0B' : 'OBJDATE',
        '\x0D' : 'OBJM',
        '\x0F' : 'OBJXML',
        '\x10' : 'OBJCC',
    }

    length = None
    header = None
    ft = None
    name = None

    data = None

    def __init__(self):
        self.data = {}

    def getData(self):
        """
        Returns a copy of the data.
        """
        return self.data.copy()
        
    def parse(self, fp):
    
        # Reset.
        self.data = {}
    
        # Get length.
        fp.seek(0,2)
        self.length = fp.tell()
        fp.seek(0)
        
        # Read header.
        self.header = fp.read(2)
        datalength = unpack(">L", fp.read(4))[0] # unsigned long, be
        assert self.length == datalength+6, "invalid file size"
        self.ft = fp.read(4)
        assert self.ft == 'TCSO', "invalid file type %s" % repr(ft)
        fp.read(6) # XXX no idea what this is
        namelength = unpack(">H", fp.read(2))[0] # unsigned short, be
        self.name = fp.read(namelength)
        fp.read(4) # XXX no idea what this is
        
        # Read loop.
        while fp.tell() < self.length:
            # Length for name.
            ln = unpack(">H", fp.read(2))[0] # unsigned short, be
            # Name.
            n = fp.read(ln)
            # Type.
            t = fp.read(1)
    
            # Get value.
            v = self.parse_value(fp, t)
            
            # Set to data dict.
            self.data[n] = v
            
            # Read end byte.
            end = fp.read(1)
            assert end == '\x00', "invalid end byte"

    def parse_value(self, fp, t):
        """
        Parse single value.
        """

        # Find parse function for type.
        try:
            f = getattr(self, 'parse_%s' % self.TYPES_MAP.get(t, 'UNSUPPORTED'))
        except AttributeError:
            raise NotImplementedError, "unsupported data type %s in lso" % repr(self.TYPES_MAP.get(t, t))
        return f(fp)

    def parse_NUMBER(self, fp):
        """
        number: 8 bytes double be.
        """
        data = unpack(">d", fp.read(8)) # double, be
        return data
        
    def parse_BOOLEAN(self, fp):
        """
        boolean: 1 byte.
        """
        data = fp.read(1)
        if data == '\x00':
            return False
        elif data == '\x01':
            return True
        else:
            raise RuntimeError, "invalid boolean data (%s)" % repr(data)
            
    def parse_STRING(self, fp):
        """
        string: 2 bytes length unsigned short, be followed by data.
        """
        l = unpack(">H", fp.read(2))[0] # unsigned short, be
        data = fp.read(l)
        return data
        
if __name__ == '__main__':

    LOG("spreedX started (r%s)" % __version__, 0)

    # Check for python gtk.
    if NOPYGTK:
        msg = "Missing python gtk or python glade."
        print >>sys.stderr, msg
        LOG(msg, -1)
        try:
            startuperrordialog("PYGTK problem", msg)
        except KeyboardInterrupt:
            raise
        except Exception:
            # This probably fails as well.
            pass
        sys.exit(1)

    # Check for python-xml.
    if NOPYXML:
        msg = "Missing python-xml."
        print >>sys.stderr, msg
        LOG(msg, -1)
        startuperrordialog("Missing dependency", msg)
        sys.exit(2)

    # Check for tray icon.
    if not GTKTRAY and not EGGTRAY:
        msg = "Missing tray icon implementation. You need either gtk >= 2.10 or gnome-python-extras."
        print >>sys.stderr, msg        
        LOG(msg, -1)
        startuperrordialog("Missing dependency", msg)
        sys.exit(3)

    LOG("Using %s as tray icon implementation" % BaseTrayIcon, 10)    

    if INOTIFY_WM:
        LOG("python-pyinotify found and initiatized (inotify bindings)", 10)
        
    if PYNOTIFY:
        LOG("python-notify found (libnotify bindings)", 10)

    # Check tools first.
    errors = check4tools([])

    if errors:
        msg = "Missing dependencies: %s." % (','.join([x[0] for x in errors]))
        print >>sys.stderr, msg        
        LOG(msg, -1)
        startuperrordialog("Missing system tools", msg)
        sys.exit(4)

    # Create configuration directory.
    if not os.path.isdir(SPREEDXBASE):
        LOG("Creating missing configuration directory %s" % SPREEDXBASE, 10)
        os.mkdir(SPREEDXBASE)

    conf = os.path.join(SPREEDXBASE, 'spreedx.xml')
    # Create configuration file if not there.
    if not os.path.isfile(conf):
        LOG("Creating missing configuration file %s" % conf, 10)
        fp = file(conf, "wb")
        fp.write(DEFAULTCONFIGURATION)
        fp.close()

    # Create main app.
    app = SpreedApp(conf=conf)
    try:
        app.main()
    except KeyboardInterrupt:
        app.on_exit_cleanup()

    LOG("spreedX exit", 0)
        
    sys.exit(0)

