"""Tests for the Xcode model builder + formatter.

Builds a real project model from an in-memory workspace and asserts it is
internally consistent (the validator finds no dangling references) and that the
formatter emits a pbxproj skeleton. This exercises a large swath of
model_builder.py / formatter.py without touching disk or running Xcode.
"""

import unittest

from builderer.details.targets.swift_library import SwiftLibrary
from builderer.generators.xcode.model import (
    FileType,
    PBXSourcesBuildPhase,
    ProductType,
    SourceTree,
)
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

    def test_project_paths_are_posix_on_any_host(self):
        # Xcode reads POSIX paths, so a project generated on Windows must not carry
        # host separators, and a nested package's group must still nest.
        lib = make_cc_library(
            "mylib",
            workspace_root="pkg/sub",
            srcs=["pkg/sub/lib.cpp"],
            hdrs=["pkg/sub/lib.h"],
            public_includes=["pkg/sub/inc"],
        )
        app = make_cc_binary(
            "app", workspace_root="pkg/sub", srcs=["pkg/sub/main.cpp"], deps=[":mylib"]
        )
        pkg = make_package("pkg/sub", [lib, app])
        config = make_config(
            buildtool="xcode",
            toolchain="clang",
            platform="macos",
            build_root="Out/build/macos.xcodeproj",
            architecture=["arm64"],
            build_config=["debug"],
        )
        proj = generate_xcode_project(config, make_workspace([pkg]))
        self.assertNotIn("\\", format_xcode_project(proj))
        sub = next(g for g in proj.groups if g.name == "sub")
        self.assertEqual({c.comment for c in sub.children}, {"mylib", "app"})

    def test_formatter_emits_pbxproj_skeleton(self):
        text = format_xcode_project(_project())
        self.assertTrue(text.startswith("// !$*UTF8*$!"))
        self.assertIn("PBXNativeTarget", text)
        self.assertIn("rootObject", text)
        self.assertIn("pkg:app", text)


def _product_refs(proj):
    refs = {f.id: f for f in proj.fileReferences}
    return {t.name: refs[t.productReference.id] for t in proj.nativeTargets}


def _setting_values(proj):
    for config in proj.buildConfigurations:
        for name, setting in config.buildSettings.items():
            values = (
                setting.value if isinstance(setting.value, list) else [setting.value]
            )
            for value in values:
                yield name, value


class TestProductReferences(unittest.TestCase):
    def test_products_resolve_in_the_targets_built_products_dir(self):
        # each target's CONFIGURATION_BUILD_DIR is its BUILT_PRODUCTS_DIR, so the
        # product is the bare filename there (not a path that never exists)
        products = _product_refs(_project())
        self.assertEqual(products["pkg:mylib"].path, "libmylib.a")
        self.assertEqual(products["pkg:app"].path, "app")
        for ref in products.values():
            self.assertEqual(ref.sourceTree, SourceTree.BUILT_PRODUCTS_DIR)
            self.assertEqual(ref.includeInIndex, 0)
            self.assertIsNone(ref.lastKnownFileType)

    def test_products_carry_an_explicit_file_type_per_product_kind(self):
        swift_lib = SwiftLibrary(
            name="slib", workspace_root="pkg", srcs=["pkg/s.swift"]
        )
        lib = make_cc_library("clib", srcs=["pkg/c.cpp"])
        tool = make_cc_binary("tool", srcs=["pkg/m.cpp"])
        pkg = make_package("pkg", [swift_lib, lib, tool])
        config = make_config(
            buildtool="xcode",
            toolchain="clang",
            platform="macos",
            build_root="Out/build/macos.xcodeproj",
            architecture=["arm64"],
        )
        products = _product_refs(generate_xcode_project(config, make_workspace([pkg])))
        self.assertEqual(products["pkg:slib"].explicitFileType, FileType.ARCHIVE)
        self.assertEqual(products["pkg:clib"].explicitFileType, FileType.ARCHIVE)
        self.assertEqual(products["pkg:tool"].explicitFileType, FileType.EXECUTABLE)

    def test_same_product_name_in_two_packages_keeps_both_references(self):
        # bare product filenames repeat across packages; their IDs must not, or one
        # target's product reference would silently replace the other's
        a = make_package(
            "a", [make_cc_library("lib", workspace_root="a", srcs=["a/x.cpp"])]
        )
        b = make_package(
            "b", [make_cc_library("lib", workspace_root="b", srcs=["b/x.cpp"])]
        )
        config = make_config(
            buildtool="xcode",
            toolchain="clang",
            platform="macos",
            build_root="Out/build/macos.xcodeproj",
            architecture=["arm64"],
        )
        proj = generate_xcode_project(config, make_workspace([a, b]))
        products = _product_refs(proj)
        self.assertNotEqual(products["a:lib"].id, products["b:lib"].id)
        self.assertEqual([f.path for f in proj.fileReferences].count("liblib.a"), 2)
        self.assertEqual(validate_references(proj), [])

    def test_file_references_use_keys_xcode_reads(self):
        text = format_xcode_project(_project())
        self.assertNotIn('"fileType"', text)
        self.assertIn('"lastKnownFileType" = "sourcecode.cpp.cpp"', text)
        self.assertIn('"explicitFileType" = "archive.ar"', text)


class TestSourceFileTypes(unittest.TestCase):
    def _project(self, srcs):
        lib = make_cc_library("lib", srcs=srcs)
        config = make_config(
            buildtool="xcode",
            toolchain="clang",
            platform="macos",
            build_root="Out/build/macos.xcodeproj",
            architecture=["arm64"],
        )
        return generate_xcode_project(
            config, make_workspace([make_package("pkg", [lib])])
        )

    def test_every_compilable_source_is_compiled_with_a_source_type(self):
        # Xcode skips a compiled file whose stated type has no build rule, so
        # each one must be in the sources phase and never typed as non-source
        srcs = ["pkg/a.c", "pkg/b.cc", "pkg/c.cpp", "pkg/d.cxx", "pkg/e.m", "pkg/f.mm"]
        proj = self._project(srcs + ["pkg/g.s"])
        refs = {f.path: f for f in proj.fileReferences}
        compiled = {
            bf.fileRef.id
            for phase in proj.buildPhases
            if isinstance(phase, PBXSourcesBuildPhase)
            for bf_ref in phase.files
            for bf in proj.buildFiles
            if bf.id == bf_ref.id
        }
        for path in srcs + ["pkg/g.s"]:
            with self.subTest(path=path):
                self.assertIn(refs[path].id, compiled)
                file_type = refs[path].lastKnownFileType
                self.assertTrue(
                    file_type is None or file_type.value.startswith("sourcecode.")
                )
        self.assertEqual(refs["pkg/b.cc"].lastKnownFileType, FileType.CPP)
        self.assertEqual(refs["pkg/d.cxx"].lastKnownFileType, FileType.CPP)

    def test_header_like_includes_are_typed_but_not_compiled(self):
        proj = self._project(["pkg/a.cpp", "pkg/table.inc", "pkg/impl.inl"])
        refs = {f.path: f for f in proj.fileReferences}
        compiled = {
            bf.fileRef.id
            for phase in proj.buildPhases
            if isinstance(phase, PBXSourcesBuildPhase)
            for bf_ref in phase.files
            for bf in proj.buildFiles
            if bf.id == bf_ref.id
        }
        for path in ("pkg/table.inc", "pkg/impl.inl"):
            with self.subTest(path=path):
                self.assertEqual(refs[path].lastKnownFileType, FileType.CPP_HEADER)
                self.assertNotIn(refs[path].id, compiled)

    def test_unknown_types_are_not_stated(self):
        proj = self._project(["pkg/a.cpp", "pkg/notes.txt"])
        ref = next(f for f in proj.fileReferences if f.path == "pkg/notes.txt")
        self.assertIsNone(ref.lastKnownFileType)
        self.assertNotIn('"text"', format_xcode_project(proj))


class TestBuildLocations(unittest.TestCase):
    def test_nothing_is_built_inside_the_project_bundle(self):
        for name, value in _setting_values(_project()):
            if isinstance(value, str):
                with self.subTest(setting=name):
                    self.assertNotIn("macos.xcodeproj", value)

    def test_build_dirs_sit_beside_the_project_bundle(self):
        settings = dict(_setting_values(_project()))
        self.assertEqual(settings["OBJROOT"], "$(SRCROOT)/Out/build/macos.noindex/.obj")
        self.assertEqual(settings["SYMROOT"], "$(SRCROOT)/Out/build/macos.noindex/.sym")
        self.assertTrue(
            settings["CONFIGURATION_BUILD_DIR"].startswith(
                "$(SRCROOT)/Out/build/macos.noindex/.artifacts/"
            )
        )


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
