from io import BytesIO
import os
import unittest
from xml.etree import ElementTree
from fontTools.misc.textTools import bytesjoin, tobytes
from fontTools.misc.xmlWriter import XMLWriter

HEADER = b'<?xml version="1.0" encoding="UTF-8"?>\n'


class TestXMLWriter(unittest.TestCase):
    def test_attribute_whitespace_roundtrip(self):
        for value in (
            "tab\tvalue",
            "line\nvalue",
            "carriage\rreturn",
            'quotes\t<&>"\r\n',
        ):
            with self.subTest(value=value):
                writer = XMLWriter(BytesIO())
                writer.simpletag("node", value=value)
                self.assertEqual(
                    value,
                    ElementTree.fromstring(writer.file.getvalue()).attrib["value"],
                )

    def test_comment_escaped(self):
        writer = XMLWriter(BytesIO())
        writer.comment("This&that are <comments>")
        self.assertEqual(
            HEADER + b"<!-- This&amp;that are &lt;comments&gt; -->",
            writer.file.getvalue(),
        )

    def test_comment_multiline(self):
        writer = XMLWriter(BytesIO())
        writer.comment("Hello world\nHow are you?")
        self.assertEqual(
            HEADER + b"<!-- Hello world\n     How are you? -->", writer.file.getvalue()
        )

    def test_encoding_default(self):
        writer = XMLWriter(BytesIO())
        self.assertEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>\n', writer.file.getvalue()
        )

    def test_encoding_utf8(self):
        # https://github.com/fonttools/fonttools/issues/246
        writer = XMLWriter(BytesIO(), encoding="utf8")
        self.assertEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>\n', writer.file.getvalue()
        )

    def test_encoding_UTF_8(self):
        # https://github.com/fonttools/fonttools/issues/246
        writer = XMLWriter(BytesIO(), encoding="UTF-8")
        self.assertEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>\n', writer.file.getvalue()
        )

    def test_encoding_UTF8(self):
        # https://github.com/fonttools/fonttools/issues/246
        writer = XMLWriter(BytesIO(), encoding="UTF8")
        self.assertEqual(
            b'<?xml version="1.0" encoding="UTF-8"?>\n', writer.file.getvalue()
        )

    def test_encoding_other(self):
        self.assertRaises(Exception, XMLWriter, BytesIO(), encoding="iso-8859-1")

    def test_write(self):
        writer = XMLWriter(BytesIO())
        writer.write("foo&bar")
        self.assertEqual(HEADER + b"foo&amp;bar", writer.file.getvalue())

    def test_indent_dedent(self):
        writer = XMLWriter(BytesIO())
        writer.write("foo")
        writer.newline()
        writer.indent()
        writer.write("bar")
        writer.newline()
        writer.dedent()
        writer.write("baz")
        self.assertEqual(
            HEADER + bytesjoin(["foo", "  bar", "baz"], "\n"), writer.file.getvalue()
        )

    def test_writecdata(self):
        writer = XMLWriter(BytesIO())
        writer.writecdata("foo&bar")
        self.assertEqual(HEADER + b"<![CDATA[foo&bar]]>", writer.file.getvalue())

    def test_writecdata_split_terminator(self):
        writer = XMLWriter(BytesIO())
        writer.writecdata("foo]]><tag/>bar")
        self.assertEqual(
            HEADER + b"<![CDATA[foo]]]]><![CDATA[><tag/>bar]]>",
            writer.file.getvalue(),
        )

    def test_simpletag(self):
        writer = XMLWriter(BytesIO())
        writer.simpletag("tag", a="1", b="2")
        self.assertEqual(HEADER + b'<tag a="1" b="2"/>', writer.file.getvalue())

    def test_begintag_endtag(self):
        writer = XMLWriter(BytesIO())
        writer.begintag("tag", attr="value")
        writer.write("content")
        writer.endtag("tag")
        self.assertEqual(
            HEADER + b'<tag attr="value">content</tag>', writer.file.getvalue()
        )

    def test_dumphex(self):
        writer = XMLWriter(BytesIO())
        writer.dumphex(
            "Type is a beautiful group of letters, not a group of beautiful letters."
        )
        self.assertEqual(
            HEADER
            + bytesjoin(
                [
                    "54797065 20697320 61206265 61757469",
                    "66756c20 67726f75 70206f66 206c6574",
                    "74657273 2c206e6f 74206120 67726f75",
                    "70206f66 20626561 75746966 756c206c",
                    "65747465 72732e  ",
                    "",
                ],
                joiner="\n",
            ),
            writer.file.getvalue(),
        )

    def test_stringifyattrs(self):
        writer = XMLWriter(BytesIO())
        expected = ' attr="0"'
        self.assertEqual(expected, writer.stringifyattrs(attr=0))
        self.assertEqual(expected, writer.stringifyattrs(attr=b"0"))
        self.assertEqual(expected, writer.stringifyattrs(attr="0"))
        self.assertEqual(expected, writer.stringifyattrs(attr="0"))

    def test_carriage_return_escaped(self):
        writer = XMLWriter(BytesIO())
        writer.write("two lines\r\nseparated by Windows line endings")
        self.assertEqual(
            HEADER + b"two lines&#13;\nseparated by Windows line endings",
            writer.file.getvalue(),
        )

    def test_newlinestr(self):
        header = b'<?xml version="1.0" encoding="UTF-8"?>'

        for nls in (None, "\n", "\r\n", "\r", ""):
            writer = XMLWriter(BytesIO(), newlinestr=nls)
            writer.write("hello")
            writer.newline()
            writer.write("world")
            writer.newline()

            linesep = tobytes(os.linesep) if nls is None else tobytes(nls)

            self.assertEqual(
                header + linesep + b"hello" + linesep + b"world" + linesep,
                writer.file.getvalue(),
            )


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
