"""Behavioral tests for the MSBuild .vcxproj emitter.

These render a real target into an in-memory xml.dom Document (no disk) and query
the DOM, so they exercise the flag-mapping, defaults, dependency propagation and
file classification code paths -- not just the mapping tables.
"""

import unittest
from xml.dom.minidom import Document

from builderer import Case, Condition, Switch
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.version import VS_VERSIONS

from factories import (
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


def _output_names(doc):
    # (Condition, TargetName, TargetExt) of each output naming group
    return [
        (
            xname.parentNode.getAttribute("Condition"),
            _texts(xname.parentNode, "TargetName")[0],
            _texts(xname.parentNode, "TargetExt")[0],
        )
        for xname in doc.getElementsByTagName("TargetName")
    ]


def _render(target, package, workspace, version=VS2022, config=None):
    proj = MsBuildProject(config or make_config(), workspace, package, target, version)
    doc = Document()
    proj._append_project(doc)
    return doc


def _render_single(target):
    pkg = make_package("pkg", [target])
    return _render(target, pkg, make_workspace([pkg]))


class TestProjectSettings(unittest.TestCase):
    def test_compile_flags_become_settings_and_unknown_flags_pass_through(self):
        app = make_cc_binary(
            "app",
            srcs=["pkg/main.cpp"],
            cxx_flags=["/Od", "/std:c++17", "/MD", "/customflag"],
        )
        doc = _render_single(app)
        self.assertIn("Disabled", _texts(doc, "Optimization"))
        self.assertIn("stdcpp17", _texts(doc, "LanguageStandard"))
        # /MD must resolve to the release DLL runtime (regression for the
        # duplicate-key bug)
        self.assertIn("MultiThreadedDLL", _texts(doc, "RuntimeLibrary"))
        # unknown compiler flags are passed through verbatim
        self.assertIn("/customflag", _texts(doc, "AdditionalOptions"))

    def test_cxx_standard_flags_map_to_language_standard(self):
        expected = {
            "/std:c++20": "stdcpp20",
            "/std:c++23": "stdcpp23",
            "/std:c++23preview": "stdcpp23",
            "/std:c++latest": "stdcpplatest",
        }
        for flag, value in expected.items():
            with self.subTest(flag=flag):
                app = make_cc_binary("app", srcs=["pkg/main.cpp"], cxx_flags=[flag])
                doc = _render_single(app)
                self.assertEqual(_texts(doc, "LanguageStandard"), [value])
                self.assertTrue(
                    all(flag not in a for a in _texts(doc, "AdditionalOptions"))
                )

    def test_globals_enable_parallel_build_settings(self):
        doc = _render_single(make_cc_binary("app", srcs=["pkg/main.cpp"]))
        self.assertIn("true", _texts(doc, "MultiProcessorCompilation"))
        self.assertIn("true", _texts(doc, "EnforceProcessCountAcrossBuilds"))
        self.assertIn("true", _texts(doc, "UseMultiToolTask"))
        self.assertTrue(_texts(doc, "ProjectGuid"))  # a project GUID is emitted

    def test_link_flags_become_settings_and_unknown_pass_through(self):
        app = make_cc_binary(
            "app",
            srcs=["pkg/main.cpp"],
            link_flags=["/DEBUG", "/SUBSYSTEM:CONSOLE", "/WEIRD"],
        )
        doc = _render_single(app)
        self.assertIn("true", _texts(doc, "GenerateDebugInformation"))
        self.assertIn("Console", _texts(doc, "SubSystem"))
        self.assertTrue(any("/WEIRD" in a for a in _texts(doc, "AdditionalOptions")))

    def test_configuration_type_reflects_target_kind(self):
        self.assertIn(
            "Application",
            _texts(
                _render_single(make_cc_binary("app", srcs=["pkg/main.cpp"])),
                "ConfigurationType",
            ),
        )
        self.assertIn(
            "StaticLibrary",
            _texts(
                _render_single(make_cc_library("lib", srcs=["pkg/a.cpp"])),
                "ConfigurationType",
            ),
        )
        # a header-only library has an empty ConfigurationType
        self.assertIn(
            "",
            _texts(
                _render_single(make_cc_library("hdronly", hdrs=["pkg/a.h"])),
                "ConfigurationType",
            ),
        )

    def test_source_and_header_files_get_correct_item_types(self):
        lib = make_cc_library(
            "lib", srcs=["pkg/a.cpp"], hdrs=["pkg/a.h", "pkg/Eigen/Dense"]
        )
        doc = _render_single(lib)
        compiles = _includes(doc, "ClCompile")
        includes = _includes(doc, "ClInclude")
        self.assertTrue(any(p.endswith("a.cpp") for p in compiles))
        self.assertTrue(any(p.endswith("a.h") for p in includes))
        # extension-less std-style header (Eigen) classifies as a header, not a source
        self.assertTrue(any(p.endswith("Dense") for p in includes))

    def test_visual_studio_version_selects_platform_toolset(self):
        # documented: MsBuildGenerator[2026] -> v145, default [2022] -> v143
        app = make_cc_binary("app", srcs=["pkg/main.cpp"])
        pkg = make_package("pkg", [app])
        doc_2026 = _render(app, pkg, make_workspace([pkg]), version=VS_VERSIONS[2026])
        self.assertIn("v145", _texts(doc_2026, "PlatformToolset"))
        doc_2022 = _render(app, pkg, make_workspace([pkg]))
        self.assertIn("v143", _texts(doc_2022, "PlatformToolset"))


class TestDependencyPropagation(unittest.TestCase):
    def test_library_dependency_propagates_defines_includes_and_reference(self):
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
        # own + dependency's public defines
        self.assertIn("APP", defines)
        self.assertIn("LIB_API", defines)
        self.assertIn("libinc", ";".join(_texts(doc, "AdditionalIncludeDirectories")))
        self.assertTrue(
            any("mylib.vcxproj" in r for r in _includes(doc, "ProjectReference"))
        )

    def test_header_only_dependency_still_propagates_defines_and_includes(self):
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
        self.assertIn("HDR_ONLY", ";".join(_texts(doc, "PreprocessorDefinitions")))
        self.assertIn("hdrinc", ";".join(_texts(doc, "AdditionalIncludeDirectories")))

    def test_private_settings_do_not_leak_to_dependents(self):
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
        self.assertIn("PUB", defines)
        self.assertNotIn("PRIV", defines)
        self.assertIn("pub", includes)
        self.assertNotIn("priv", includes)

    def test_binary_references_full_transitive_lib_closure(self):
        # Regression: app -> mid(real) -> hdr(header-only) -> deep(real).
        # deep must be a direct ProjectReference of the binary; MSBuild's transitive
        # LinkLibraryDependencies recursion could not carry deep's .lib through the
        # .lib-less header-only hdr, dropping it from the link line. Flattening onto
        # the binary fixes it.
        deep = make_cc_library("deep", srcs=["pkg/deep.cpp"])
        hdr = make_cc_library("hdr", hdrs=["pkg/hdr.h"], deps=[":deep"])
        mid = make_cc_library("mid", srcs=["pkg/mid.cpp"], deps=[":hdr"])
        app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":mid"])
        pkg = make_package("pkg", [deep, hdr, mid, app])
        refs = _includes(_render(app, pkg, make_workspace([pkg])), "ProjectReference")
        self.assertTrue(any("deep.vcxproj" in r for r in refs))
        self.assertTrue(any("mid.vcxproj" in r for r in refs))
        self.assertTrue(any("hdr.vcxproj" in r for r in refs))

    def test_library_emits_no_project_references(self):
        # lib->lib edges are gone: a library references nothing (it links nothing; its
        # deps' headers reach it via the separate include walk, not via project
        # references).
        deep = make_cc_library("deep", srcs=["pkg/deep.cpp"])
        mid = make_cc_library("mid", srcs=["pkg/mid.cpp"], deps=[":deep"])
        pkg = make_package("pkg", [deep, mid])
        refs = _includes(_render(mid, pkg, make_workspace([pkg])), "ProjectReference")
        self.assertEqual(refs, [])

    def test_library_still_gets_transitive_includes_without_references(self):
        # Removing lib->lib edges must NOT break include/define propagation into
        # libraries.
        deep = make_cc_library(
            "deep",
            srcs=["pkg/deep.cpp"],
            public_includes=["pkg/deepinc"],
            public_defines=["DEEP"],
        )
        mid = make_cc_library("mid", srcs=["pkg/mid.cpp"], deps=[":deep"])
        pkg = make_package("pkg", [deep, mid])
        doc = _render(mid, pkg, make_workspace([pkg]))
        self.assertIn("deepinc", ";".join(_texts(doc, "AdditionalIncludeDirectories")))
        self.assertIn("DEEP", ";".join(_texts(doc, "PreprocessorDefinitions")))


DEBUG_X64 = "'$(Configuration)|$(Platform)'=='debug|x64'"
RELEASE_X64 = "'$(Configuration)|$(Platform)'=='release|x64'"


class TestOutputNaming(unittest.TestCase):
    def test_default_output_name_is_target_name(self):
        for target, name, ext in [
            (make_cc_binary("app", srcs=["pkg/main.cpp"]), "app", ".exe"),
            (make_cc_library("lib", srcs=["pkg/a.cpp"]), "lib", ".lib"),
        ]:
            with self.subTest(target=target.name):
                self.assertEqual(
                    _output_names(_render_single(target)), [(DEBUG_X64, name, ext)]
                )

    def test_output_path_file_name_names_the_output(self):
        # Regression: only OutDir came from output_path, so MSBuild named the file
        # after the project and it never reached the declared artifact path.
        for make_target, output_path, name, ext in [
            (make_cc_binary, "Out/bin/Tool.exe", "Tool", ".exe"),
            (make_cc_binary, "Out/bin/my.tool.exe", "my.tool", ".exe"),
            (make_cc_binary, "Out/bin/tool", "tool", ""),
            (make_cc_library, "Out/lib/Custom.lib", "Custom", ".lib"),
        ]:
            with self.subTest(output_path=output_path):
                target = make_target(
                    "target", srcs=["pkg/a.cpp"], output_path=output_path
                )
                self.assertEqual(
                    _output_names(_render_single(target)), [(DEBUG_X64, name, ext)]
                )

    def test_output_path_special_characters_are_escaped(self):
        app = make_cc_binary(
            "app", srcs=["pkg/main.cpp"], output_path="Out/a$(b)/c%d;e@f'g.exe"
        )
        doc = _render_single(app)
        self.assertEqual(
            _texts(doc, "OutDir"), ["$(ProjectDir)\\..\\..\\..\\a%24(b)\\"]
        )
        self.assertEqual(_output_names(doc), [(DEBUG_X64, "c%25d%3Be%40f%27g", ".exe")])

    def test_output_name_resolves_per_configuration(self):
        app = make_cc_binary(
            "app",
            srcs=["pkg/main.cpp"],
            output_path=Switch(
                Case(Condition(build_config="debug"), "Out/debug/AppD.exe"),
                Case(Condition(build_config="release"), "Out/release/App.exe"),
            ),
        )
        pkg = make_package("pkg", [app])
        doc = _render(
            app,
            pkg,
            make_workspace([pkg]),
            config=make_config(build_config=["debug", "release"]),
        )
        self.assertEqual(
            _output_names(doc),
            [(DEBUG_X64, "AppD", ".exe"), (RELEASE_X64, "App", ".exe")],
        )

    def test_output_name_follows_cpp_props(self):
        # Microsoft.Cpp.props assigns TargetExt unconditionally, overwriting any
        # value set before it is imported.
        doc = _render_single(make_cc_binary("app", srcs=["pkg/main.cpp"]))
        children = [
            n for n in doc.documentElement.childNodes if n.nodeType == n.ELEMENT_NODE
        ]
        cpp_props = next(
            i
            for i, n in enumerate(children)
            if n.tagName == "Import"
            and n.getAttribute("Project").endswith("\\Microsoft.Cpp.props")
        )
        output_names = [
            i for i, n in enumerate(children) if n.getElementsByTagName("TargetExt")
        ]
        self.assertTrue(output_names)
        self.assertTrue(all(cpp_props < i for i in output_names))

    def test_header_only_library_has_no_output_name(self):
        hdr = make_cc_library("hdronly", hdrs=["pkg/a.h"])
        self.assertEqual(_output_names(_render_single(hdr)), [])
