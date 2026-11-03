#! /usr/bin/env python
# Alters the left and right sidebearings of a glyph

from __future__ import print_function, division, absolute_import
from fontTools.ttLib import TTFont

if len(sys.argv) != 5:
  print("usage: alter-sidebearings.py in.ttf out.ttf glyphname newLSB newRSB")
  sys.exit(1)

font = TTFont(sys.argv[1])
outfile = sys.argv[2]
glyphname = sys.argv[3]
newLSB = sys.argv[4]
newRSB = sys.argv[5]

assert "glyf" in font # OTF only for now.

oldWidth, oldLSB = font["hmtx"].metrics[glyphname]
oldRSB = oldWidth - max([f[0] for f in font["glyf"][glyphname].coordinates])
inkWidth = oldWidth - (oldLSB+oldRSB)
font["hmtx"].metrics[glyphname] = (newLSB+inkWidth+newRSB, newLSB)
font["glyf"][glyphname].coordinates -= (oldLSB-newLSB,0)

font.save(outfile)