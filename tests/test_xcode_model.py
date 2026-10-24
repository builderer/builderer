import unittest

from builderer.details.file_types import FILE_KINDS
from builderer.generators.xcode.model import FileType, generate_id
from builderer.generators.xcode.model_builder import COMPILED_KINDS


class TestXcodeModel(unittest.TestCase):
    def test_source_types_follow_the_shared_file_kinds(self):
        for name, file_type in [
            ("a.c", FileType.C),
            ("a.cc", FileType.CPP),
            ("a.cpp", FileType.CPP),
            ("a.CXX", FileType.CPP),
            ("a.m", FileType.OBJC),
            ("a.mm", FileType.OBJCPP),
            ("a.swift", FileType.SWIFT),
            ("a.metal", FileType.METAL),
        ]:
            with self.subTest(name=name):
                self.assertEqual(FileType.for_source(name), file_type)

    def test_headers_are_c_or_cxx_headers(self):
        self.assertEqual(FileType.for_source("a.h"), FileType.C_HEADER)
        self.assertEqual(FileType.for_source("A.H"), FileType.C_HEADER)
        for name in [
            "a.hh",
            "a.hpp",
            "a.hxx",
            "a.inl",
            "a.inc",
            "a.def",
            "Eigen/Dense",
        ]:
            with self.subTest(name=name):
                self.assertEqual(FileType.for_source(name), FileType.CPP_HEADER)

    def test_unknown_sources_and_assembly_are_left_for_xcode_to_infer(self):
        # a stated type with no build rule makes Xcode skip the file; Xcode tells
        # .s from .S itself
        for name in ["a.s", "a.S", "a.txt", "a.png"]:
            with self.subTest(name=name):
                self.assertIsNone(FileType.for_source(name))

    def test_compiled_sources_are_never_typed_as_non_source(self):
        for ext, kind in FILE_KINDS.items():
            if kind in COMPILED_KINDS:
                file_type = FileType.for_source(f"a{ext}")
                with self.subTest(ext=ext):
                    if file_type is not None:
                        self.assertTrue(file_type.value.startswith("sourcecode."))

    def test_resources_are_never_typed_as_sources_or_headers(self):
        self.assertEqual(FileType.for_resource("Info.plist"), FileType.PLIST)
        self.assertEqual(FileType.for_resource("A.xcassets"), FileType.ASSET_CATALOG)
        # an extensionless resource is just data, not a header
        for name in ["LICENSE", "a.h", "a.cpp", "a.json"]:
            with self.subTest(name=name):
                self.assertIsNone(FileType.for_resource(name))

    def test_generate_id_is_24_chars_and_unique_per_key(self):
        # Xcode object identifiers must be 24-char and stable per key
        self.assertEqual(len(generate_id("k")), 24)
        self.assertNotEqual(generate_id("k"), generate_id("other"))


if __name__ == "__main__":
    unittest.main()
