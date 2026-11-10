##################################
ttx: Convert fonts to XML and back
##################################


TTX – From OpenType and TrueType to XML and Back
------------------------------------------------

Once installed you can use the ttx command to convert binary font files (.otf, .ttf, etc) to the TTX XML format, edit them, and convert them back to binary format. TTX files have a .ttx file extension::

    ttx /path/to/font.otf
    ttx /path/to/font.ttx

The TTX application can be used in two ways, depending on what platform you run it on:

* As a command line tool (Windows/DOS, Unix, macOS)
* By dropping files onto the application (Windows, macOS)

TTX detects what kind of files it is fed: it will output a ``.ttx`` file when it sees a ``.ttf`` or ``.otf``, and it will compile a ``.ttf`` or ``.otf`` when the input file is a ``.ttx`` file. By default, the output file is created in the same folder as the input file, and will have the same name as the input file but with a different extension. TTX will never overwrite existing files, but if necessary will append a unique number to the output filename (before the extension) such as ``Arial#1.ttf``.

When using TTX from the command line there are a bunch of extra options. These are explained in the help text, as displayed when typing ``ttx -h`` at the command prompt. These additional options include:


* specifying the folder where the output files are created
* specifying which tables to dump or which tables to exclude
* merging partial .ttx files with existing .ttf or .otf files
* listing brief table info instead of dumping to .ttx
* splitting tables to separate .ttx files
* disabling TrueType instruction disassembly

The TTX file format
^^^^^^^^^^^^^^^^^^^

.. begin table list

The following tables are currently supported::

    BASE, CBDT, CBLC, CFF, CFF2, COLR, CPAL, DMAP, DSIG, Debg, EBDT,
    EBLC, EBSC, FFTM, Feat, GDEF, GLYF, GPOS, GSUB, GVAR, Glat, Gloc,
    HHEA, HMTX, HVAR, IFT, IFTX, JSTF, LOCA, LTSH, MATH, MAXP, MVAR,
    OS/2, STAT, SVG, Silf, Sill, TSI0, TSI1, TSI2, TSI3, TSI5, TSIB,
    TSIC, TSID, TSIJ, TSIP, TSIS, TSIV, TTFA, VARC, VDMX, VHEA, VMTX,
    VORG, VVAR, ankr, avar, bdat, bgcl, bhed, bloc, bsln, cidg, cmap,
    cvar, cvt, feat, fpgm, fvar, gasp, gcid, glyf, gvar, hdmx, head,
    hhea, hmtx, kern, lcar, loca, ltag, maxp, meta, mort, morx, name,
    opbd, post, prep, prop, sbix, trak, vhea and vmtx

.. end table list

Other tables are dumped as hexadecimal data.

TrueType fonts use glyph indices (GlyphIDs) to refer to glyphs in most places. While this is fine in binary form, it is really hard to work with for humans. Therefore we use names instead.

The glyph names are either extracted from the ``CFF`` table or the ``post`` table, or are derived from a Unicode ``cmap`` table. In the latter case the Adobe Glyph List is used to calculate names based on Unicode values. If all of these methods fail, names are invented based on GlyphID (eg ``glyph00142``)

It is possible that different glyphs use the same name. If this happens, we force the names to be unique by appending #n to the name (n being an integer number.) The original names are being kept, so this has no influence on a "round tripped" font.

Because the order in which glyphs are stored inside the binary font is important, we maintain an ordered list of glyph names in the font.

In ``STAT`` XML, ``AxisIndex`` values include axis-name comments when the
corresponding ``name`` records are available. These indices refer to ``STAT``'s
design-axis records, not to ``fvar``'s axis order. The comments do not change the
binary data.

.. automodule:: fontTools.ttx
   :members:
   :undoc-members:
