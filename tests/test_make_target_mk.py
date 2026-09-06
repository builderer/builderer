"""Behavioral tests for the Makefile emitter (rendered to a StringIO, no disk)."""

import io
import unittest
from pathlib import Path

from builderer.generators.make.target_mk import TargetMk

from factories import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_apple_application,
    make_package,
    make_workspace,
)


def _make_config(**over):
    return make_config(
        platform="linux",
        toolchain="gcc",
        buildtool="make",
        architecture="x86-64",
        build_config="debug",
        build_root="Out/build/linux",
        **over,
    )


def _makefile(target, package, workspace, config):
    tm = TargetMk(config, workspace, Path(config.build_root), package, target)
    buf = io.StringIO()
    tm._write_makefile(buf)
    return buf.getvalue()


def _single(target, config=None):
    pkg = make_package("pkg", [target])
    return _makefile(target, pkg, make_workspace([pkg]), config or _make_config())


class TestTargetMk(unittest.TestCase):
    def test_only_compilable_extensions_enter_srcs(self):
        lib = make_cc_library("lib", srcs=["pkg/a.cpp", "pkg/notcompiled.h"])
        mk = _single(lib)
        self.assertIn("a.cpp", mk)
        self.assertNotIn("notcompiled.h", mk)  # headers are filtered out of SRCS

    def test_arch_and_compiler_flags_are_emitted(self):
        lib = make_cc_library("lib", srcs=["pkg/a.cpp"], cxx_flags=["-O2", "-Wall"])
        mk = _single(lib)
        self.assertIn("-m64 -march=x86-64", mk)  # PLATFORM_ARCH_FLAGS[linux][x86-64]
        self.assertIn("-O2 -Wall", mk)

    def test_library_emits_archive_rule_and_phony_target(self):
        mk = _single(make_cc_library("lib", srcs=["pkg/a.cpp"]))
        self.assertIn("$(AR) rcS", mk)
        self.assertIn("pkg@lib:", mk)

    def test_binary_with_library_dependency_links_and_inherits_settings(self):
        lib = make_cc_library(
            "mylib",
            srcs=["pkg/lib.cpp"],
            public_defines=["LIB_API"],
            public_includes=["pkg/inc"],
        )
        app = make_cc_binary(
            "app", srcs=["pkg/main.cpp"], private_defines=["APP"], deps=[":mylib"]
        )
        pkg = make_package("pkg", [lib, app])
        mk = _makefile(app, pkg, make_workspace([pkg]), _make_config())
        self.assertIn("$(CCLD)", mk)  # binaries are linked
        self.assertIn("libmylib.a", mk)  # against the dependency's archive
        # own + inherited public defines
        self.assertIn("APP", mk)
        self.assertIn("LIB_API", mk)
        self.assertIn("pkg/inc", mk)  # inherited public include

    def test_apple_application_makefile_packages_bundle_with_plist(self):
        app_bin = make_cc_binary("appbin", srcs=["pkg/main.cpp"])
        bundle = make_apple_application(
            "MyApp",
            binary=":appbin",
            info_plist={"CFBundleName": "MyApp", "CFBundleExecutable": "MyApp"},
        )
        pkg = make_package("pkg", [app_bin, bundle])
        ws = make_workspace([pkg])
        config = make_config(
            platform="macos",
            toolchain="clang",
            buildtool="make",
            architecture="arm64",
            build_config="debug",
            build_root="Out/build/macos",
        )
        mk = _makefile(bundle, pkg, ws, config)
        self.assertIn("Packaging", mk)
        # CFBundleExecutable drives the binary name
        self.assertIn("Contents/MacOS/MyApp", mk)
        # Info.plist echoed line-by-line
        self.assertIn("<key>CFBundleName</key>", mk)
        self.assertIn("PkgInfo", mk)

    def test_header_only_dependency_propagates_but_is_not_linked(self):
        # a header-only library contributes its public includes/defines to dependents
        # but produces no archive, so it must NOT appear on the link line
        hdr = make_cc_library(
            "hdronly",
            hdrs=["pkg/h.hpp"],
            public_includes=["pkg/hdrinc"],
            public_defines=["HDR_ONLY"],
        )
        app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":hdronly"])
        pkg = make_package("pkg", [hdr, app])
        mk = _makefile(app, pkg, make_workspace([pkg]), _make_config())
        self.assertIn("HDR_ONLY", mk)
        self.assertIn("pkg/hdrinc", mk)
        # nothing to archive/link for a header-only lib
        self.assertNotIn("libhdronly.a", mk)
