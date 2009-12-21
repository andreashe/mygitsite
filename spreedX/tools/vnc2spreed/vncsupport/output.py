#!/usr/bin/env python
##
##  pyvnc2swf - output.py
##
##  $Id: output.py,v 1.1 2007/03/31 04:02:15 euske Exp $
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

import sys, zlib
from image import *
stderr = sys.stderr
lowerbound = max
upperbound = min



##  MovieOutputStream
##
class MovieOutputStream:

  """
  MovieOutputStream is an abstract class which produces
  some external representation of a movie (either to a file or to a display).
  This is used for generating SWF files or playing movies on the screen.
  """
  
  def __init__(self, info, debug=0):
    self.debug = debug
    self.info = info
    self.output_frames = 0
    self.cursor_image = None
    self.cursor_offset = None
    self.cursor_pos = None
    return

  def open(self):
    return
  
  def set_keyframe(self):
    return
  
  def paint_frame(self, (images, othertags, cursor_info)):
    if cursor_info:
      (cursor_image, cursor_pos) = cursor_info
      self.cursor_image = cursor_image or self.cursor_image
      self.cursor_pos = cursor_pos or self.cursor_pos
    return

  def change_size(self):
    return

  def next_frame(self):
    self.output_frames += 1
    return
  
  def close(self):
    if self.debug:
      print >>stderr, 'stream: close'
    return

  def write_mp3frames(self, frameid=None):
    return
  
  def preserve_frame(self):
    return None
  
  def recover_frame(self, img):
    raise NotImplementedError


##  FLVVideoStream
##  Contributed by Luis Fernando <lfkpoa-69@yahoo.com.br>
##
class FLVVideoStream(MovieOutputStream):

  """
  FLVVideoStream produces a FLV file with a video object.
  """
  
  flv_version = 1                       # FLV 1

  def __init__(self, info, debug=0):
    assert info.filename, 'Filename not specified!'
    MovieOutputStream.__init__(self, info, debug)
    return
  
  def open(self):
    MovieOutputStream.open(self)
    self.writer = FLVWriter(self.info.filename, self.flv_version,
                            (0,self.info.width*20, 0,self.info.height*20),
                            self.info.framerate)
    self.othertags = []
    (x,y,w,h) = self.info.clipping
    self.screen = SWFVideoScreen(x, y, w, h, self.info.blocksize, self.info.blocksize,
                                 scaling=self.info.scaling)
    self.set_keyframe()
    self.painted = False
    return

  def paint_frame(self, (images, othertags, cursor_info)):
    MovieOutputStream.paint_frame(self, (images, othertags, cursor_info))
    self.othertags.extend(othertags)
    for ((x0,y0), (w,h,data)) in images:
      if self.debug:
        print >>stderr, 'paint:', (x0,y0), (w,h)
      if self.screen.paint_image(x0, y0, w, h, data):
        self.painted = True
    if cursor_info:
      (cursor_image, cursor_pos) = cursor_info
      if cursor_image:
        (w, h, dx, dy, data) = cursor_image
        self.cursor_offset = (dx, dy)
        self.cursor_image = create_image_from_string_argb(w, h, data)
        self.painted = True
      if cursor_pos:
        self.cursor_pos = cursor_pos
        self.painted = True
    return

  def next_frame(self):
    if self.is_keyframe or self.painted:
      r = []
      changed = self.is_keyframe
      self.screen.prepare_image(self.cursor_image, self.cursor_offset, self.cursor_pos)
      for y in xrange(self.screen.vblocks):
        for x in xrange(self.screen.hblocks):
          data = self.screen.get_block_change(x, y)
          r.append(data)
          if data:
            changed = True
      if changed:
        # write FLV tag
        self.writer.start_tag()
        # SCREENVIDEOPACKET
        if self.is_keyframe:
          self.writer.writebits(4, 1)
          self.is_keyframe = False
        else:
          self.writer.writebits(4, 2)
        self.writer.writebits(4, 3) # screenvideo codec
        self.writer.writebits(4, self.screen.block_w/16-1)
        self.writer.writebits(12, self.screen.out_width)
        self.writer.writebits(4, self.screen.block_h/16-1)
        self.writer.writebits(12, self.screen.out_height)
        self.writer.finishbits()
        for blocks in r:
          if blocks:
            data = zlib.compress(''.join(blocks))
            self.writer.writeub16(len(data))
            self.writer.write(data)
          else:
            self.writer.writeub16(0)
        t = (self.output_frames*1000+1) / self.info.framerate
        self.writer.end_tag(9, t)
    MovieOutputStream.next_frame(self)
    return

  def set_keyframe(self):
    self.screen.init_blocks()
    self.is_keyframe = True
    return

  def close(self):
    assert not self.writer.fpstack
    MovieOutputStream.close(self)
    self.writer.write_file(self.output_frames)
    return
