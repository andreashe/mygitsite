#!/usr/bin/env python
##
##  pyvnc2swf - image.py
##
##  $Id: image.py,v 1.1 2007/03/31 04:02:15 euske Exp $
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

#  format: 1: solid,
#          2: raw (uncompressed)
#          3: DefineBitLossless
#          4: SCREENVIDEOPACKET
IMG_SOLID = 1
IMG_RAW = 2
IMG_LOSSLESS = 3
IMG_VIDEOPACKET = 4
