# Xcode scheme and workspace files.
#
# Xcode names a scheme after its .xcscheme file, so a scheme named after a
# canonical "pkg/path:target" name would land in a subdirectory Xcode never
# reads. Instead builderer writes one shared scheme per native target, named
# by the target's flat name, and turns off Xcode's own scheme autocreation.

import os
from pathlib import Path
from typing import Dict, Union
from xml.dom.minidom import Document, Element

from builderer.details.as_iterator import str_iter
from builderer.details.naming import flat_target_name
from builderer.details.plist_xml import plist_dict_to_xml_text
from builderer.generators.xcode.model import (
    PBXFileReference,
    PBXNativeTarget,
    ProductType,
    XcodeProject,
)
from builderer.generators.xcode.model_builder import ProjectInfo

# Paths relative to the .xcodeproj bundle
SCHEMES_DIR = "xcshareddata/xcschemes"
WORKSPACE_CONTENTS = "project.xcworkspace/contents.xcworkspacedata"
WORKSPACE_SETTINGS = "project.xcworkspace/xcshareddata/WorkspaceSettings.xcsettings"

# Products Xcode can launch from a scheme's Run and Profile actions
RUNNABLE_PRODUCT_TYPES = frozenset({ProductType.TOOL, ProductType.APPLICATION})

LLDB_DEBUGGER = "Xcode.DebuggerFoundation.Debugger.LLDB"
LLDB_LAUNCHER = "Xcode.DebuggerFoundation.Launcher.LLDB"


def _append(xparent: Union[Document, Element], name: str, attrs={}) -> Element:
    xdoc = xparent if isinstance(xparent, Document) else xparent.ownerDocument
    assert xdoc
    xelement = xdoc.createElement(name)
    for key, value in attrs.items():
        xelement.setAttribute(key, value)
    xparent.appendChild(xelement)
    return xelement


def _to_xml(xdoc: Document) -> str:
    return xdoc.toprettyxml(indent="   ", encoding="UTF-8").decode("utf-8")


def _append_buildable(
    xparent: Element,
    target: PBXNativeTarget,
    product_ref: PBXFileReference,
    container: str,
):
    _append(
        xparent,
        "BuildableReference",
        {
            "BuildableIdentifier": "primary",
            "BlueprintIdentifier": target.id,
            "BuildableName": product_ref.path,
            "BlueprintName": target.name,
            "ReferencedContainer": container,
        },
    )


# The Run and Profile actions launch runnable products; for anything else Xcode
# still wants the target, as the source of build settings for macro expansion.
def _append_runnable(
    xparent: Element,
    target: PBXNativeTarget,
    product_ref: PBXFileReference,
    container: str,
):
    if target.productType in RUNNABLE_PRODUCT_TYPES:
        xrunnable = _append(
            xparent, "BuildableProductRunnable", {"runnableDebuggingMode": "0"}
        )
    else:
        xrunnable = _append(xparent, "MacroExpansion")
    _append_buildable(xrunnable, target, product_ref, container)


def create_scheme(
    target: PBXNativeTarget,
    product_ref: PBXFileReference,
    container: str,
    build_config: str,
) -> str:
    xdoc = Document()
    xscheme = _append(xdoc, "Scheme", {"version": "1.7"})

    xbuild = _append(
        xscheme,
        "BuildAction",
        {"parallelizeBuildables": "YES", "buildImplicitDependencies": "YES"},
    )
    xentry = _append(
        _append(xbuild, "BuildActionEntries"),
        "BuildActionEntry",
        {
            "buildForTesting": "YES",
            "buildForRunning": "YES",
            "buildForProfiling": "YES",
            "buildForArchiving": "YES",
            "buildForAnalyzing": "YES",
        },
    )
    _append_buildable(xentry, target, product_ref, container)

    xtest = _append(
        xscheme,
        "TestAction",
        {
            "buildConfiguration": build_config,
            "selectedDebuggerIdentifier": LLDB_DEBUGGER,
            "selectedLauncherIdentifier": LLDB_LAUNCHER,
            "shouldUseLaunchSchemeArgsEnv": "YES",
        },
    )
    _append(xtest, "Testables")

    xlaunch = _append(
        xscheme,
        "LaunchAction",
        {
            "buildConfiguration": build_config,
            "selectedDebuggerIdentifier": LLDB_DEBUGGER,
            "selectedLauncherIdentifier": LLDB_LAUNCHER,
            "launchStyle": "0",
            "useCustomWorkingDirectory": "NO",
            "ignoresPersistentStateOnLaunch": "NO",
            "debugDocumentVersioning": "YES",
            "debugServiceExtension": "internal",
            "allowLocationSimulation": "YES",
        },
    )
    _append_runnable(xlaunch, target, product_ref, container)

    xprofile = _append(
        xscheme,
        "ProfileAction",
        {
            "buildConfiguration": build_config,
            "shouldUseLaunchSchemeArgsEnv": "YES",
            "savedToolIdentifier": "",
            "useCustomWorkingDirectory": "NO",
            "debugDocumentVersioning": "YES",
        },
    )
    _append_runnable(xprofile, target, product_ref, container)

    _append(xscheme, "AnalyzeAction", {"buildConfiguration": build_config})
    _append(
        xscheme,
        "ArchiveAction",
        {"buildConfiguration": build_config, "revealArchiveInOrganizer": "YES"},
    )
    return _to_xml(xdoc)


def create_workspace_contents() -> str:
    xdoc = Document()
    xworkspace = _append(xdoc, "Workspace", {"version": "1.0"})
    _append(xworkspace, "FileRef", {"location": "self:"})
    return _to_xml(xdoc)


# Without this Xcode autocreates a scheme per target, named (and saved) after
# the canonical target name, alongside the generated ones.
def create_workspace_settings() -> str:
    settings = {"IDEWorkspaceSharedSettings_AutocreateContextsIfNeeded": False}
    return plist_dict_to_xml_text(settings) + "\n"


# Every file builderer writes into the .xcodeproj besides project.pbxproj,
# keyed by path relative to the bundle.
def create_xcode_files(
    project_info: ProjectInfo, project: XcodeProject
) -> Dict[str, str]:
    # Xcode resolves a scheme's "container:" path against the project's
    # projectDirPath, which is the workspace root (SRCROOT).
    xcodeproj_path = project_info.workspace_root / project_info.base_config.build_root
    container_path = os.path.relpath(xcodeproj_path, project_info.workspace_root)
    container = f"container:{Path(container_path).as_posix()}"
    build_config = next(str_iter(project_info.base_config.build_config))

    native_targets = {t.name: t for t in project.nativeTargets}
    file_refs = {f.id: f for f in project.fileReferences}

    files: Dict[str, str] = {}
    scheme_names: Dict[str, str] = {}
    for full_name, target_info in sorted(project_info.targets.items()):
        # Header-only libraries have no native target, so no scheme
        target = native_targets.get(full_name)
        if target is None:
            continue
        scheme_name = flat_target_name(
            target_info.package.name, target_info.target.name
        )
        # Scheme files must also stay distinct on case-insensitive filesystems
        folded = scheme_name.casefold()
        if folded in scheme_names:
            raise ValueError(
                f"Xcode scheme '{scheme_name}' collides with "
                f"'{scheme_names[folded]}' on case-insensitive filesystems"
            )
        scheme_names[folded] = scheme_name
        product_ref = file_refs[target.productReference.id]
        files[f"{SCHEMES_DIR}/{scheme_name}.xcscheme"] = create_scheme(
            target, product_ref, container, build_config
        )

    files[WORKSPACE_CONTENTS] = create_workspace_contents()
    files[WORKSPACE_SETTINGS] = create_workspace_settings()
    return files
