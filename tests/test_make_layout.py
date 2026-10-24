"""Make intermediates layout (in memory, no disk).

The spec under test:
- objects live at $(OBJS_ROOT)/<package>/<target>/<object path>, with
  OBJS_ROOT = <build_root>/.obj/<arch>/<config>;
- <object path> is the source's path relative to the lowest common ancestor
  directory of the target's compiled sources, plus ".o" (".air" for Metal), so
  distinct sources never collide and nothing contains "..";
- dependency files sit beside their objects as <source>.d;
- each target writes rules.mk (objects and rules) and options.mk (every setting);
  objects depend on options.mk and outputs on both, so adding or removing
  sources never recompiles anything else;
- Swift and Metal intermediates live in the target's own directory.
"""

import io
import os
import unittest
from pathlib import Path, PurePosixPath

from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_library import SwiftLibrary
from builderer.generators.make.root_makefile import RootMakefile
from builderer.generators.make.target_mk import TargetMk
from builderer.generators.make.utils import object_subpaths, target_obj_dir

from factories import (
    make_apple_application,
    make_config,
    make_cc_binary,
    make_cc_library,
    make_package,
    make_workspace,
)

WS = Path("/ws")


def _config(platform="linux", **over):
    if platform == "macos":
        over.setdefault("toolchain", "clang")
        over.setdefault("architecture", "arm64")
    return make_config(
        platform=platform,
        toolchain=over.pop("toolchain", "gcc"),
        buildtool="make",
        architecture=over.pop("architecture", "x86-64"),
        build_config="debug",
        build_root="Out/build/linux",
        **over,
    )


# (rules.mk text, options.mk text) of a target
def _render(target, package, workspace, config=None):
    config = config or _config()
    tm = TargetMk(config, workspace, Path("unused"), package, target)
    return tm.rules_text(), tm.options_text()


# A workspace-relative directory as make sees it from the test workspace root
def _ws_rel(path):
    return Path(os.path.relpath(Path(path).resolve(), Path(".").resolve())).as_posix()


def _single(target, package_name="pkg", config=None):
    pkg = make_package(package_name, [target])
    return _render(target, pkg, make_workspace([pkg]), config)


# The source patterns build files produce, as builderer hands them to make:
# workspace-relative, with "pkg/../" segments from {Pkg:target} expansion.
LAYOUT_CASES = {
    "first-party": (
        ["apps/triangle/main.c"],
        {"apps/triangle/main.c": "main.c"},
    ),
    "borrowed from one repo": (
        [
            "external/../Out/.sandbox/external/glfw_repo/h1/src/context.c",
            "external/../Out/.sandbox/external/glfw_repo/h1/src/cocoa_init.m",
        ],
        {
            "external/../Out/.sandbox/external/glfw_repo/h1/src/context.c": "context.c",
            "external/../Out/.sandbox/external/glfw_repo/h1/src/cocoa_init.m": "cocoa_init.m",
        },
    ),
    "local unit against repo headers": (
        ["External/Khronos/vk_mem_alloc.cpp"],
        {"External/Khronos/vk_mem_alloc.cpp": "vk_mem_alloc.cpp"},
    ),
    "local unit plus a repo source": (
        [
            "External/STB/my_custom_symbols.c",
            "External/STB/../../Out/.sandbox/External/STB/repo/h1/stb_image.c",
        ],
        {
            "External/STB/my_custom_symbols.c": "External/STB/my_custom_symbols.c",
            "External/STB/../../Out/.sandbox/External/STB/repo/h1/stb_image.c": "Out/.sandbox/External/STB/repo/h1/stb_image.c",
        },
    ),
    "local src/ plus repo src/": (
        [
            "External/Dawn/src/x.cpp",
            "External/Dawn/../../Out/.sandbox/External/Dawn/DawnRepo/h1/src/tint/lang/core/type/type.cc",
        ],
        {
            "External/Dawn/src/x.cpp": "External/Dawn/src/x.cpp",
            "External/Dawn/../../Out/.sandbox/External/Dawn/DawnRepo/h1/src/tint/lang/core/type/type.cc": "Out/.sandbox/External/Dawn/DawnRepo/h1/src/tint/lang/core/type/type.cc",
        },
    ),
    "a repo plus generated code": (
        [
            "External/Khronos/../../Out/.sandbox/External/Khronos/SpirVToolsRepo/h1/source/a.cpp",
            "External/Khronos/../../Out/.sandbox/External/Khronos/SpirVTools-CodeGen/h2/gen.cpp",
        ],
        {
            "External/Khronos/../../Out/.sandbox/External/Khronos/SpirVToolsRepo/h1/source/a.cpp": "SpirVToolsRepo/h1/source/a.cpp",
            "External/Khronos/../../Out/.sandbox/External/Khronos/SpirVTools-CodeGen/h2/gen.cpp": "SpirVTools-CodeGen/h2/gen.cpp",
        },
    ),
    "sources in subfolders": (
        ["pkg/src/a.c", "pkg/src/sub/b.c"],
        {"pkg/src/a.c": "a.c", "pkg/src/sub/b.c": "sub/b.c"},
    ),
    "sources in subfolders plus one above": (
        ["pkg/src/a.c", "pkg/src/sub/b.c", "pkg/x.c"],
        {"pkg/src/a.c": "src/a.c", "pkg/src/sub/b.c": "src/sub/b.c", "pkg/x.c": "x.c"},
    ),
    "same file names in different folders": (
        ["r/a/type.cc", "r/b/type.cc", "r/a/b/type.cc"],
        {
            "r/a/type.cc": "a/type.cc",
            "r/b/type.cc": "b/type.cc",
            "r/a/b/type.cc": "a/b/type.cc",
        },
    ),
    "same stem, different language": (
        ["pkg/a.c", "pkg/a.cpp"],
        {"pkg/a.c": "a.c", "pkg/a.cpp": "a.cpp"},
    ),
    "sandbox outside the workspace": (
        ["pkg/x.c", "/tmp/sb/pkg/repo/h1/y.c"],
        {"pkg/x.c": "ws/pkg/x.c", "/tmp/sb/pkg/repo/h1/y.c": "tmp/sb/pkg/repo/h1/y.c"},
    ),
    "sandbox=True copy of mixed sources": (
        [
            "Out/.sandbox/pkg/t/h1/source/x.c",
            "Out/.sandbox/pkg/t/h1/source/../Out/.sandbox/pkg/repo/h2/y.c",
        ],
        {
            "Out/.sandbox/pkg/t/h1/source/x.c": "source/x.c",
            "Out/.sandbox/pkg/t/h1/source/../Out/.sandbox/pkg/repo/h2/y.c": "Out/.sandbox/pkg/repo/h2/y.c",
        },
    ),
}


class TestObjectSubpaths(unittest.TestCase):
    def test_source_patterns_map_to_expected_object_paths(self):
        for name, (srcs, expected) in LAYOUT_CASES.items():
            with self.subTest(case=name):
                _, subpaths = object_subpaths(srcs, WS)
                self.assertEqual(subpaths, expected)

    def test_object_paths_are_distinct_and_never_climb(self):
        for name, (srcs, _) in LAYOUT_CASES.items():
            with self.subTest(case=name):
                _, subpaths = object_subpaths(srcs, WS)
                self.assertEqual(len(set(subpaths.values())), len(srcs))
                for subpath in subpaths.values():
                    parts = PurePosixPath(subpath).parts
                    self.assertNotIn("..", parts)
                    self.assertFalse(PurePosixPath(subpath).is_absolute())

    def test_ancestor_is_the_deepest_shared_directory(self):
        ancestor, _ = object_subpaths(["pkg/src/a.c", "pkg/src/sub/b.c"], WS)
        self.assertEqual(ancestor, "/ws/pkg/src")

    def test_no_sources_have_no_ancestor(self):
        self.assertEqual(object_subpaths([], WS), (None, {}))


class TestObjectRules(unittest.TestCase):
    def test_objects_live_in_the_targets_intermediates_directory(self):
        rules, options = _single(make_cc_library("lib", srcs=["pkg/a.cpp"]))
        self.assertIn("OBJ_DIR__pkg@lib := $(OBJS_ROOT)/pkg/lib\n", rules)
        self.assertIn(
            "$(OBJ_DIR__pkg@lib)/a.cpp.o: $(SRC_ROOT__pkg@lib)/a.cpp "
            "$(OPTIONS__pkg@lib)\n",
            rules,
        )
        self.assertIn(
            f"SRC_ROOT__pkg@lib := $(WORKSPACE_ROOT)/{_ws_rel('pkg')}\n", options
        )

    def test_nested_and_root_packages_map_to_directories(self):
        nested = make_package("a/b", [make_cc_library("t", srcs=["a/b/x.c"])])
        root = make_package(".", [make_cc_library("t", srcs=["x.c"])])
        self.assertEqual(
            target_obj_dir(nested, nested.targets["t"]), "$(OBJS_ROOT)/a/b/t"
        )
        self.assertEqual(target_obj_dir(root, root.targets["t"]), "$(OBJS_ROOT)/t")

    def test_dependency_files_sit_beside_their_objects(self):
        rules, options = _single(make_cc_library("lib", srcs=["pkg/a.c"]))
        self.assertIn("DEPS__pkg@lib := $(OBJS__pkg@lib:.o=.d)\n", rules)
        self.assertIn("-include $(DEPS__pkg@lib)\n", rules)
        self.assertIn("-MF $(@:.o=.d)", options)

    def test_only_compiled_sources_shape_object_paths(self):
        # srcs routinely list headers and .def files from other folders
        lib = make_cc_library(
            "lib", srcs=["pkg/src/a.c", "pkg/include/a.h", "pkg/defs/x.def"]
        )
        rules, options = _single(lib)
        self.assertIn("$(OBJ_DIR__pkg@lib)/a.c.o:", rules)
        self.assertNotIn("a.h", rules)
        self.assertNotIn("x.def", rules)
        self.assertIn(f"$(WORKSPACE_ROOT)/{_ws_rel('pkg/src')}\n", options)

    def test_c_and_cxx_sources_use_their_own_compiler(self):
        rules, _ = _single(make_cc_library("lib", srcs=["pkg/a.c", "pkg/a.cpp"]))
        c_rule = rules.split("$(OBJ_DIR__pkg@lib)/a.c.o:")[1].split("\n\n")[0]
        cxx_rule = rules.split("$(OBJ_DIR__pkg@lib)/a.cpp.o:")[1].split("\n\n")[0]
        self.assertIn("$(CC_COMPILE__pkg@lib)", c_rule)
        self.assertIn("$(CXX_COMPILE__pkg@lib)", cxx_rule)

    def test_compile_commands_compile_the_first_prerequisite(self):
        _, options = _single(make_cc_library("lib", srcs=["pkg/a.c"]))
        compile_line = next(
            l for l in options.splitlines() if l.startswith("CC_COMPILE__")
        )
        self.assertIn(" = $(CC) ", compile_line)  # expanded per object at recipe time
        self.assertIn("-c $< -o $@", compile_line)

    def test_same_source_in_two_targets_gets_two_objects_with_own_flags(self):
        a = make_cc_library("a", srcs=["pkg/shared.c"], private_defines=["A"])
        b = make_cc_library("b", srcs=["pkg/shared.c"], private_defines=["B"])
        pkg = make_package("pkg", [a, b])
        ws = make_workspace([pkg])
        rules_a, options_a = _render(a, pkg, ws)
        rules_b, options_b = _render(b, pkg, ws)
        self.assertIn("OBJ_DIR__pkg@a := $(OBJS_ROOT)/pkg/a\n", rules_a)
        self.assertIn("OBJ_DIR__pkg@b := $(OBJS_ROOT)/pkg/b\n", rules_b)
        self.assertIn("DEFINES__pkg@a := A", options_a)
        self.assertIn("DEFINES__pkg@b := B", options_b)


class TestMakefiles(unittest.TestCase):
    """rules.mk holds the object list and rules; options.mk every setting that
    decides how the target builds. Objects depend on options.mk, outputs on
    both, so editing sources rebuilds only those objects plus the output."""

    def _texts(self, **kwargs):
        kwargs.setdefault("srcs", ["pkg/src/a.c"])
        return _single(make_cc_binary("app", **kwargs))

    def test_files_live_in_the_targets_directory(self):
        lib = make_cc_library("lib", srcs=["a/b/x.c"])
        pkg = make_package("a/b", [lib])
        tm = TargetMk(_config(), make_workspace([pkg]), Path("root"), pkg, lib)
        self.assertEqual(tm.path, Path("root/a/b/lib/rules.mk"))
        self.assertEqual(tm.options_path, Path("root/a/b/lib/options.mk"))

    def test_rules_include_the_options_first(self):
        rules, _ = self._texts()
        self.assertTrue(
            rules.startswith(
                "# Generated by Builderer\n\n"
                "include $(BUILD_CONFIG_ROOT)/pkg/app/options.mk\n"
            )
        )

    def test_each_option_change_changes_only_the_options(self):
        base_rules, base_options = self._texts()
        for change in [
            {"private_defines": ["X=1"]},
            {"c_flags": ["-O2"]},
            {"link_flags": ["-lm"]},
            {"private_includes": ["pkg/../Out/.sandbox/pkg/repo/h2/include"]},
            {"srcs": ["pkg/source/a.c"]},  # the sources moved
        ]:
            with self.subTest(change=change):
                rules, options = self._texts(**change)
                self.assertNotEqual(options, base_options)
                if "srcs" not in change:
                    self.assertEqual(rules, base_rules)

    def test_adding_or_removing_sources_changes_only_the_rules(self):
        two_rules, two_options = self._texts(srcs=["pkg/src/a.c", "pkg/src/b.c"])
        three_rules, three_options = self._texts(
            srcs=["pkg/src/a.c", "pkg/src/b.c", "pkg/src/c.c"]
        )
        self.assertEqual(two_options, three_options)
        self.assertNotEqual(two_rules, three_rules)

    def test_objects_depend_on_options_and_outputs_on_both_files(self):
        rules, _ = _single(make_cc_library("lib", srcs=["pkg/a.c", "pkg/b.cpp"]))
        self.assertIn(
            "OPTIONS__pkg@lib := $(BUILD_CONFIG_ROOT)/pkg/lib/options.mk\n", rules
        )
        self.assertIn(
            "RULES__pkg@lib := $(BUILD_CONFIG_ROOT)/pkg/lib/rules.mk\n", rules
        )
        object_rules = [
            l for l in rules.splitlines() if l.startswith("$(OBJ_DIR__pkg@lib)/")
        ]
        self.assertEqual(len(object_rules), 2)
        for rule in object_rules:
            self.assertTrue(rule.endswith(" $(OPTIONS__pkg@lib)"))
        output_rule = next(l for l in rules.splitlines() if "liblib.a:" in l)
        self.assertIn("$(OPTIONS__pkg@lib)", output_rule)
        self.assertIn("$(RULES__pkg@lib)", output_rule)

    def test_makefiles_are_not_linked_or_archived(self):
        # outputs depend on the makefiles, so recipes list their inputs explicitly
        rules, _ = self._texts()
        self.assertNotIn("$^", rules)

    def test_app_bundle_repackages_when_its_rules_change(self):
        binary = make_cc_binary("bin", srcs=["pkg/main.c"])
        app = make_apple_application(
            "App.app", binary=":bin", info_plist={"CFBundleIdentifier": "x"}
        )
        pkg = make_package("pkg", [binary, app])
        tm = TargetMk(
            _config(platform="macos"), make_workspace([pkg]), Path("r"), pkg, app
        )
        self.assertIsNone(tm.options_text())
        bundle_rule = next(
            l
            for l in tm.rules_text().splitlines()
            if l.startswith("$(WORKSPACE_ROOT)/") and "App.app:" in l
        )
        self.assertTrue(bundle_rule.endswith(" $(RULES__pkg@App.app)"))


class TestSwiftIntermediates(unittest.TestCase):
    def setUp(self):
        self.lib = SwiftLibrary(
            name="sl", workspace_root="pkg", srcs=["pkg/a.swift"], swift_header="sl.h"
        )
        self.app = SwiftBinary(
            name="app", workspace_root="pkg", srcs=["pkg/main.swift"], deps=[":sl"]
        )
        self.cc = make_cc_binary("cc", srcs=["pkg/m.c"], deps=[":sl"])
        self.pkg = make_package("pkg", [self.lib, self.app, self.cc])
        self.ws = make_workspace([self.pkg])
        self.config = _config(platform="macos")

    def test_library_outputs_live_in_its_intermediates_directory(self):
        rules, _ = _render(self.lib, self.pkg, self.ws, self.config)
        self.assertIn("SWIFT_OBJ__pkg@sl := $(OBJS_ROOT)/pkg/sl/sl.swift.o\n", rules)
        self.assertIn(
            "SWIFTMODULE__pkg@sl := $(OBJS_ROOT)/pkg/sl/sl.swiftmodule\n", rules
        )
        self.assertIn(
            "SWIFTHEADER__pkg@sl := $(OBJS_ROOT)/pkg/sl/include/sl.h\n", rules
        )

    def test_swift_dependents_search_the_dependency_targets_directory(self):
        rules, options = _render(self.app, self.pkg, self.ws, self.config)
        self.assertIn("SWIFT_MODULE_I__pkg@app := -I $(OBJS_ROOT)/pkg/sl\n", options)
        self.assertIn("$(OBJS_ROOT)/pkg/sl/sl.swiftmodule", rules)

    def test_c_dependents_include_the_emitted_header(self):
        rules, options = _render(self.cc, self.pkg, self.ws, self.config)
        self.assertIn("$(OBJS_ROOT)/pkg/sl/include", options)
        self.assertIn("| $(OBJS_ROOT)/pkg/sl/include/sl.h", rules)

    def test_module_compile_depends_on_both_makefiles(self):
        # the module compiles whole, so its source list (rules.mk) matters too
        rules, _ = _render(self.lib, self.pkg, self.ws, self.config)
        compile_rule = next(
            l for l in rules.splitlines() if l.startswith("$(SWIFT_OBJ")
        )
        self.assertIn("$(OPTIONS__pkg@sl)", compile_rule)
        self.assertIn("$(RULES__pkg@sl)", compile_rule)


class TestMetalIntermediates(unittest.TestCase):
    def test_air_files_live_in_the_targets_intermediates_directory(self):
        shaders = MetalLibrary(
            name="shaders",
            workspace_root="pkg",
            srcs=["pkg/metal/a.metal", "pkg/metal/sub/b.metal"],
        )
        rules, options = _single(shaders, config=_config(platform="macos"))
        self.assertIn(
            "$(OBJS_ROOT)/pkg/shaders/a.metal.air: $(SRC_ROOT__pkg@shaders)/a.metal "
            "$(OPTIONS__pkg@shaders)\n",
            rules,
        )
        self.assertIn("$(OBJS_ROOT)/pkg/shaders/sub/b.metal.air:", rules)
        self.assertIn("METALFLAGS__pkg@shaders := -target air64-apple-macos", options)
        self.assertIn(
            f"SRC_ROOT__pkg@shaders := $(WORKSPACE_ROOT)/{_ws_rel('pkg/metal')}\n",
            options,
        )


class TestRootMakefile(unittest.TestCase):
    def _root(self):
        lib = make_cc_library("lib", srcs=["pkg/a.c"])
        ws = make_workspace([make_package("pkg", [lib])])
        buf = io.StringIO()
        RootMakefile(config=_config(), workspace=ws)._write_makefile(buf)
        return buf.getvalue()

    def test_objects_root_is_per_arch_and_config_under_the_build_root(self):
        self.assertIn(
            "OBJS_ROOT         := $(BUILD_ROOT)/.obj/$(ARCH)/$(CONFIG)\n", self._root()
        )

    def test_unused_roots_are_gone(self):
        root = self._root()
        self.assertNotIn("LIBS_ROOT", root)
        self.assertNotIn("RUNTIME_ROOT", root)

    def test_moved_c_family_sources_cannot_stop_the_build(self):
        root = self._root()
        for ext in (".c", ".m", ".cc", ".cpp", ".cxx", ".mm"):
            self.assertIn(f"\n%{ext}: ;\n", root)


if __name__ == "__main__":
    unittest.main()
