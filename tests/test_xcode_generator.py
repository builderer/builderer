"""Tests for the Xcode model builder + formatter.

Builds a real project model from an in-memory workspace and asserts it is
internally consistent (the validator finds no dangling references) and that the
formatter emits a pbxproj skeleton. This exercises a large swath of
model_builder.py / formatter.py without touching disk or running Xcode.
"""

import unittest

from builderer.generators.xcode.model import ProductType
from builderer.generators.xcode.model_builder import generate_xcode_project
from builderer.generators.xcode.settings import CLANG_FLAGS, parse
from builderer.generators.xcode.formatter import format_xcode_project
from builderer.generators.xcode.validator import (
    validate_references,
    validate_output_paths,
)

from factories import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_package,
    make_workspace,
)


def _project(cxx_flags=[]):
    lib = make_cc_library(
        "mylib",
        srcs=["pkg/lib.cpp"],
        hdrs=["pkg/lib.h"],
        public_includes=["pkg/inc"],
        public_defines=["LIB=1"],
        cxx_flags=cxx_flags,
    )
    app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":mylib"])
    pkg = make_package("pkg", [lib, app])
    ws = make_workspace([pkg])
    config = make_config(
        buildtool="xcode",
        toolchain="clang",
        platform="macos",
        build_root="Out/build/macos.xcodeproj",
        architecture=["arm64"],
        build_config=["debug", "release"],
    )
    return generate_xcode_project(config, ws)


class TestXcodeGenerator(unittest.TestCase):
    def test_generated_model_has_no_dangling_references(self):
        proj = _project()
        self.assertEqual(validate_references(proj), [])
        validate_output_paths(proj)  # must not raise

    def test_model_has_a_native_target_per_build_target(self):
        by_name = {t.name: t.productType for t in _project().nativeTargets}
        self.assertEqual(by_name["pkg:mylib"], ProductType.STATIC_LIBRARY)
        self.assertEqual(by_name["pkg:app"], ProductType.TOOL)

    def test_model_includes_source_file_references(self):
        paths = {r.path for r in _project().fileReferences}
        self.assertTrue(any(p.endswith("lib.cpp") for p in paths))
        self.assertTrue(any(p.endswith("main.cpp") for p in paths))

    def test_formatter_emits_pbxproj_skeleton(self):
        text = format_xcode_project(_project())
        self.assertTrue(text.startswith("// !$*UTF8*$!"))
        self.assertIn("PBXNativeTarget", text)
        self.assertIn("rootObject", text)
        self.assertIn("pkg:app", text)


class TestCompilerFlagParsing(unittest.TestCase):
    def test_cxx_standard_flags_map_to_language_standard_setting(self):
        expected = {
            "-std=c++14": "c++14",
            "-std=c++17": "c++17",
            "-std=c++20": "c++20",
            "-std=c++23": "c++23",
            "-std=c++2b": "c++23",
            "-std=c++26": "c++26",
            "-std=c++2c": "c++26",
            "-std=gnu++14": "gnu++14",
            "-std=gnu++17": "gnu++17",
            "-std=gnu++20": "gnu++20",
            "-std=gnu++23": "gnu++23",
            "-std=gnu++2b": "gnu++23",
            "-std=gnu++26": "gnu++26",
            "-std=gnu++2c": "gnu++26",
        }
        for flag, value in expected.items():
            with self.subTest(flag=flag):
                settings, remaining = parse(CLANG_FLAGS, [flag])
                self.assertEqual(settings, {"CLANG_CXX_LANGUAGE_STANDARD": value})
                self.assertEqual(remaining, [])

    def test_target_cxx_standard_becomes_build_setting(self):
        proj = _project(cxx_flags=["-std=c++26"])
        configs = [
            c for c in proj.buildConfigurations if c.owner and "mylib" in c.owner
        ]
        self.assertTrue(configs)
        for config in configs:
            settings = config.buildSettings
            self.assertEqual(settings["CLANG_CXX_LANGUAGE_STANDARD"].value, "c++26")
            for name, setting in settings.items():
                if name.startswith("OTHER_CPLUSPLUSFLAGS"):
                    self.assertNotIn("-std=c++26", setting.value)
