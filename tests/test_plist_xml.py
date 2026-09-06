import unittest
from xml.dom.minidom import parseString

from builderer.generators.make.target_mk import (
    _plist_value_to_xml_lines,
    _plist_dict_to_xml_text,
)


class TestPlistValueToXmlLines(unittest.TestCase):
    def test_string_value(self):
        self.assertEqual(_plist_value_to_xml_lines("hi"), ["  <string>hi</string>"])

    def test_bool_serializes_as_flag_not_integer(self):
        # bool is an int subclass; it must serialize as <true/>/<false/>, not <integer>
        self.assertEqual(_plist_value_to_xml_lines(True), ["  <true/>"])
        self.assertEqual(_plist_value_to_xml_lines(False), ["  <false/>"])

    def test_numeric_values(self):
        self.assertEqual(_plist_value_to_xml_lines(7), ["  <integer>7</integer>"])
        self.assertEqual(_plist_value_to_xml_lines(2.5), ["  <real>2.5</real>"])

    def test_list_value_recurses(self):
        self.assertEqual(
            _plist_value_to_xml_lines(["a", 1]),
            [
                "  <array>",
                "    <string>a</string>",
                "    <integer>1</integer>",
                "  </array>",
            ],
        )

    def test_nested_dict_has_sorted_keys(self):
        self.assertEqual(
            _plist_value_to_xml_lines({"b": "2", "a": "1"}),
            [
                "  <dict>",
                "    <key>a</key>",
                "    <string>1</string>",
                "    <key>b</key>",
                "    <string>2</string>",
                "  </dict>",
            ],
        )

    def test_unsupported_type_raises(self):
        with self.assertRaisesRegex(ValueError, "unsupported info_plist value type"):
            _plist_value_to_xml_lines(object())


class TestPlistDictToXmlText(unittest.TestCase):
    def test_full_document_envelope(self):
        text = _plist_dict_to_xml_text({"CFBundleName": "Demo"})
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("<!DOCTYPE plist PUBLIC", text)
        self.assertIn('<plist version="1.0">', text)
        self.assertIn("  <key>CFBundleName</key>", text)
        self.assertIn("  <string>Demo</string>", text)
        self.assertTrue(text.endswith("</plist>"))

    def test_special_chars_are_escaped_so_the_document_stays_well_formed(self):
        # expected escaping derived from the XML spec, not from the code's output
        self.assertEqual(
            _plist_value_to_xml_lines("a & b <x>"),
            ["  <string>a &amp; b &lt;x&gt;</string>"],
        )
        # a CFBundleName with & or < is valid per AppleApplication's validator (it's a
        # str), so the generated Info.plist (keys and values) must still parse as XML
        parseString(_plist_dict_to_xml_text({"A & B": "Tom & Jerry <fun>"}))
