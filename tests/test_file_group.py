"""In-memory behavioral tests for file_group: strip_prefix -> (src, dst) resolution,
and how apple_application merges file_groups into structure-preserving resources."""

import io
from pathlib import Path

import pytest

from builderer.details.targets.file_group import FileGroup
from builderer.generators.make.target_mk import TargetMk
from builderer.generators.xcode.model import DstSubfolderSpec, PBXCopyFilesBuildPhase
from builderer.generators.xcode.model_builder import generate_xcode_project

from conftest import (
    make_apple_application,
    make_cc_binary,
    make_config,
    make_package,
    make_workspace,
)


def _file_group(name, *, srcs, strip_prefix="", workspace_root="pkg"):
    # srcs are given in their post-glob (package-prefixed) form, since these
    # in-memory tests do not run the workspace's globbing pass.
    return FileGroup(
        name=name, srcs=srcs, strip_prefix=strip_prefix, workspace_root=workspace_root
    )


# --- resource_destinations: strip_prefix -> (src, dst) ----------------------


def test_default_strip_prefix_keeps_full_package_relative_path():
    fg = _file_group("data", srcs=["pkg/assets/textures/oak.png"])
    assert fg.resource_destinations() == [
        ("pkg/assets/textures/oak.png", "assets/textures/oak.png")
    ]


def test_explicit_strip_prefix_drops_prefix_and_preserves_subtree():
    fg = _file_group(
        "data",
        strip_prefix="assets",
        srcs=["pkg/assets/textures/oak.png", "pkg/assets/app.icon"],
    )
    assert fg.resource_destinations() == [
        ("pkg/assets/textures/oak.png", "textures/oak.png"),
        ("pkg/assets/app.icon", "app.icon"),  # directly under prefix -> flat
    ]


def test_strip_prefix_matching_normalizes_dotdot_and_trailing_slash():
    # Mirrors a {pkg:generate}/... reference resolving outside the package: the
    # match must use path normalization, never a naive string prefix.
    fg = _file_group(
        "gen",
        strip_prefix="../sandbox/gen/",
        srcs=["pkg/../sandbox/gen/a.icon", "pkg/../sandbox/gen/sub/b.icon"],
    )
    assert fg.resource_destinations() == [
        ("pkg/../sandbox/gen/a.icon", "a.icon"),
        ("pkg/../sandbox/gen/sub/b.icon", "sub/b.icon"),
    ]


def test_source_outside_strip_prefix_errors():
    fg = _file_group("data", strip_prefix="assets", srcs=["pkg/other/x.bin"])
    with pytest.raises(ValueError, match="not under"):
        fg.resource_destinations()


# --- apple_application: merge + collision across file_groups ----------------


def _app(resources, groups):
    binary = make_cc_binary("bin", srcs=["pkg/main.cpp"])
    app = make_apple_application(
        "App.app",
        binary=":bin",
        info_plist={"CFBundleIdentifier": "x", "CFBundleExecutable": "bin"},
        resources=resources,
    )
    pkg = make_package("pkg", [binary, app, *groups])
    return app, pkg, make_workspace([pkg])


def test_resolve_resources_merges_groups_sorted_by_destination():
    tex = _file_group(
        "tex", strip_prefix="assets", srcs=["pkg/assets/textures/oak.png"]
    )
    icons = _file_group("icons", strip_prefix="res", srcs=["pkg/res/app.icon"])
    app, pkg, ws = _app([":tex", ":icons"], [tex, icons])
    assert app.resolve_resources(ws, pkg) == [
        ("pkg/res/app.icon", "app.icon"),
        ("pkg/assets/textures/oak.png", "textures/oak.png"),
    ]


def test_resolve_resources_errors_on_destination_collision():
    a = _file_group("a", strip_prefix="d1", srcs=["pkg/d1/config.json"])
    b = _file_group("b", strip_prefix="d2", srcs=["pkg/d2/config.json"])
    app, pkg, ws = _app([":a", ":b"], [a, b])
    with pytest.raises(ValueError, match="collision"):
        app.resolve_resources(ws, pkg)


def test_resolve_resources_rejects_non_file_group_label():
    app, pkg, ws = _app([":bin"], [])  # the binary is not a file_group
    with pytest.raises(ValueError, match="must reference a file_group"):
        app.resolve_resources(ws, pkg)


# --- make generator: structure-preserving copies ----------------------------


def _makefile(app, pkg, ws):
    config = make_config(
        platform="macos",
        toolchain="clang",
        buildtool="make",
        architecture="arm64",
        build_config="debug",
        build_root="Out/build/macos",
    )
    tm = TargetMk(config, ws, Path("Out/build/macos"), pkg, app)
    buf = io.StringIO()
    tm._write_makefile(buf)
    return buf.getvalue()


def test_make_preserves_subdirectories_and_flattens_root_files():
    tex = _file_group(
        "tex", strip_prefix="assets", srcs=["pkg/assets/textures/wood/oak.texture"]
    )
    icons = _file_group("icons", strip_prefix="res", srcs=["pkg/res/app.icon"])
    app, pkg, ws = _app([":tex", ":icons"], [tex, icons])
    mk = _makefile(app, pkg, ws)
    # nested file: its subdirectory is created and the file lands under it
    assert "$(MKDIR) $@/Contents/Resources/textures/wood" in mk
    assert (
        "$(CP) $(WORKSPACE_ROOT)/pkg/assets/textures/wood/oak.texture "
        "$@/Contents/Resources/textures/wood/oak.texture" in mk
    )
    # file directly under its strip_prefix lands flat at the resources root
    assert (
        "$(CP) $(WORKSPACE_ROOT)/pkg/res/app.icon $@/Contents/Resources/app.icon" in mk
    )
    # each resource is a prerequisite, so editing it triggers a re-copy
    assert "$(WORKSPACE_ROOT)/pkg/assets/textures/wood/oak.texture" in mk


# --- xcode generator: per-subdir Copy Files phase actually wires the file ----


def test_xcode_wires_resource_into_a_copy_files_phase_for_its_subdirectory():
    tex = _file_group(
        "tex", strip_prefix="assets", srcs=["pkg/assets/textures/wood/oak.texture"]
    )
    app, pkg, ws = _app([":tex"], [tex])
    config = make_config(
        buildtool="xcode",
        toolchain="clang",
        platform="macos",
        build_root="Out/build/macos.xcodeproj",
        architecture=["arm64"],
        build_config=["debug"],
    )
    proj = generate_xcode_project(config, ws)

    file_ref = next(
        f
        for f in proj.fileReferences
        if f.path.endswith("assets/textures/wood/oak.texture")
    )
    build_file = next(bf for bf in proj.buildFiles if bf.fileRef.id == file_ref.id)
    phase = next(
        p
        for p in proj.buildPhases
        if isinstance(p, PBXCopyFilesBuildPhase)
        and p.dstSubfolderSpec == DstSubfolderSpec.RESOURCES
        and p.dstPath == "textures/wood"
    )
    # the build file is a member of that phase -- the wiring Xcode needs to copy it
    # (a dangling file ref / empty phase would slip past a weaker existence check).
    assert build_file.id in {ref.id for ref in phase.files}
