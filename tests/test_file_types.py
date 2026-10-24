"""The shared file classification every generator uses (in memory, no disk).

The spec under test: a file's kind follows from its extension, compared
case-insensitively; known header spellings, and files without an extension, are
headers; anything else is unknown (None) so each generator applies its own policy.
"""

import unittest
from pathlib import Path

from builderer.details.file_types import (
    C_FAMILY_KINDS,
    FileKind,
    file_kind,
    kind_extensions,
)


class TestFileKind(unittest.TestCase):
    def test_sources_are_classified_by_language(self):
        for name, kind in [
            ("a.c", FileKind.C),
            ("a.cc", FileKind.CXX),
            ("a.cpp", FileKind.CXX),
            ("a.cxx", FileKind.CXX),
            ("a.m", FileKind.OBJC),
            ("a.mm", FileKind.OBJCXX),
            ("a.s", FileKind.ASM),
            ("a.S", FileKind.ASM),  # preprocessed assembly
            ("a.swift", FileKind.SWIFT),
            ("a.metal", FileKind.METAL),
        ]:
            with self.subTest(name=name):
                self.assertEqual(file_kind(name), kind)

    def test_header_spellings_are_headers(self):
        for name in [
            "a.h",
            "a.hh",
            "a.hpp",
            "a.hxx",
            "a.inl",
            "a.inc",
            "a.def",
            "a.tc",
            "a.th",
        ]:
            with self.subTest(name=name):
                self.assertEqual(file_kind(name), FileKind.HEADER)

    def test_extensionless_files_are_headers(self):
        # std-style headers such as Eigen's "Dense", even under dotted folders
        for name in ["Eigen/Dense", "lib-1.2/include/vector", "algorithm"]:
            with self.subTest(name=name):
                self.assertEqual(file_kind(name), FileKind.HEADER)

    def test_extensions_compare_case_insensitively(self):
        self.assertEqual(file_kind("A.CPP"), FileKind.CXX)
        self.assertEqual(file_kind("A.H"), FileKind.HEADER)
        self.assertEqual(file_kind("A.DEF"), FileKind.HEADER)

    def test_unknown_extensions_have_no_kind(self):
        for name in ["a.txt", "a.py", "a.tar.gz", "a.cpp.bak", "a.png"]:
            with self.subTest(name=name):
                self.assertIsNone(file_kind(name))

    def test_full_and_path_object_paths_are_accepted(self):
        self.assertEqual(file_kind(Path("/ws/pkg/src/a.cc")), FileKind.CXX)
        self.assertEqual(file_kind("pkg/../Out/.sandbox/r/h1/a.c"), FileKind.C)


class TestKindGroups(unittest.TestCase):
    def test_c_family_covers_everything_the_c_compilers_build(self):
        self.assertEqual(
            kind_extensions(C_FAMILY_KINDS),
            [".c", ".cc", ".cpp", ".cxx", ".m", ".mm", ".s"],
        )

    def test_headers_and_other_languages_are_not_c_family(self):
        for kind in (FileKind.HEADER, FileKind.SWIFT, FileKind.METAL):
            self.assertNotIn(kind, C_FAMILY_KINDS)


if __name__ == "__main__":
    unittest.main()
