from xml.dom.minidom import parseString

import pytest

from builderer.generators.make.target_mk import (
    _plist_value_to_xml_lines,
    _plist_dict_to_xml_text,
)


def test_string_value():
    assert _plist_value_to_xml_lines("hi") == ["  <string>hi</string>"]


def test_bool_serializes_as_flag_not_integer():
    # bool is an int subclass; it must serialize as <true/>/<false/>, not <integer>
    assert _plist_value_to_xml_lines(True) == ["  <true/>"]
    assert _plist_value_to_xml_lines(False) == ["  <false/>"]


def test_numeric_values():
    assert _plist_value_to_xml_lines(7) == ["  <integer>7</integer>"]
    assert _plist_value_to_xml_lines(2.5) == ["  <real>2.5</real>"]


def test_list_value_recurses():
    assert _plist_value_to_xml_lines(["a", 1]) == [
        "  <array>",
        "    <string>a</string>",
        "    <integer>1</integer>",
        "  </array>",
    ]


def test_nested_dict_has_sorted_keys():
    assert _plist_value_to_xml_lines({"b": "2", "a": "1"}) == [
        "  <dict>",
        "    <key>a</key>",
        "    <string>1</string>",
        "    <key>b</key>",
        "    <string>2</string>",
        "  </dict>",
    ]


def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="unsupported info_plist value type"):
        _plist_value_to_xml_lines(object())


def test_full_document_envelope():
    text = _plist_dict_to_xml_text({"CFBundleName": "Demo"})
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE plist PUBLIC" in text
    assert '<plist version="1.0">' in text
    assert "  <key>CFBundleName</key>" in text
    assert "  <string>Demo</string>" in text
    assert text.endswith("</plist>")


def test_special_chars_are_escaped_so_the_document_stays_well_formed():
    # expected escaping derived from the XML spec, not from the code's output
    assert _plist_value_to_xml_lines("a & b <x>") == [
        "  <string>a &amp; b &lt;x&gt;</string>"
    ]
    # a CFBundleName with & or < is valid per AppleApplication's validator (it's a
    # str), so the generated Info.plist (keys and values) must still parse as XML
    parseString(_plist_dict_to_xml_text({"A & B": "Tom & Jerry <fun>"}))
