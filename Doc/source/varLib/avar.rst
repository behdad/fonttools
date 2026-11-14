#####################
avar: Axis mappings
#####################

``fonttools varLib.avar.map`` maps variation coordinates through avar version
1 or 2. ``fonttools varLib.avar.reverse`` inverts it, finding pre-fvar
coordinates for a post-avar target::

    fonttools varLib.avar.reverse -i Font.ttf wght=0.6 wdth=-0.2

``-i`` selects normalized targets; by default the result uses pre-fvar units.
Add ``-o`` for normalized input coordinates in the result. An omitted target
axis means normalized zero while its input is free; a pinned or hidden axis is
left unconstrained, since its input cannot move. Hidden *input* axes are
always held at their fvar defaults. To fix another input axis, use ``--pin``
with a pre-fvar value (independent of ``-i`` and ``-o``)::

    fonttools varLib.avar.reverse -i --pin opsz=14 Font.ttf wght=0.6

Omit the value to pin an axis at its fvar default. Repeat ``--pin`` or
comma-separate to fix more axes::

    fonttools varLib.avar.reverse -i --pin opsz,wdth=100 Font.ttf wght=0.6

By default every non-hidden axis may vary. To restrict the result to a chosen
set of input axes, use ``--vary`` (comma-separated or repeated); every other
axis is pinned to its fvar default, overriding hidden flags::

    fonttools varLib.avar.reverse -i --vary wght,wdth,opsz Font.ttf wght=0.6 wdth=-0.2

``--roundtrip`` instead treats the coordinates as a pre-fvar source: it
forward-maps them through avar and then reverses the result, which is handy for
checking how well a design location survives the round trip (``-i`` then
applies to the source)::

    fonttools varLib.avar.reverse --roundtrip -o Font.ttf wght=700 wdth=125

Reverse mapping requires the optional ``fonttools[avar]`` dependencies.
It minimizes normalized output error, then prefers fewer non-default input
axes among solutions within one F2Dot14 unit of the best error found. A greedy
search seeks sparse solutions; neither global optimality nor the minimum
possible number of axes is guaranteed. Unreachable targets return an
approximation; ``--show-error`` prints the residual, and the Python API returns
it as the ``error`` alongside the location. CLI output is rounded to the font's
F2Dot14 resolution for readability. The font is not modified.

.. automodule:: fontTools.varLib.avar.reverse
   :members: reverse
