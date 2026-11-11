####################################
merge: Merge multiple fonts into one
####################################

.. rubric:: Overview:
   :heading-level: 2

:mod:`fontTools.merge` provides both a library and a command line interface
(``fonttools merge``) for merging multiple fonts together.

Run ``fonttools merge --help`` (or ``pyftmerge --help``) to list the command-line
options. ``-h`` is also supported. Help is written to standard output without
opening any font or input-list files.

If the merged BMP mapping exceeds the 16-bit limits of a ``cmap`` format 4
subtable, the merger uses format 12 instead. All nominal mappings and separate
Unicode variation mappings are retained. Such fonts require a reader that
supports format 12. BMP maps that fit in format 4 keep their representation.

.. autoclass:: fontTools.merge.Merger
   :members:
   :undoc-members:
