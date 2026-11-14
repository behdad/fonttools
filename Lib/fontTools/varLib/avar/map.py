from fontTools.varLib.models import normalizeValue


def _denormalize(v, triplet):
    if v >= 0:
        return triplet[1] + v * (triplet[2] - triplet[1])
    else:
        return triplet[1] + v * (triplet[1] - triplet[0])


def _load_font(parser, fontpath):
    """Load a variable font, or build one from a designspace, for a CLI."""
    from fontTools.ttLib import TTFont

    if fontpath.endswith(".designspace"):
        from .build import build

        font = TTFont()
        build(font, fontpath)
        return font
    font = TTFont(fontpath)
    if "fvar" not in font:
        parser.error(f"Font '{fontpath}' does not contain an 'fvar' table.")
    return font


def _parse_coordinates(parser, items, allow_default=False):
    """Parse ``AXIS=value`` CLI items into a location dict (shared by the CLIs).

    With ``allow_default``, a bare ``AXIS`` maps to ``None`` (the axis default).
    """
    location = {}
    for item in items:
        tag, sep, value = item.partition("=")
        if allow_default and tag and not sep:
            location[tag] = None
            continue
        if not sep or not tag or not value:
            parser.error(
                f"Invalid coordinate {item!r}. Expected AXIS=value, e.g. wght=500"
            )
        try:
            location[tag] = float(value)
        except ValueError:
            parser.error(
                f"Invalid coordinate value in {item!r}. Expected a number after '='"
            )
    return location


def map(
    font,
    location,
    *,
    inputNormalized=False,
    outputNormalized=False,
    dropZeroes=False,
    reverse=False,
    pinned=None,
    vary=None,
):
    """Map coordinates through avar, or approximately invert it.

    Omitted axes use their fvar defaults in user coordinates, or zero when
    inputNormalized is True. dropZeroes omits normalized-zero OUTPUT axes,
    independently of the input/output units and the avar version.

    With ``reverse=True``, return the ``(location, error)`` tuple from
    :func:`fontTools.varLib.avar.reverse.reverse`; otherwise return the mapped
    location. ``pinned`` and ``vary`` are only supported for reverse mapping.
    """
    if reverse:
        from .reverse import reverse as reverse_map

        return reverse_map(
            font,
            location,
            inputNormalized=inputNormalized,
            outputNormalized=outputNormalized,
            dropZeroes=dropZeroes,
            pinned=pinned,
            vary=vary,
        )
    if pinned is not None:
        raise ValueError("Axis pins require reverse mapping")
    if vary is not None:
        raise ValueError("Axis vary lists require reverse mapping")
    if "fvar" not in font:
        return None

    fvar = font["fvar"]
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes}
    unknownAxes = sorted(tag for tag in location if tag not in axes)
    if unknownAxes:
        raise ValueError(f"Unknown axis tag(s): {', '.join(unknownAxes)}")

    location = {
        tag: (
            location.get(tag, 0)
            if inputNormalized
            else normalizeValue(location.get(tag, triple[1]), triple)
        )
        for tag, triple in axes.items()
    }

    if "avar" in font:
        location = font["avar"].renormalizeLocation(location, font, dropZeroes)

    # Filter before denormalizing: a normalized zero can become a nonzero
    # user-space default. avar v1 and fonts without avar need this too.
    if dropZeroes:
        location = {tag: value for tag, value in location.items() if value != 0}

    if not outputNormalized:
        location = {
            tag: _denormalize(value, axes[tag]) for tag, value in location.items()
        }

    return location


def main(args=None):
    """Map variation coordinates through the `avar` table."""

    import argparse
    import sys

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        "fonttools varLib.avar.map",
        description="Map variation coordinates through the `avar` table. "
        "To invert the mapping, see `fonttools varLib.avar.reverse`.",
    )
    parser.add_argument("font", metavar="varfont.ttf", help="Variable-font file.")
    parser.add_argument(
        "coords",
        metavar="[AXIS=value...]",
        help="Coordinates to map, e.g. 'wght=700 wdth=75'. "
        "Omit coordinates to map the default location.",
        nargs="*",
        default=[],
    )
    parser.add_argument(
        "-f", action="store_true", help="Do not omit axes at default location."
    )
    parser.add_argument(
        "-i", action="store_true", help="Input coordinates are normalized (-1..1)."
    )
    parser.add_argument(
        "-o", action="store_true", help="Output coordinates as normalized (-1..1)."
    )

    options = parser.parse_args(args)

    font = _load_font(parser, options.font)
    location = _parse_coordinates(parser, options.coords)

    try:
        mapped = map(
            font,
            location,
            inputNormalized=options.i,
            outputNormalized=options.o,
            dropZeroes=not options.f,
        )
    except ValueError as e:
        parser.error(str(e))
    assert mapped is not None

    for tag in mapped:
        v = mapped[tag]
        v = int(v) if v == int(v) else v
        print(f"{tag}={v:g}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
