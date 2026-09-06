import unittest

from builderer.generators.xcode.model import FileType, generate_id


class TestXcodeModel(unittest.TestCase):
    def test_filetype_from_extension_maps_known_and_falls_back_to_text(self):
        self.assertEqual(FileType.from_extension(".cpp"), FileType.CPP)
        # accepts no leading dot
        self.assertEqual(FileType.from_extension("mm"), FileType.OBJCPP)
        self.assertEqual(FileType.from_extension(".h"), FileType.C_HEADER)
        # unknown -> TEXT
        self.assertEqual(FileType.from_extension(".xyz"), FileType.TEXT)

    def test_generate_id_is_24_chars_and_unique_per_key(self):
        # Xcode object identifiers must be 24-char and stable per key
        self.assertEqual(len(generate_id("k")), 24)
        self.assertNotEqual(generate_id("k"), generate_id("other"))
