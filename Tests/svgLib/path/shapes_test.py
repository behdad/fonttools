from fontTools.svgLib.path import shapes
from fontTools.misc import etree
import pytest


@pytest.mark.parametrize(
    "svg_xml, expected_path, expected_transform",
    [
        # path: direct passthrough
        ("<path d='I love kittens'/>", "I love kittens", None),
        # path no @d
        ("<path duck='Mallard'/>", None, None),
        # line
        ('<line x1="10" x2="50" y1="110" y2="150"/>', "M10,110 L50,150", None),
        # line, decimal positioning
        (
            '<line x1="10.0" x2="50.5" y1="110.2" y2="150.7"/>',
            "M10,110.2 L50.5,150.7",
            None,
        ),
        # rect: minimal valid example
        ("<rect width='1' height='1'/>", "M0,0 H1 V1 H0 V0 z", None),
        # rect: sharp corners
        (
            "<rect x='10' y='11' width='17' height='11'/>",
            "M10,11 H27 V22 H10 V11 z",
            None,
        ),
        # rect: round corners
        (
            "<rect x='9' y='9' width='11' height='7' rx='2'/>",
            "M11,9 H18 A2,2 0 0 1 20,11 V14 A2,2 0 0 1 18,16 H11"
            " A2,2 0 0 1 9,14 V11 A2,2 0 0 1 11,9 z",
            None,
        ),
        # rect: simple
        (
            "<rect x='11.5' y='16' width='11' height='2'/>",
            "M11.5,16 H22.5 V18 H11.5 V16 z",
            None,
        ),
        # rect: the one above plus a rotation
        (
            "<rect x='11.5' y='16' transform='matrix(0.7071 -0.7071 0.7071 0.7071 -7.0416 16.9999)' width='11' height='2'/>",
            "M11.5,16 H22.5 V18 H11.5 V16 z",
            (0.7071, -0.7071, 0.7071, 0.7071, -7.0416, 16.9999),
        ),
        # polygon
        ("<polygon points='30,10 50,30 10,30'/>", "M30,10 50,30 10,30 z", None),
        # polyline
        ("<polyline points='30,10 50,30 10,30'/>", "M30,10 50,30 10,30", None),
        # circle, minimal valid example
        ("<circle r='1'/>", "M-1,0 A1,1 0 1 1 1,0 A1,1 0 1 1 -1,0", None),
        # circle
        (
            "<circle cx='600' cy='200' r='100'/>",
            "M500,200 A100,100 0 1 1 700,200 A100,100 0 1 1 500,200",
            None,
        ),
        # circle, decimal positioning
        (
            "<circle cx='12' cy='6.5' r='1.5'></circle>",
            "M10.5,6.5 A1.5,1.5 0 1 1 13.5,6.5 A1.5,1.5 0 1 1 10.5,6.5",
            None,
        ),
        # circle, with transform
        (
            '<circle transform="matrix(0.9871 -0.1602 0.1602 0.9871 -7.525 8.6516)" cx="49.9" cy="51" r="14.3"/>',
            "M35.6,51 A14.3,14.3 0 1 1 64.2,51 A14.3,14.3 0 1 1 35.6,51",
            (0.9871, -0.1602, 0.1602, 0.9871, -7.525, 8.6516),
        ),
        # ellipse
        (
            '<ellipse cx="100" cy="50" rx="100" ry="50"/>',
            "M0,50 A100,50 0 1 1 200,50 A100,50 0 1 1 0,50",
            None,
        ),
        # ellipse, decimal positioning
        (
            '<ellipse cx="100.5" cy="50" rx="10" ry="50.5"/>',
            "M90.5,50 A10,50.5 0 1 1 110.5,50 A10,50.5 0 1 1 90.5,50",
            None,
        ),
        # ellipse, with transform
        (
            '<ellipse transform="matrix(0.9557 -0.2945 0.2945 0.9557 -14.7694 20.1454)" cx="59.5" cy="59.1" rx="30.9" ry="11.9"/>',
            "M28.6,59.1 A30.9,11.9 0 1 1 90.4,59.1 A30.9,11.9 0 1 1 28.6,59.1",
            (0.9557, -0.2945, 0.2945, 0.9557, -14.7694, 20.1454),
        ),
        # translate, ty defaults to 0
        ("<path d='M0,0' transform='translate(5)'/>", "M0,0", (1, 0, 0, 1, 5, 0)),
        # translate, comma and space separated
        ("<path d='M0,0' transform='translate(5, 7)'/>", "M0,0", (1, 0, 0, 1, 5, 7)),
        # scale, sy defaults to sx
        ("<path d='M0,0' transform='scale(2)'/>", "M0,0", (2, 0, 0, 2, 0, 0)),
        # scale, padded with spaces
        ("<path d='M0,0' transform='scale( 2 , 3 )'/>", "M0,0", (2, 0, 0, 3, 0, 0)),
        # rotate, angle in degrees
        ("<path d='M0,0' transform='rotate(90)'/>", "M0,0", (0, 1, -1, 0, 0, 0)),
        # rotate about (10, 20): translate(10 20) rotate(90) translate(-10 -20)
        (
            "<path d='M0,0' transform='rotate(90 10 20)'/>",
            "M0,0",
            (0, 1, -1, 0, 30, 10),
        ),
        # skewX, tan(45deg) == 1
        (
            "<path d='M0,0' transform='skewX(45)'/>",
            "M0,0",
            pytest.approx((1, 0, 1, 1, 0, 0)),
        ),
        # skewY
        (
            "<path d='M0,0' transform='skewY(45)'/>",
            "M0,0",
            pytest.approx((1, 1, 0, 1, 0, 0)),
        ),
        # transform list: the rightmost transform is applied first
        (
            "<path d='M0,0' transform='translate(10,20) scale(2)'/>",
            "M0,0",
            (2, 0, 0, 2, 10, 20),
        ),
        (
            "<path d='M0,0' transform='scale(2) translate(10,20)'/>",
            "M0,0",
            (2, 0, 0, 2, 20, 40),
        ),
        # transform list, comma separated
        (
            "<path d='M0,0' transform='matrix(1, 0, 0, 1, 10, 20), rotate(90) scale(2)'/>",
            "M0,0",
            (0, 2, -2, 0, 10, 20),
        ),
        # transform list, no separator
        (
            "<path d='M0,0' transform='translate(5)scale(2)'/>",
            "M0,0",
            (2, 0, 0, 2, 5, 0),
        ),
        # transform list, padded with spaces
        ("<path d='M0,0' transform=' translate(5) '/>", "M0,0", (1, 0, 0, 1, 5, 0)),
        # empty transform list
        ("<path d='M0,0' transform=''/>", "M0,0", (1, 0, 0, 1, 0, 0)),
    ],
)
def test_el_to_path(svg_xml, expected_path, expected_transform):
    pb = shapes.PathBuilder()
    pb.add_path_from_element(etree.fromstring(svg_xml))
    if expected_path:
        expected_paths = [expected_path]
        expected_transforms = [expected_transform]
    else:
        expected_paths = []
        expected_transforms = []
    assert pb.paths == expected_paths
    assert pb.transforms == expected_transforms


@pytest.mark.parametrize(
    "transform, error",
    [
        ("translateX(5)", NotImplementedError),
        ("matrix(1 0 0 1 5)", ValueError),
        ("translate(5 7 9)", ValueError),
        ("rotate(90 10)", ValueError),
        ("skewX()", ValueError),
        ("translate(5", ValueError),
        ("foo translate(5)", ValueError),
        ("translate(5) bar", ValueError),
        ("translate(5);scale(2)", ValueError),
    ],
)
def test_el_to_path_invalid_transform(transform, error):
    pb = shapes.PathBuilder()
    el = etree.fromstring(f"<path d='M0,0' transform='{transform}'/>")
    with pytest.raises(error):
        pb.add_path_from_element(el)
