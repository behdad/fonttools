#######################################
varLib: Support for OpenType Variations
#######################################

.. contents:: On this page:
    :local:
       
.. rubric:: Overview
   :heading-level: 2

The :py:mod:`fontTools.varLib` package contains a number of classes and routines
for handling, building and interpolating variable font data. These routines
rely on a common set of concepts, many of which are equivalent to concepts
in the OpenType Specification, but some of which are unique to :py:mod:`varLib`.


Supporting modules
------------------

.. toctree::
   :maxdepth: 1

   avar
   builder
   cff
   errors
   featureVars
   instancer
   interpolatable
   interpolate_layout
   iup
   merger
   models
   mutator
   mvar
   plot
   varStore


Terminology
-----------

axis
   "A designer-determined variable in a font face design that can be used to
   derive multiple, variant designs within a family." (OpenType Specification)
   An axis has a minimum value, a maximum value and a default value.

designspace
   The n-dimensional space formed by the font's axes. (OpenType Specification
   calls this the "design-variation space")

scalar
   A value which is able to be varied at different points in the designspace:
   for example, the horizontal advance width of the glyph "a" is a scalar.
   However, see also *support scalar* below.

default location
   A point in the designspace whose coordinates are the default value of
   all axes.

location
   A point in the designspace, specified as a set of coordinates on one or
   more axes. In the context of ``varLib``, a location is a dictionary with
   the keys being the axis tags and the values being the coordinates on the
   respective axis. A ``varLib`` location dictionary may be "sparse", in the
   sense that axes defined in the font may be omitted from the location's
   coordinates, in which case the default value of the axis is assumed.
   For example, given a font having a ``wght`` axis ranging from 200-1000
   with default 400, and a ``wdth`` axis ranging 100-300 with default 150,
   the location ``{"wdth": 200}`` represents the point ``wght=400,wdth=200``.

master
   The value of a scalar at a given location. **Note that this is a
   considerably more general concept than the usual type design sense of
   the term "master".**

normalized location
   While the range of an axis is determined by its minimum and maximum values
   as set by the designer, locations are specified internally to the font binary
   in the range -1 to 1, with 0 being the default, -1 being the minimum and
   1 being the maximum. A normalized location is one which is scaled to the
   range (-1,1) on all of its axes. Note that as the range from minimum to
   default and from default to maximum on a given axis may differ (for
   example, given ``wght min=200 default=500 max=1000``, the difference
   between a normalized location -1 of a normalized location of 0 represents a
   difference of 300 units while the difference between a normalized location
   of 0 and a normalized location of 1 represents a difference of 700 units),
   a location is scaled by a different factor depending on whether it is above
   or below the axis' default value.

support
   While designers tend to think in terms of masters - that is, a precise
   location having a particular value - OpenType Variations specifies the
   variation of scalars in terms of deltas which are themselves composed of
   the combined contributions of a set of triangular regions, each having
   a contribution value of 0 at its minimum value, rising linearly to its
   full contribution at the *peak* and falling linearly to zero from the
   peak to the maximum value. The OpenType Specification calls these "regions",
   while ``varLib`` calls them "supports" (a mathematical term used in real
   analysis) and expresses them as a dictionary mapping each axis tag to a
   tuple ``(min, peak, max)``.

box
   ``varLib`` uses the term "box" to denote the minimum and maximum "corners" of
   a support, ignoring its peak value.

delta
   The term "delta" is used in OpenType Variations in two senses. In the
   more general sense, a delta is the difference between a scalar at a
   given location and its value at the default location. Additionally, inside
   the font, variation data is stored as a mapping between supports and deltas.
   The delta (in the first sense) is computed by summing the product of the
   delta of each support by a factor representing the support's contribution
   at this location (see "support scalar" below).

support scalar
   When interpolating a set of variation data, the support scalar represents
   the scalar multiplier of the support's contribution at this location. For
   example, the support scalar will be 1 at the support's peak location, and
   0 below its minimum or above its maximum.


Package contents
----------------

.. automodule:: fontTools.varLib
   :members:
   :undoc-members:
