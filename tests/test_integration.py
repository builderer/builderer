"""Integration tests: how the subsystems plug together.

The other test modules cover each piece (conditionals, the dependency graph,
individual emitters) in isolation. These exercise the *seams* between them --
conditional resolution flowing into a generator, multi-config fan-out, and
cross-file reference consistency between the generated .sln and .vcxproj files --
using programmatically-built workspaces (no build-file parsing; that path is
covered by the examples build).
"""

import io
from pathlib import Path
from xml.dom.minidom import Document

import pytest

from builderer import Condition, Optional
from builderer.details.workspace import target_full_name
from builderer.generators.make.target_mk import TargetMk
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.solution import MsBuildSolution
from builderer.generators.msbuild.version import VS_VERSIONS
from builderer.generators.xcode.model_builder import generate_xcode_project
from builderer.generators.xcode.validator import validate_references

from conftest import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_package,
    make_workspace,
)

VS2022 = VS_VERSIONS[2022]


def _texts(doc, tag):
    return [
        e.firstChild.nodeValue if e.firstChild else ""
        for e in doc.getElementsByTagName(tag)
    ]


def _project_doc(config, target, package, workspace):
    proj = MsBuildProject(config, workspace, package, target, VS2022)
    doc = Document()
    proj._append_project(doc)
    return proj, doc


def test_conditional_flags_resolve_against_active_config_during_generation():
    # I-1: the conditional system and the generator must compose -- a Condition-gated
    # flag reaches the emitted project only for the matching config
    app = make_cc_binary(
        "app",
        srcs=["pkg/m.cpp"],
        cxx_flags=[
            Optional(Condition(toolchain="msvc"), "/Od"),
            Optional(Condition(toolchain="gcc"), "-O0"),
        ],
    )
    pkg = make_package("pkg", [app])
    cfg = make_config(toolchain="msvc", architecture="x64", build_config="debug")
    _, doc = _project_doc(cfg, app, pkg, make_workspace([pkg]))
    assert "Disabled" in _texts(doc, "Optimization")  # msvc /Od -> Optimization
    # the non-matching gcc flag is dropped entirely (not passed through as unknown)
    assert all("-O0" not in a for a in _texts(doc, "AdditionalOptions"))


def test_multi_arch_multi_config_fans_out_coherently():
    # I-2: a config with N architectures x M build_configs produces the full cartesian
    # product, and the .vcxproj and .sln agree on it
    app = make_cc_binary("app", srcs=["pkg/m.cpp"])
    pkg = make_package("pkg", [app])
    cfg = make_config(architecture=["x64", "arm64"], build_config=["debug", "release"])
    ws = make_workspace([pkg])
    _, doc = _project_doc(cfg, app, pkg, ws)
    project_configs = {
        e.getAttribute("Include")
        for e in doc.getElementsByTagName("ProjectConfiguration")
    }
    expected = {"debug|x64", "release|x64", "debug|arm64", "release|arm64"}
    assert project_configs == expected
    projects = {target_full_name(pkg, app): MsBuildProject(cfg, ws, pkg, app, VS2022)}
    buf = io.StringIO()
    MsBuildSolution(cfg, ws, projects, VS2022)._write_solution(buf)
    sln = buf.getvalue()
    for combo in expected:
        assert f"{combo} = {combo}" in sln  # solution-configuration matrix matches


def test_solution_and_projects_agree_on_dependency_guids_and_paths():
    # I-3: cross-file consistency -- the .sln records the dependency by the
    # dependency project's actual GUID, and the dependent .vcxproj references the
    # dependency's actual project file
    lib = make_cc_library("mylib", srcs=["pkg/l.cpp"])
    app = make_cc_binary("app", srcs=["pkg/m.cpp"], deps=[":mylib"])
    pkg = make_package("pkg", [lib, app])
    cfg = make_config(architecture=["x64"], build_config=["debug"])
    ws = make_workspace([pkg])
    projects = {
        target_full_name(pkg, t): MsBuildProject(cfg, ws, pkg, t, VS2022)
        for t in (lib, app)
    }
    buf = io.StringIO()
    MsBuildSolution(cfg, ws, projects, VS2022)._write_solution(buf)
    sln = buf.getvalue()
    lib_guid = projects[target_full_name(pkg, lib)].project_guid
    # the "{guid} = {guid}" form only appears in the ProjectDependencies section
    assert f"{lib_guid} = {lib_guid}" in sln
    _, app_doc = _project_doc(cfg, app, pkg, ws)
    refs = [
        e.getAttribute("Include")
        for e in app_doc.getElementsByTagName("ProjectReference")
        if e.getAttribute("Include")
    ]
    assert any("mylib.vcxproj" in r for r in refs)


def test_makefile_links_dependencies_in_dependency_order():
    # I-4: the dependency graph order must reach the link line -- a dependent's
    # archive precedes its dependency's (left-to-right static link resolution).
    # app -> high -> low
    low = make_cc_library("low", srcs=["pkg/low.cpp"])
    high = make_cc_library("high", srcs=["pkg/high.cpp"], deps=[":low"])
    app = make_cc_binary("app", srcs=["pkg/m.cpp"], deps=[":high"])
    pkg = make_package("pkg", [low, high, app])
    cfg = make_config(
        platform="linux",
        toolchain="gcc",
        buildtool="make",
        architecture="x86-64",
        build_config="debug",
        build_root="Out/build/linux",
    )
    buf = io.StringIO()
    TargetMk(
        cfg, make_workspace([pkg]), Path("Out/build/linux"), pkg, app
    )._write_makefile(buf)
    link_line = next(
        line
        for line in buf.getvalue().splitlines()
        if "libhigh.a" in line and "liblow.a" in line
    )
    assert link_line.index("libhigh.a") < link_line.index("liblow.a")


# --- Combinatorial sweeps -----------------------------------------------------
# The examples build only samples a few (platform, toolchain) points and proves
# they compile. These sweep every supported configuration and prove the
# generators still produce coherent, internally-consistent output -- catching a
# break in, say, the macos/arm64 or emscripten/wasm32 path that the examples
# build would miss.


def _lib_and_binary_workspace():
    lib = make_cc_library("mylib", srcs=["pkg/l.cpp"])
    app = make_cc_binary("app", srcs=["pkg/m.cpp"], deps=[":mylib"])
    pkg = make_package("pkg", [lib, app])
    return make_workspace([pkg]), pkg, app


@pytest.mark.parametrize(
    "platform,toolchain,arch",
    [
        ("linux", "gcc", "x86-64"),
        ("linux", "gcc", "i386"),
        ("macos", "clang", "arm64"),
        ("macos", "clang", "x86_64"),
        ("emscripten", "emscripten", "wasm32"),
    ],
)
def test_make_generator_is_coherent_across_supported_configs(platform, toolchain, arch):
    ws, pkg, app = _lib_and_binary_workspace()
    cfg = make_config(
        platform=platform,
        toolchain=toolchain,
        buildtool="make",
        architecture=arch,
        build_config="debug",
        build_root="b",
    )
    buf = io.StringIO()
    TargetMk(cfg, ws, Path("b"), pkg, app)._write_makefile(buf)
    mk = buf.getvalue()
    assert "$(CCLD)" in mk  # the binary link rule is emitted
    assert "libmylib.a" in mk  # ...and links the dependency's archive


@pytest.mark.parametrize("arch", ["x64", "arm64"])
def test_msbuild_generator_is_coherent_across_architectures(arch):
    ws, pkg, app = _lib_and_binary_workspace()
    cfg = make_config(
        platform="windows", toolchain="msvc", architecture=arch, build_config="debug"
    )
    _, doc = _project_doc(cfg, app, pkg, ws)
    configs = {
        e.getAttribute("Include")
        for e in doc.getElementsByTagName("ProjectConfiguration")
    }
    assert configs == {f"debug|{arch}"}
    refs = [
        e.getAttribute("Include")
        for e in doc.getElementsByTagName("ProjectReference")
        if e.getAttribute("Include")
    ]
    assert any("mylib.vcxproj" in r for r in refs)


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_xcode_generator_is_coherent_across_architectures(arch):
    ws, pkg, app = _lib_and_binary_workspace()
    cfg = make_config(
        buildtool="xcode",
        toolchain="clang",
        platform="macos",
        build_root="b.xcodeproj",
        architecture=[arch],
        build_config=["debug"],
    )
    proj = generate_xcode_project(cfg, ws)
    assert validate_references(proj) == []  # model stays internally consistent
    assert {t.name for t in proj.nativeTargets} == {"pkg:mylib", "pkg:app"}
