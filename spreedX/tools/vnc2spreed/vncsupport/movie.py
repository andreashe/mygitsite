#!/usr/bin/env python
##
##  pyvnc2swf - movie.py
##
##  $Id: movie.py,v 1.1 2007/03/31 04:02:15 euske Exp $
##
##  Copyright (C) 2005 by Yusuke Shinyama (yusuke at cs . nyu . edu)
##  All Rights Reserved.
##
##  This is free software; you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation; either version 2 of the License, or
##  (at your option) any later version.
##
##  This software is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License for more details.
##
##  You should have received a copy of the GNU General Public License
##  along with this software; if not, write to the Free Software
##  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307,
##  USA.
##

import sys, zlib, re
from rfb import RFBMovieConverter
from image import IMG_LOSSLESS, IMG_VIDEOPACKET
stderr = sys.stderr


##  SWFInfo
##
class SWFInfo:

  """
  SWFInfo holds information about headers and mp3 data
  in a SWF file. The values of this object are changed
  as parsing goes on.
  """
  
  def __init__(self, filename=None):
    self.filename = filename
    self.compression = None
    self.clipping = None
    self.framerate = None
    self.scaling = None
    self.blocksize = None
    self.swf_version = None
    self.width = None
    self.height = None
    self.mp3 = None
    self.scalable = False
    return

  def __repr__(self):
    return '<SWFInfo: filename=%r, compression=%r, clipping=%r, framerate=%r, scaling=%r, blocksize=%r, swf_version=%r, mp3=%r>' % \
           (self.filename, self.compression, self.clipping, self.framerate, self.scaling, self.blocksize, self.swf_version, self.mp3)

  def set_defaults(self, w0, h0): # size in pixels
    # THIS MUST BE CALLED BEFORE MovieOutputStream.open()
    if not self.clipping:
      self.clipping = (0,0,w0,h0)
    else:
      (w0,h0) = (self.clipping[2], self.clipping[3])
    if self.scaling:
      (w0,h0) = (int(w0*self.scaling), int(h0*self.scaling))
    if self.width != None and (self.width != w0 or self.height != h0):
      print >>stderr, 'Warning: movie size already set: %dx%d' % (self.width, self.height)
    elif self.width == None:
      (self.width, self.height) = (w0,h0)
      print >>stderr, 'Output movie size: %dx%d' % (self.width, self.height)
    if not self.framerate:
      self.framerate = 12.0
    if not self.blocksize:
      self.blocksize = 32
    return

  def set_scalable(self, scalable):
    self.scalable = scalable
    return

  def set_framerate(self, framerate):
    if self.framerate != None and self.framerate != framerate:
      print >>stderr, 'Warning: movie framerate is overridden.'
      return      
    self.framerate = float(framerate)
    return

  def set_size(self, width, height):
    self.width = width
    self.height = height
    self.clipping = (self.clipping[0], self.clipping[1], width, height)

  def get_size(self):
    return self.width, self.height

  def set_clipping(self, s):
    m = re.match(r'^(\d+)x(\d+)\+(\d+)\+(\d+)$', s)
    if not m:
      raise ValueError('Invalid clipping spec: %r' % s)
    f = map(int, m.groups())
    self.clipping = (f[2],f[3], f[0],f[1])
    return
    
  def get_clipping(self):
    if not self.clipping:
      raise ValueError('Clipping not set.')
    (x,y,w,h) = self.clipping
    return '%dx%d+%d+%d' % (w,h,x,y)

  def set_swf_version(self, swf_version):
    self.swf_version = swf_version
    return


  
