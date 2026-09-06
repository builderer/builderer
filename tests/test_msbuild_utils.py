import unittest
from pathlib import Path

from builderer.generators.msbuild.utils import msvc_file_rule


class TestMsvcFileRule(unittest.TestCase):
    def test_msvc_file_rule_classifies_sources_as_compile(self):
        for name in ["a.cpp", "a.cc", "a.cxx", "a.c", "A.CPP"]:
            with self.subTest(name=name):
                self.assertEqual(msvc_file_rule(Path(name)), "ClCompile")

    def test_msvc_file_rule_classifies_headers_as_include(self):
        for name in ["a.h", "a.hpp", "a.hxx", "a.inl", "a.inc", "a.tc", "a.th"]:
            with self.subTest(name=name):
                self.assertEqual(msvc_file_rule(Path(name)), "ClInclude")

    def test_msvc_file_rule_treats_extensionless_file_as_header(self):
        # std-style headers like Eigen's "Dense" have no extension
        self.assertEqual(msvc_file_rule(Path("Eigen/Dense")), "ClInclude")

    def test_msvc_file_rule_rejects_unknown_extension(self):
        with self.assertRaisesRegex(ValueError, "Unsupported file extension"):
            msvc_file_rule(Path("a.txt"))
