"""Behavioral tests for the MSBuild .vcxproj emitter.

These render a real target into an in-memory xml.dom Document (no disk) and query
the DOM, so they exercise the flag-mapping, defaults, dependency propagation and
file classification code paths -- not just the mapping tables.
"""

from xml.dom.minidom import Document

from builderer.generators.msbuild.project import MsBuildProject, unique_list
from builderer.generators.msbuild.version import VS_VERSIONS

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


def _includes(doc, tag):
    return [
        e.getAttribute("Include")
        for e in doc.getElementsByTagName(tag)
        if e.getAttribute("Include")
    ]


def _render(target, package, workspace, version=VS2022):
    proj = MsBuildProject(make_config(), workspace, package, target, version)
    doc = Document()
    proj._append_project(doc)
    return doc


def _render_single(target):
    pkg = make_package("pkg", [target])
    return _render(target, pkg, make_workspace([pkg]))


def test_compile_flags_become_settings_and_unknown_flags_pass_through():
    app = make_cc_binary(
        "app",
        srcs=["pkg/main.cpp"],
        cxx_flags=["/Od", "/std:c++17", "/MD", "/customflag"],
    )
    doc = _render_single(app)
    assert "Disabled" in _texts(doc, "Optimization")
    assert "stdcpp17" in _texts(doc, "LanguageStandard")
    # /MD must resolve to the release DLL runtime (regression for the duplicate-key bug)
    assert "MultiThreadedDLL" in _texts(doc, "RuntimeLibrary")
    # unknown compiler flags are passed through verbatim
    assert "/customflag" in _texts(doc, "AdditionalOptions")


def test_globals_enable_parallel_build_settings():
    doc = _render_single(make_cc_binary("app", srcs=["pkg/main.cpp"]))
    assert "true" in _texts(doc, "MultiProcessorCompilation")
    assert "true" in _texts(doc, "EnforceProcessCountAcrossBuilds")
    assert "true" in _texts(doc, "UseMultiToolTask")
    assert _texts(doc, "ProjectGuid")  # a project GUID is emitted


def test_link_flags_become_settings_and_unknown_pass_through():
    app = make_cc_binary(
        "app",
        srcs=["pkg/main.cpp"],
        link_flags=["/DEBUG", "/SUBSYSTEM:CONSOLE", "/WEIRD"],
    )
    doc = _render_single(app)
    assert "true" in _texts(doc, "GenerateDebugInformation")
    assert "Console" in _texts(doc, "SubSystem")
    assert any("/WEIRD" in a for a in _texts(doc, "AdditionalOptions"))


def test_configuration_type_reflects_target_kind():
    assert "Application" in _texts(
        _render_single(make_cc_binary("app", srcs=["pkg/main.cpp"])),
        "ConfigurationType",
    )
    assert "StaticLibrary" in _texts(
        _render_single(make_cc_library("lib", srcs=["pkg/a.cpp"])), "ConfigurationType"
    )
    # a header-only library has an empty ConfigurationType
    assert "" in _texts(
        _render_single(make_cc_library("hdronly", hdrs=["pkg/a.h"])),
        "ConfigurationType",
    )


def test_source_and_header_files_get_correct_item_types():
    lib = make_cc_library(
        "lib", srcs=["pkg/a.cpp"], hdrs=["pkg/a.h", "pkg/Eigen/Dense"]
    )
    doc = _render_single(lib)
    compiles = _includes(doc, "ClCompile")
    includes = _includes(doc, "ClInclude")
    assert any(p.endswith("a.cpp") for p in compiles)
    assert any(p.endswith("a.h") for p in includes)
    # extension-less std-style header (Eigen) classifies as a header, not a source
    assert any(p.endswith("Dense") for p in includes)


def test_library_dependency_propagates_defines_includes_and_reference():
    lib = make_cc_library(
        "mylib",
        srcs=["pkg/lib.cpp"],
        public_defines=["LIB_API"],
        public_includes=["pkg/libinc"],
    )
    app = make_cc_binary(
        "app", srcs=["pkg/main.cpp"], private_defines=["APP"], deps=[":mylib"]
    )
    pkg = make_package("pkg", [lib, app])
    doc = _render(app, pkg, make_workspace([pkg]))
    defines = ";".join(_texts(doc, "PreprocessorDefinitions"))
    assert (
        "APP" in defines and "LIB_API" in defines
    )  # own + dependency's public defines
    assert "libinc" in ";".join(_texts(doc, "AdditionalIncludeDirectories"))
    assert any("mylib.vcxproj" in r for r in _includes(doc, "ProjectReference"))


def test_unique_list_dedupes_preserving_order():
    assert unique_list([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_header_only_dependency_still_propagates_defines_and_includes():
    # a header-only library (no sources) must still contribute its public
    # includes/defines to a dependent's compile settings
    hdr = make_cc_library(
        "hdronly",
        hdrs=["pkg/h.hpp"],
        public_includes=["pkg/hdrinc"],
        public_defines=["HDR_ONLY"],
    )
    app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":hdronly"])
    pkg = make_package("pkg", [hdr, app])
    doc = _render(app, pkg, make_workspace([pkg]))
    assert "HDR_ONLY" in ";".join(_texts(doc, "PreprocessorDefinitions"))
    assert "hdrinc" in ";".join(_texts(doc, "AdditionalIncludeDirectories"))


def test_private_settings_do_not_leak_to_dependents():
    # public_* flow to consumers; private_* must stay internal to the library
    lib = make_cc_library(
        "lib",
        srcs=["pkg/l.cpp"],
        public_defines=["PUB"],
        private_defines=["PRIV"],
        public_includes=["pkg/pub"],
        private_includes=["pkg/priv"],
    )
    app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":lib"])
    pkg = make_package("pkg", [lib, app])
    doc = _render(app, pkg, make_workspace([pkg]))
    defines = ";".join(_texts(doc, "PreprocessorDefinitions"))
    includes = ";".join(_texts(doc, "AdditionalIncludeDirectories"))
    assert "PUB" in defines and "PRIV" not in defines
    assert "pub" in includes and "priv" not in includes


def test_visual_studio_version_selects_platform_toolset():
    # documented: MsBuildGenerator[2026] -> v145, default [2022] -> v143
    app = make_cc_binary("app", srcs=["pkg/main.cpp"])
    pkg = make_package("pkg", [app])
    doc_2026 = _render(app, pkg, make_workspace([pkg]), version=VS_VERSIONS[2026])
    assert "v145" in _texts(doc_2026, "PlatformToolset")
    doc_2022 = _render(app, pkg, make_workspace([pkg]))
    assert "v143" in _texts(doc_2022, "PlatformToolset")
