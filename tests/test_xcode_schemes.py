"""Generated Xcode schemes and workspace files (in memory, no disk, no Xcode).

The spec under test: one shared scheme per native target, named by its flat
target name so the file sits directly in xcshareddata/xcschemes (Xcode never
reads subdirectories there); each scheme's references resolve to the target and
its product; and Xcode's own scheme autocreation is turned off.
"""

import plistlib
import unittest
from xml.dom.minidom import parseString

from builderer.generators.xcode.model import ProductType
from builderer.generators.xcode.model_builder import (
    create_xcode_project,
    gather_project_info,
)
from builderer.generators.xcode.schemes import (
    SCHEMES_DIR,
    WORKSPACE_CONTENTS,
    WORKSPACE_SETTINGS,
    create_xcode_files,
)

from factories import (
    make_apple_application,
    make_config,
    make_cc_binary,
    make_cc_library,
    make_package,
    make_workspace,
)

BUILD_ROOT = "Out/build/macos-xcode.xcodeproj"


def _config(**over):
    return make_config(
        buildtool="xcode",
        toolchain="clang",
        platform="macos",
        build_root=BUILD_ROOT,
        architecture=["arm64"],
        build_config=["debug", "release"],
        **over,
    )


def _files(packages, config=None):
    project_info = gather_project_info(config or _config(), make_workspace(packages))
    project = create_xcode_project(project_info)
    return project, create_xcode_files(project_info, project)


def _workspace_packages():
    lib = make_cc_library(
        "lib", workspace_root="MyProject/SubModule", srcs=["MyProject/SubModule/l.cpp"]
    )
    headers = make_cc_library(
        "headers", workspace_root="MyProject/SubModule", hdrs=["h.h"]
    )
    tool = make_cc_binary(
        "Client",
        workspace_root="MyProject/SubModule",
        srcs=["MyProject/SubModule/m.cpp"],
        deps=[":lib"],
    )
    binary = make_cc_binary("bin", srcs=["pkg/main.cpp"])
    app = make_apple_application(
        "App.app",
        binary=":bin",
        info_plist={"CFBundleIdentifier": "x", "CFBundleExecutable": "bin"},
    )
    return [
        make_package("MyProject/SubModule", [lib, headers, tool]),
        make_package("pkg", [binary, app]),
    ]


def _scheme(files, name):
    return parseString(files[f"{SCHEMES_DIR}/{name}.xcscheme"])


def _buildable_refs(xdoc):
    return xdoc.getElementsByTagName("BuildableReference")


class TestSchemeFiles(unittest.TestCase):
    def test_one_flat_named_scheme_per_native_target_plus_workspace_files(self):
        _, files = _files(_workspace_packages())
        self.assertEqual(
            set(files),
            {
                f"{SCHEMES_DIR}/MyProject.SubModule@lib.xcscheme",
                f"{SCHEMES_DIR}/MyProject.SubModule@Client.xcscheme",
                f"{SCHEMES_DIR}/pkg@bin.xcscheme",
                f"{SCHEMES_DIR}/pkg@App.app.xcscheme",
                WORKSPACE_CONTENTS,
                WORKSPACE_SETTINGS,
            },
        )

    def test_scheme_files_sit_directly_in_the_schemes_directory(self):
        # Xcode only discovers top-level *.xcscheme files
        _, files = _files(_workspace_packages())
        for path in files:
            if path.startswith(SCHEMES_DIR):
                self.assertNotIn("/", path[len(SCHEMES_DIR) + 1 :])

    def test_every_file_is_well_formed_xml(self):
        _, files = _files(_workspace_packages())
        for path, text in files.items():
            with self.subTest(path=path):
                parseString(text)

    def test_generation_is_deterministic(self):
        _, a = _files(_workspace_packages())
        _, b = _files(_workspace_packages())
        self.assertEqual(a, b)


class TestSchemeContents(unittest.TestCase):
    def test_buildable_references_resolve_to_the_target_and_its_product(self):
        project, files = _files(_workspace_packages())
        refs = {f.id: f for f in project.fileReferences}
        for target in project.nativeTargets:
            pkg, name = target.name.split(":")
            scheme = _scheme(files, f"{pkg.replace('/', '.')}@{name}")
            buildables = _buildable_refs(scheme)
            self.assertTrue(buildables)
            for xref in buildables:
                with self.subTest(target=target.name):
                    self.assertEqual(
                        xref.getAttribute("BuildableIdentifier"), "primary"
                    )
                    self.assertEqual(
                        xref.getAttribute("BlueprintIdentifier"), target.id
                    )
                    self.assertEqual(xref.getAttribute("BlueprintName"), target.name)
                    self.assertEqual(
                        xref.getAttribute("BuildableName"),
                        refs[target.productReference.id].path,
                    )

    def test_container_is_the_project_path_relative_to_the_workspace_root(self):
        # Xcode resolves "container:" against projectDirPath (the workspace root),
        # not against the directory holding the .xcodeproj
        _, files = _files(_workspace_packages())
        for xref in _buildable_refs(_scheme(files, "pkg@bin")):
            self.assertEqual(
                xref.getAttribute("ReferencedContainer"), f"container:{BUILD_ROOT}"
            )

    def test_runnable_products_launch_and_libraries_only_expand_macros(self):
        project, files = _files(_workspace_packages())
        kinds = {t.name: t.productType for t in project.nativeTargets}
        self.assertEqual(kinds["MyProject/SubModule:Client"], ProductType.TOOL)
        self.assertEqual(kinds["pkg:App.app"], ProductType.APPLICATION)
        for name, runnable in [
            ("MyProject.SubModule@Client", True),
            ("pkg@App.app", True),
            ("MyProject.SubModule@lib", False),
        ]:
            scheme = _scheme(files, name)
            for action in ("LaunchAction", "ProfileAction"):
                with self.subTest(scheme=name, action=action):
                    xaction = scheme.getElementsByTagName(action)[0]
                    runnables = xaction.getElementsByTagName("BuildableProductRunnable")
                    macros = xaction.getElementsByTagName("MacroExpansion")
                    self.assertEqual(len(runnables), 1 if runnable else 0)
                    self.assertEqual(len(macros), 0 if runnable else 1)

    def test_target_is_built_for_every_action(self):
        _, files = _files(_workspace_packages())
        entry = _scheme(files, "MyProject.SubModule@Client").getElementsByTagName(
            "BuildActionEntry"
        )[0]
        for action in ("Testing", "Running", "Profiling", "Archiving", "Analyzing"):
            self.assertEqual(entry.getAttribute(f"buildFor{action}"), "YES")

    def test_every_action_uses_the_first_build_config(self):
        _, files = _files(_workspace_packages())
        scheme = _scheme(files, "MyProject.SubModule@Client")
        actions = [
            "TestAction",
            "LaunchAction",
            "ProfileAction",
            "AnalyzeAction",
            "ArchiveAction",
        ]
        for action in actions:
            xaction = scheme.getElementsByTagName(action)[0]
            self.assertEqual(xaction.getAttribute("buildConfiguration"), "debug")

    def test_names_with_xml_special_characters_are_escaped(self):
        lib = make_cc_library("a&b", workspace_root="q<r", srcs=["q<r/a.cpp"])
        project, files = _files([make_package("q<r", [lib])])
        xref = _buildable_refs(_scheme(files, "q<r@a&b"))[0]
        self.assertEqual(xref.getAttribute("BlueprintName"), "q<r:a&b")


class TestSchemeNameCollisions(unittest.TestCase):
    def test_names_differing_only_by_case_are_rejected(self):
        # scheme files would overwrite each other on case-insensitive filesystems
        upper = make_cc_library("Lib", srcs=["pkg/a.cpp"])
        lower = make_cc_library("lib", srcs=["pkg/b.cpp"])
        with self.assertRaises(ValueError) as ctx:
            _files([make_package("pkg", [upper, lower])])
        self.assertIn("pkg@Lib", str(ctx.exception))
        self.assertIn("pkg@lib", str(ctx.exception))


class TestWorkspaceFiles(unittest.TestCase):
    def test_workspace_settings_turn_off_scheme_autocreation(self):
        _, files = _files(_workspace_packages())
        settings = plistlib.loads(files[WORKSPACE_SETTINGS].encode("utf-8"))
        self.assertEqual(
            settings, {"IDEWorkspaceSharedSettings_AutocreateContextsIfNeeded": False}
        )

    def test_workspace_contents_reference_the_enclosing_project(self):
        _, files = _files(_workspace_packages())
        xdoc = parseString(files[WORKSPACE_CONTENTS])
        refs = xdoc.getElementsByTagName("FileRef")
        self.assertEqual([r.getAttribute("location") for r in refs], ["self:"])


if __name__ == "__main__":
    unittest.main()
