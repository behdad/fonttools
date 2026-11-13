#####################
avar: Axis mappings
#####################

``fonttools varLib.avar.map`` maps variation coordinates through avar version
1 or 2. Use ``--reverse`` to find pre-fvar coordinates for a post-avar target::

    fonttools varLib.avar.map --reverse -i Font.ttf wght=0.6 wdth=-0.2

``-i`` selects normalized targets; by default the result uses pre-fvar units.
Add ``-o`` for normalized input coordinates in the result. Omitted target axes
mean normalized zero, including hidden output axes. Hidden *input* axes are
always held at their fvar defaults. To fix another input axis, use ``--pin``
with a pre-fvar value (independent of ``-i`` and ``-o``)::

    fonttools varLib.avar.map --reverse -i --pin opsz=14 Font.ttf wght=0.6

Reverse mapping requires the optional ``fonttools[avar]`` dependencies.
It minimizes normalized output error, then prefers fewer non-default input
axes among solutions within one F2Dot14 unit of the best error found. A greedy
search seeks sparse solutions; neither global optimality nor the minimum
possible number of axes is guaranteed. Unreachable targets return an
approximation and log the residual. The font is not modified.

.. automodule:: fontTools.varLib.avar.reverse
   :members: reverse
