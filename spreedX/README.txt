=========================================
spreedX screen sharing client
=========================================

spreedX is the screen sharing client for spreed services. It enables you to
share a single window or the complete screen to remote participants of a 
spreed online web meeting.


Quick start
--------------------

- First of all extract the spreedX archive somewhere where you 
  have execute permissions. Eg. into your home directory. 
      
- Make sure you have the required dependencies installed.
   
 These are:
      
 - /usr/bin/xwininfo
 - python >= 2.4, 
 - python-xml, 
 - python-gtk >= 2.8, 
 - x11vnc,
 - python-gnome-extras (only required for gtk 2.8)
        
- Start the spreedX application by typing ./spreedX inside the 
  installation folder.
      
- The spreed icon appears inside your system tray and indicates
  that the application is ready.
      
- Join a spreed online web meeting as moderator and select 
  screen sharing.
      
- Press the "share" button to connect to the local spreedX application.

- The spreed icon in your system tray is now green and a pop up window
  will appear. 
      
- Follow the instructions inside the pop up window and start to share
  either the complete screen or a single window.
      
- As soon as screen sharing is activated, the spreed tray icon has a red
  border and is flashing (if supported).
      
- To stop screen sharing, either leave the spreed web meeting or press
  the Stop entry in the tray icon context menu.
  

Installation
------------------

Extract the spreedX tarball into your home folder. If you are root and
want to install it system wide, extract it into /opt.

spreedX requires third party software being installed on your local system.
All these dependencies can be resolved using package management tools.

RHEL 5
~~~~~~~~~

As RHEL does not contain x11vnc in the standard repository you have to
add the DAG/DRIESS yum repository.

http://dag.wieers.com/rpm/

You can either add the yum repository or download the x11vnc RPM directly.

Novell SLE 10
~~~~~~~~~~~~~~~~~~~

Install the following packages (including all dependencies) using Yast.

- python-gnome-extras
- python-xml
- LibVNCServer

Ubuntu 8.04
~~~~~~~~~~~~~~~~

Install the following packages using apt.

- x11vnc
- python-gtk2

Debian 4
~~~~~~~~~~~~

Install the following packages using apt.

- x11vnc
- python-gtk2
- python-gnome2-extras

Fedora 8
~~~~~~~~~~~~

As Fedora does not contain x11vnc in the standard repository you have to
add the DAG/DRIESS yum repository.

http://dag.wieers.com/rpm/

You can either add the yum repository or download x11vnc RPM directly.  

Also you need to install xwininfo as its no longer standard.
"yum install xwininfo" will do the job.

openSUSE 10.2 
~~~~~~~~~~~~~~~~~~

Install the following packages (including all dependencies) using Yast.

- python-gnome-extras
- python-xml
- LibVNCServer
    
Other distributions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have another or older release, you might still have the dependencies
available using your package manager. Usually it should be no problem if
your distribution release is rather uptodate.

You need the following software (and its dependencies).

 - /usr/bin/xwininfo
 - python >= 2.4
 - python-gtk >= 2.8
 - python-gnome-extras (only when python-gtk < 2.10)
 - x11vnc >= 0.7


Usage
-----------

To use the screen sharing feature of a spreed web meeting, you have to start
the spreedX client on your local machine (this is the machine with the screen
you want to share).

To start the spreedX application, open a terminal, change the directory to
the installation folder (cd) and type "./spreedX". 

You can also start the application from your file manager (eg. Nautilus or 
Konqueror) by double click on "spreedX" (inside the installation folder).

The application will refuse to start, if you are missing one of the depen-
dencies. See Installation section of this document for details.

If the application started, a spreed icon will appear inside the system 
tray area.

Now you have to establish a conference connection, by joining a spreed 
web meeting on the same machine with your web browser. Inside the conference
select screen sharing and press the share button, to establish a connection
to the scree sharing application.

If the connection is active, the spreed icon inside your system tray is 
enabled (green).

You can now start screen sharing by selecting start from the spreed icon
context menu or from the pop up window which appears as soon as the spreedX
application detected a conference connection.

When screen sharing is enabled, the spreed tray icon is flashing (when
supported by your system) and has a red border.


Proxy support
------------------

spreedX uses HTTPS connections to communicate with the spreed server. Thus
if your Internet connection does require a proxy for HTTPS you have to enter
the proxy details into the preferences screen. To view preferences, please
select "Preferences" from the context menu of the spreed icon in your system
tray.

You can enter proxy details inside the "Connection" tab. If your proxy
does require authentication, please enter your credentials as well. **NOTE: 
only basic authentication is supported.**


Example:

::
 
 Address  : proxy.mydomain.com:3128
 Username : jane.doe@nowhere.com
 Password : ****


Sharing remote VNC server
----------------------------------

spreed can also share any given VNC server. This makes it possible to 
connect spreedX to your built-in desktop sharing server (eg. vino for Gnome) 
or even to remote VNC servers.
    
You can configure this feature in the preferences window.
    
Example:
(This shares the local Gnome vino server).
 
::   
 
 Remote VNC server settings
   Address  : localhost:5900
   Password :
    
Leave the password empty if your server does not require a password.
    

More information or help
----------------------------------

Please visit http://spreed.com for more information and support.


    
-- (c)2007 struktur AG - mailto: info@spreed.com


    
    

