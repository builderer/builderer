"""Make intermediates layout (in memory, no disk).

The spec under test:
- objects live at $(OBJS_ROOT)/<package>/<target>/<object path>, with
  OBJS_ROOT = <build_root>/.obj/<arch>/<config>;
- <object path> is the source's path relative to the lowest common ancestor
  directory of the target's compiled sources, plus ".o" (".air" for Metal), so
  distinct sources never collide and nothing contains "..";
- dependency files sit beside their objects as <source>.d;
- every object depends on its target's compile-settings stamp;
- Swift and Metal intermediates live in the target's own directory.
"""

import io
import unittest
from pathlib import Path, PurePosixPath

from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_library import SwiftLibrary
from builderer.generators.make.root_makefile import RootMakefile
from builderer.generators.make.target_mk import TargetMk
from builderer.generators.make.utils import object_subpaths, target_obj_dir

from factories import (
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


def _render(target, package, workspace, config=None):
    config = config or _config()
    tm = TargetMk(config, workspace, Path("unused"), package, target)
    buf = io.StringIO()
    tm._write_makefile(buf)
    return buf.getvalue(), tm.compile_stamp


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
        mk, _ = _single(make_cc_library("lib", srcs=["pkg/a.cpp"]))
        self.assertIn("OBJ_DIR__pkg@lib := $(OBJS_ROOT)/pkg/lib\n", mk)
        self.assertIn(
            "$(OBJ_DIR__pkg@lib)/a.cpp.o: $(WORKSPACE_ROOT)/pkg/a.cpp "
            "$(COMPILE_STAMP__pkg@lib)\n",
            mk,
        )

    def test_nested_and_root_packages_map_to_directories(self):
        nested = make_package("a/b", [make_cc_library("t", srcs=["a/b/x.c"])])
        root = make_package(".", [make_cc_library("t", srcs=["x.c"])])
        self.assertEqual(
            target_obj_dir(nested, nested.targets["t"]), "$(OBJS_ROOT)/a/b/t"
        )
        self.assertEqual(target_obj_dir(root, root.targets["t"]), "$(OBJS_ROOT)/t")

    def test_dependency_files_sit_beside_their_objects(self):
        mk, _ = _single(make_cc_library("lib", srcs=["pkg/a.c"]))
        self.assertIn("DEPS__pkg@lib := $(OBJS__pkg@lib:.o=.d)\n", mk)
        self.assertIn("-MF $(@:.o=.d)", mk)
        self.assertIn("-include $(DEPS__pkg@lib)\n", mk)

    def test_only_compiled_sources_shape_object_paths(self):
        # srcs routinely list headers and .def files from other folders
        lib = make_cc_library(
            "lib", srcs=["pkg/src/a.c", "pkg/include/a.h", "pkg/defs/x.def"]
        )
        mk, stamp = _single(lib)
        self.assertIn("$(OBJ_DIR__pkg@lib)/a.c.o:", mk)
        self.assertNotIn("a.h", mk)
        self.assertNotIn("x.def", mk)
        self.assertIn(str(Path("pkg/src").resolve()), stamp)

    def test_c_and_cxx_sources_use_their_own_compiler(self):
        mk, _ = _single(make_cc_library("lib", srcs=["pkg/a.c", "pkg/a.cpp"]))
        c_rule = mk.split("$(OBJ_DIR__pkg@lib)/a.c.o:")[1].split("\n\n")[0]
        cxx_rule = mk.split("$(OBJ_DIR__pkg@lib)/a.cpp.o:")[1].split("\n\n")[0]
        self.assertIn("$(CC_COMPILE__pkg@lib)", c_rule)
        self.assertIn("$(CXX_COMPILE__pkg@lib)", cxx_rule)

    def test_compile_commands_compile_the_first_prerequisite(self):
        mk, _ = _single(make_cc_library("lib", srcs=["pkg/a.c"]))
        compile_line = next(l for l in mk.splitlines() if l.startswith("CC_COMPILE__"))
        self.assertIn(" = $(CC) ", compile_line)  # expanded per object at recipe time
        self.assertIn("-c $< -o $@", compile_line)

    def test_same_source_in_two_targets_gets_two_objects_with_own_flags(self):
        a = make_cc_library("a", srcs=["pkg/shared.c"], private_defines=["A"])
        b = make_cc_library("b", srcs=["pkg/shared.c"], private_defines=["B"])
        pkg = make_package("pkg", [a, b])
        ws = make_workspace([pkg])
        mk_a, _ = _render(a, pkg, ws)
        mk_b, _ = _render(b, pkg, ws)
        self.assertIn("OBJ_DIR__pkg@a := $(OBJS_ROOT)/pkg/a\n", mk_a)
        self.assertIn("OBJ_DIR__pkg@b := $(OBJS_ROOT)/pkg/b\n", mk_b)
        self.assertIn("$(OBJ_DIR__pkg@a)/shared.c.o:", mk_a)
        self.assertIn("$(OBJ_DIR__pkg@b)/shared.c.o:", mk_b)
        self.assertIn("DEFINES__pkg@a := A", mk_a)
        self.assertIn("DEFINES__pkg@b := B", mk_b)


class TestCompileStamp(unittest.TestCase):
    def _stamp(self, **kwargs):
        kwargs.setdefault("srcs", ["pkg/src/a.c"])
        _, stamp = _single(make_cc_library("lib", **kwargs))
        return stamp

    def test_stamp_lives_beside_the_targets_makefile(self):
        lib = make_cc_library("lib", srcs=["pkg/a.c"])
        pkg = make_package("a/b", [lib])
        tm = TargetMk(_config(), make_workspace([pkg]), Path("root"), pkg, lib)
        self.assertEqual(tm.stamp_path, Path("root/a/b/lib.compile"))
        self.assertEqual(tm.path, Path("root/a/b/lib.mk"))

    def test_changed_define_changes_the_stamp(self):
        self.assertNotEqual(
            self._stamp(private_defines=["X=1"]), self._stamp(private_defines=["X=2"])
        )

    def test_changed_flag_changes_the_stamp(self):
        self.assertNotEqual(self._stamp(c_flags=["-O0"]), self._stamp(c_flags=["-O2"]))

    def test_new_dependency_sandbox_changes_the_stamp(self):
        old = "pkg/../Out/.sandbox/pkg/repo/h1/include"
        new = "pkg/../Out/.sandbox/pkg/repo/h2/include"
        self.assertNotEqual(
            self._stamp(public_includes=[old]), self._stamp(public_includes=[new])
        )

    def test_moved_sources_change_the_stamp(self):
        self.assertNotEqual(
            self._stamp(srcs=["pkg/src/a.c"]), self._stamp(srcs=["pkg/source/a.c"])
        )

    def test_new_source_in_the_same_place_keeps_the_stamp(self):
        self.assertEqual(
            self._stamp(srcs=["pkg/src/a.c", "pkg/src/b.c"]),
            self._stamp(srcs=["pkg/src/a.c", "pkg/src/b.c", "pkg/src/c.c"]),
        )

    def test_every_object_depends_on_the_stamp(self):
        mk, _ = _single(make_cc_library("lib", srcs=["pkg/a.c", "pkg/b.cpp"]))
        self.assertIn(
            "COMPILE_STAMP__pkg@lib := $(BUILD_CONFIG_ROOT)/pkg/lib.compile\n", mk
        )
        rules = [l for l in mk.splitlines() if l.startswith("$(OBJ_DIR__pkg@lib)/")]
        self.assertEqual(len(rules), 2)
        for rule in rules:
            self.assertTrue(rule.endswith(" $(COMPILE_STAMP__pkg@lib)"))


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
        mk, _ = _render(self.lib, self.pkg, self.ws, self.config)
        self.assertIn("SWIFT_OBJ__pkg@sl := $(OBJS_ROOT)/pkg/sl/sl.swift.o\n", mk)
        self.assertIn("SWIFTMODULE__pkg@sl := $(OBJS_ROOT)/pkg/sl/sl.swiftmodule\n", mk)
        self.assertIn("SWIFTHEADER__pkg@sl := $(OBJS_ROOT)/pkg/sl/include/sl.h\n", mk)

    def test_swift_dependents_search_the_dependency_targets_directory(self):
        mk, _ = _render(self.app, self.pkg, self.ws, self.config)
        self.assertIn("SWIFT_MODULE_I__pkg@app := -I $(OBJS_ROOT)/pkg/sl\n", mk)
        self.assertIn("$(OBJS_ROOT)/pkg/sl/sl.swiftmodule", mk)

    def test_c_dependents_include_the_emitted_header(self):
        mk, _ = _render(self.cc, self.pkg, self.ws, self.config)
        self.assertIn("$(OBJS_ROOT)/pkg/sl/include", mk)
        self.assertIn("| $(OBJS_ROOT)/pkg/sl/include/sl.h", mk)

    def test_module_compile_depends_on_its_stamp(self):
        mk, stamp = _render(self.lib, self.pkg, self.ws, self.config)
        compile_rule = next(l for l in mk.splitlines() if l.startswith("$(SWIFT_OBJ"))
        self.assertIn("$(COMPILE_STAMP__pkg@sl)", compile_rule)
        # the module compiles whole, so its source list is part of the stamp
        self.assertIn("pkg/a.swift", stamp)


class TestMetalIntermediates(unittest.TestCase):
    def test_air_files_live_in_the_targets_intermediates_directory(self):
        shaders = MetalLibrary(
            name="shaders",
            workspace_root="pkg",
            srcs=["pkg/metal/a.metal", "pkg/metal/sub/b.metal"],
        )
        mk, stamp = _single(shaders, config=_config(platform="macos"))
        self.assertIn(
            "$(OBJS_ROOT)/pkg/shaders/a.metal.air: $(WORKSPACE_ROOT)/pkg/metal/a.metal "
            "$(COMPILE_STAMP__pkg@shaders)\n",
            mk,
        )
        self.assertIn("$(OBJS_ROOT)/pkg/shaders/sub/b.metal.air:", mk)
        self.assertIn("flags: -target air64-apple-macos", stamp)


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
