"""Tests for the Xcode model builder + formatter.

Builds a real project model from an in-memory workspace and asserts it is
internally consistent (the validator finds no dangling references) and that the
formatter emits a pbxproj skeleton. This exercises a large swath of
model_builder.py / formatter.py without touching disk or running Xcode.
"""

from builderer.generators.xcode.model import ProductType
from builderer.generators.xcode.model_builder import generate_xcode_project
from builderer.generators.xcode.formatter import format_xcode_project
from builderer.generators.xcode.validator import (
    validate_references,
    validate_output_paths,
)

from conftest import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_package,
    make_workspace,
)


def _project():
    lib = make_cc_library(
        "mylib",
        srcs=["pkg/lib.cpp"],
        hdrs=["pkg/lib.h"],
        public_includes=["pkg/inc"],
        public_defines=["LIB=1"],
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


def test_generated_model_has_no_dangling_references():
    proj = _project()
    assert validate_references(proj) == []
    validate_output_paths(proj)  # must not raise


def test_model_has_a_native_target_per_build_target():
    by_name = {t.name: t.productType for t in _project().nativeTargets}
    assert by_name["pkg:mylib"] == ProductType.STATIC_LIBRARY
    assert by_name["pkg:app"] == ProductType.TOOL


def test_model_includes_source_file_references():
    paths = {r.path for r in _project().fileReferences}
    assert any(p.endswith("lib.cpp") for p in paths)
    assert any(p.endswith("main.cpp") for p in paths)


def test_formatter_emits_pbxproj_skeleton():
    text = format_xcode_project(_project())
    assert text.startswith("// !$*UTF8*$!")
    assert "PBXNativeTarget" in text
    assert "rootObject" in text
    assert "pkg:app" in text
