import unittest
from pathlib import Path

from builderer.generators.msbuild.utils import msbuild_escape, msvc_file_rule


class TestMsbuildEscape(unittest.TestCase):
    def test_msbuild_escape_escapes_special_characters(self):
        self.assertEqual(msbuild_escape("%$@';?*"), "%25%24%40%27%3B%3F%2A")

    def test_msbuild_escape_keeps_other_characters(self):
        value = "..\\Out dir\\my-app_1.0 (x64)!#&+,=[]{}~"
        self.assertEqual(msbuild_escape(value), value)


class TestMsvcFileRule(unittest.TestCase):
    def test_msvc_file_rule_classifies_sources_as_compile(self):
        for name in ["a.cpp", "a.cc", "a.cxx", "a.c", "A.CPP"]:
            with self.subTest(name=name):
                self.assertEqual(msvc_file_rule(Path(name)), "ClCompile")

    def test_msvc_file_rule_classifies_headers_as_include(self):
        for name in [
            "a.h",
            "a.hh",
            "a.hpp",
            "a.hxx",
            "a.inl",
            "a.inc",
            "a.def",
            "A.DEF",
            "a.tc",
            "a.th",
        ]:
            with self.subTest(name=name):
                self.assertEqual(msvc_file_rule(Path(name)), "ClInclude")

    def test_msvc_file_rule_treats_extensionless_file_as_header(self):
        # std-style headers like Eigen's "Dense" have no extension
        self.assertEqual(msvc_file_rule(Path("Eigen/Dense")), "ClInclude")

    def test_msvc_file_rule_rejects_unknown_extension(self):
        with self.assertRaisesRegex(ValueError, "Unsupported file extension"):
            msvc_file_rule(Path("a.txt"))

    def test_msvc_file_rule_rejects_sources_msvc_does_not_compile(self):
        # Objective-C, GNU assembly, Swift and Metal have no MSVC compile rule
        for name in ["a.m", "a.mm", "a.s", "a.swift", "a.metal"]:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Unsupported file extension"):
                    msvc_file_rule(Path(name))
