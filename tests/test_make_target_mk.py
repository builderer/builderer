"""Behavioral tests for the Makefile emitter (rendered to a StringIO, no disk)."""

import io
from pathlib import Path

from builderer.generators.make.target_mk import TargetMk

from conftest import (
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


def test_only_compilable_extensions_enter_srcs():
    lib = make_cc_library("lib", srcs=["pkg/a.cpp", "pkg/notcompiled.h"])
    mk = _single(lib)
    assert "a.cpp" in mk
    assert "notcompiled.h" not in mk  # headers are filtered out of SRCS


def test_arch_and_compiler_flags_are_emitted():
    lib = make_cc_library("lib", srcs=["pkg/a.cpp"], cxx_flags=["-O2", "-Wall"])
    mk = _single(lib)
    assert "-m64 -march=x86-64" in mk  # PLATFORM_ARCH_FLAGS[linux][x86-64]
    assert "-O2 -Wall" in mk


def test_library_emits_archive_rule_and_phony_target():
    mk = _single(make_cc_library("lib", srcs=["pkg/a.cpp"]))
    assert "$(AR) rcS" in mk
    assert "pkg@lib:" in mk


def test_binary_with_library_dependency_links_and_inherits_settings():
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
    assert "$(CCLD)" in mk  # binaries are linked
    assert "libmylib.a" in mk  # against the dependency's archive
    assert "APP" in mk and "LIB_API" in mk  # own + inherited public defines
    assert "pkg/inc" in mk  # inherited public include


def test_apple_application_makefile_packages_bundle_with_plist():
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
    assert "Packaging" in mk
    assert "Contents/MacOS/MyApp" in mk  # CFBundleExecutable drives the binary name
    assert "<key>CFBundleName</key>" in mk  # Info.plist echoed line-by-line
    assert "PkgInfo" in mk


def test_header_only_dependency_propagates_but_is_not_linked():
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
    assert "HDR_ONLY" in mk
    assert "pkg/hdrinc" in mk
    assert "libhdronly.a" not in mk  # nothing to archive/link for a header-only lib
