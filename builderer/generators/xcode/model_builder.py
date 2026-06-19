# Xcode project model builder.
#
# This module provides functionality to convert a builderer target into an Xcode project model.
# It extracts information from the workspace and converts it to the appropriate Xcode project model
# structures defined in model.py.

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import os
from collections import defaultdict
from dataclasses import dataclass, field

from builderer import Config
from builderer.details.target_artifact import (
    get_target_artifact_subpath,
    get_target_artifact_filename,
)
from builderer.details.package import Package
from builderer.details.targets.apple_application import (
    AppleApplication,
    validate_resolved_info_plist,
)
from builderer.details.targets.target import BuildTarget
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_cc_module import SwiftCcModule
from builderer.details.targets.swift_library import SwiftLibrary
from builderer.details.workspace import Workspace, target_full_name
from builderer.details.variable_expansion import resolve_conditionals, bake_config
from builderer.details.as_iterator import str_iter
from builderer.generators.xcode.model import (
    BuildSetting,
    DstSubfolderSpec,
    FileType,
    PBXBuildFile,
    PBXCopyFilesBuildPhase,
    PBXFileReference,
    PBXFrameworksBuildPhase,
    PBXGroup,
    PBXNativeTarget,
    PBXProject,
    PBXResourcesBuildPhase,
    PBXShellScriptBuildPhase,
    PBXSourcesBuildPhase,
    ProductType,
    Reference,
    SourceTree,
    XCBuildConfiguration,
    XCConfigurationList,
    XcodeProject,
    YesNo,
    PBXTargetDependency,
    PBXContainerItemProxy,
    ProxyType,
)

SettingValue = Union[str, YesNo]


# Apple platform/SDK traits live in these frozen dataclasses, keyed on
# config.platform via APPLE_PLATFORMS below. The generator branches on TRAITS
# (sdk.is_simulator, platform.multi_sdk, ...) rather than on SDK name strings, so
# adding tvOS/watchOS/visionOS is a single new frozen ApplePlatform instance
# (plus RULES flags) with no SDK names hardcoded anywhere in the logic.
#
# A build picks one SDK at build time via `xcodebuild -sdk`; for a multi-SDK
# platform (a device SDK + a simulator SDK) products/intermediates are separated
# per SDK via [sdk=...] conditional settings so device and simulator never
# collide or invalidate each other. The device SDK's product lands at the user's
# output_path (the deployable); the simulator's lands in intermediates.
# Intrinsic facts about an Apple SDK. (Where a product is saved is generator
# policy, not an SDK attribute, so it lives in the generator — not here.)
#  - signed: products built against this SDK are code-signed. iOS device SDKs
#    sign; simulator SDKs cannot (Xcode rejects even ad-hoc signing for them).
#  - is_simulator: this is a simulator SDK (launched via simctl, not devicectl).
@dataclass(frozen=True)
class AppleSdk:
    name: str
    signed: bool = False
    is_simulator: bool = False

    @property
    def dir_tag(self) -> str:
        return self.name

    # Xcode conditional-build-setting selector matching this SDK, e.g.
    # OTHER_LDFLAGS[sdk=iphonesimulator*]. Operates on $(SDKROOT) at build time.
    @property
    def selector(self) -> str:
        return f"sdk={self.name}*"


@dataclass(frozen=True)
class ApplePlatform:
    # config.platform value (e.g. "ios").
    name: str
    # Every SDK this project builds for, device first. Exactly one is the device
    # SDK (is_simulator=False); a multi-SDK platform also has a simulator SDK.
    sdks: Tuple[AppleSdk, ...]
    deploy_setting: str
    plist_version_key: str
    default_device_families: Optional[str] = None

    # The device SDK, whose name is SDKROOT. Xcode overlays a simulator SDK at
    # build time for a simulator destination.
    @property
    def device_sdk(self) -> AppleSdk:
        return next(s for s in self.sdks if not s.is_simulator)

    @property
    def sdkroot(self) -> str:
        return self.device_sdk.name

    @property
    def multi_sdk(self) -> bool:
        return len(self.sdks) > 1


MACOS = ApplePlatform(
    name="macos",
    sdks=(AppleSdk("macosx"),),
    deploy_setting="MACOSX_DEPLOYMENT_TARGET",
    plist_version_key="LSMinimumSystemVersion",
)

IOS = ApplePlatform(
    name="ios",
    sdks=(
        AppleSdk("iphoneos", signed=True),
        AppleSdk("iphonesimulator", is_simulator=True),
    ),
    deploy_setting="IPHONEOS_DEPLOYMENT_TARGET",
    plist_version_key="MinimumOSVersion",
    default_device_families="1,2",
)

# Future: TVOS, WATCHOS, VISIONOS as additional frozen ApplePlatform instances.
APPLE_PLATFORMS: Dict[str, ApplePlatform] = {
    "macos": MACOS,
    "ios": IOS,
}

# Extensions that Xcode can compile (add to sources build phase)
COMPILABLE_EXTENSIONS = frozenset(
    {
        # C/C++
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        # Objective-C/C++
        ".m",
        ".mm",
        # Assembly
        ".s",
        # Swift
        ".swift",
        # Metal (Xcode's built-in rule compiles these into default.metallib)
        ".metal",
    }
)


@dataclass(frozen=True)
class XcodeSetting:
    name: str  # Xcode build setting name
    default: SettingValue  # Default value at project level
    choices: Dict[str, SettingValue] = field(
        default_factory=dict
    )  # flag -> value mapping


# Unified table of Xcode build settings
# - default: value set at project level
# - choices: maps command-line flags to setting values (includes -Wno-* variants)
# Flags not in any choices dict pass through to OTHER_CFLAGS (e.g. -Wall, -Wextra)
XCODE_SETTINGS: List[XcodeSetting] = [
    # Warning settings - defaults prevent Xcode from injecting its own -W flags
    # Each includes both positive (-W*) and negative (-Wno-*) variants
    XcodeSetting(
        "GCC_WARN_64_TO_32_BIT_CONVERSION",
        YesNo.NO,
        {
            "-Wshorten-64-to-32": YesNo.YES,
            "-Wno-shorten-64-to-32": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_ABOUT_RETURN_TYPE",
        YesNo.NO,
        {
            "-Wreturn-type": YesNo.YES,
            "-Wno-return-type": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_UNDECLARED_SELECTOR",
        YesNo.NO,
        {
            "-Wundeclared-selector": YesNo.YES,
            "-Wno-undeclared-selector": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_UNINITIALIZED_AUTOS",
        YesNo.NO,
        {
            "-Wuninitialized": YesNo.YES,
            "-Wno-uninitialized": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_UNUSED_FUNCTION",
        YesNo.NO,
        {
            "-Wunused-function": YesNo.YES,
            "-Wno-unused-function": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_UNUSED_VARIABLE",
        YesNo.NO,
        {
            "-Wunused-variable": YesNo.YES,
            "-Wno-unused-variable": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING",
        YesNo.NO,
        {
            "-Wblock-capture-autoreleasing": YesNo.YES,
            "-Wno-block-capture-autoreleasing": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_BOOL_CONVERSION",
        YesNo.NO,
        {
            "-Wbool-conversion": YesNo.YES,
            "-Wno-bool-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_COMMA",
        YesNo.NO,
        {
            "-Wcomma": YesNo.YES,
            "-Wno-comma": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_CONSTANT_CONVERSION",
        YesNo.NO,
        {
            "-Wconstant-conversion": YesNo.YES,
            "-Wno-constant-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS",
        YesNo.NO,
        {
            "-Wdeprecated-implementations": YesNo.YES,
            "-Wno-deprecated-implementations": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_DIRECT_OBJC_ISA_USAGE",
        YesNo.NO,
        {
            "-Wdeprecated-objc-isa-usage": YesNo.YES,
            "-Wno-deprecated-objc-isa-usage": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_DOCUMENTATION_COMMENTS",
        YesNo.NO,
        {
            "-Wdocumentation": YesNo.YES,
            "-Wno-documentation": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_EMPTY_BODY",
        YesNo.NO,
        {
            "-Wempty-body": YesNo.YES,
            "-Wno-empty-body": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_ENUM_CONVERSION",
        YesNo.NO,
        {
            "-Wenum-conversion": YesNo.YES,
            "-Wno-enum-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_INFINITE_RECURSION",
        YesNo.NO,
        {
            "-Winfinite-recursion": YesNo.YES,
            "-Wno-infinite-recursion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_INT_CONVERSION",
        YesNo.NO,
        {
            "-Wint-conversion": YesNo.YES,
            "-Wno-int-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_NON_LITERAL_NULL_CONVERSION",
        YesNo.NO,
        {
            "-Wnon-literal-null-conversion": YesNo.YES,
            "-Wno-non-literal-null-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF",
        YesNo.NO,
        {
            "-Wimplicit-retain-self": YesNo.YES,
            "-Wno-implicit-retain-self": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_OBJC_LITERAL_CONVERSION",
        YesNo.NO,
        {
            "-Wobjc-literal-conversion": YesNo.YES,
            "-Wno-objc-literal-conversion": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_OBJC_ROOT_CLASS",
        YesNo.NO,
        {
            "-Wobjc-root-class": YesNo.YES,
            "-Wno-objc-root-class": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER",
        YesNo.NO,
        {
            "-Wquoted-include-in-framework-header": YesNo.YES,
            "-Wno-quoted-include-in-framework-header": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_RANGE_LOOP_ANALYSIS",
        YesNo.NO,
        {
            "-Wrange-loop-analysis": YesNo.YES,
            "-Wno-range-loop-analysis": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_STRICT_PROTOTYPES",
        YesNo.NO,
        {
            "-Wstrict-prototypes": YesNo.YES,
            "-Wno-strict-prototypes": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_SUSPICIOUS_MOVE",
        YesNo.NO,
        {
            "-Wmove": YesNo.YES,
            "-Wno-move": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_UNGUARDED_AVAILABILITY",
        YesNo.NO,
        {
            "-Wunguarded-availability": YesNo.YES,
            "-Wno-unguarded-availability": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN_UNREACHABLE_CODE",
        YesNo.NO,
        {
            "-Wunreachable-code": YesNo.YES,
            "-Wno-unreachable-code": YesNo.NO,
        },
    ),
    XcodeSetting(
        "CLANG_WARN__DUPLICATE_METHOD_MATCH",
        YesNo.NO,
        {
            "-Wduplicate-method-match": YesNo.YES,
            "-Wno-duplicate-method-match": YesNo.NO,
        },
    ),
    # Warning control
    XcodeSetting(
        "GCC_TREAT_WARNINGS_AS_ERRORS",
        YesNo.NO,
        {
            "-Werror": YesNo.YES,
            "-Wno-error": YesNo.NO,
        },
    ),
    XcodeSetting(
        "GCC_WARN_INHIBIT_ALL_WARNINGS",
        YesNo.NO,
        {
            "-w": YesNo.YES,
        },
    ),
    XcodeSetting(
        "GCC_WARN_PEDANTIC",
        YesNo.NO,
        {
            "-pedantic": YesNo.YES,
            "-Wpedantic": YesNo.YES,
            "-Wno-pedantic": YesNo.NO,
        },
    ),
    # Optimization levels
    XcodeSetting(
        "GCC_OPTIMIZATION_LEVEL",
        "0",
        {
            "-O0": "0",
            "-O1": "1",
            "-O2": "2",
            "-O3": "3",
            "-Os": "s",
            "-Ofast": "fast",
        },
    ),
    # Debug info
    XcodeSetting(
        "GCC_GENERATE_DEBUGGING_SYMBOLS",
        YesNo.NO,
        {
            "-g": YesNo.YES,
            "-g0": YesNo.NO,
        },
    ),
    # C++ language standard
    XcodeSetting(
        "CLANG_CXX_LANGUAGE_STANDARD",
        "c++17",
        {
            "-std=c++14": "c++14",
            "-std=c++17": "c++17",
            "-std=c++20": "c++20",
            "-std=c++23": "c++23",
            "-std=gnu++14": "gnu++14",
            "-std=gnu++17": "gnu++17",
            "-std=gnu++20": "gnu++20",
        },
    ),
    # C language standard
    XcodeSetting(
        "GCC_C_LANGUAGE_STANDARD",
        "c17",
        {
            "-std=c11": "c11",
            "-std=c17": "c17",
            "-std=gnu11": "gnu11",
            "-std=gnu17": "gnu17",
        },
    ),
]

# Build lookup table: flag -> (setting_name, value)
_FLAG_LOOKUP: Dict[str, Tuple[str, SettingValue]] = {
    flag: (setting.name, value)
    for setting in XCODE_SETTINGS
    for flag, value in setting.choices.items()
}


def parse_compiler_flags(
    flags: List[str],
) -> Tuple[Dict[str, SettingValue], List[str]]:
    settings: Dict[str, SettingValue] = {}
    remaining: List[str] = []

    for flag in flags:
        if flag in _FLAG_LOOKUP:
            name, value = _FLAG_LOOKUP[flag]
            settings[name] = value
        else:
            # Unknown flags pass through to OTHER_CFLAGS
            remaining.append(flag)

    return settings, remaining


@dataclass(frozen=True)
class TargetResult:
    target: PBXNativeTarget
    file_references: List[PBXFileReference]
    groups: List[PBXGroup]
    build_files: List[PBXBuildFile]
    build_phases: List[
        Union[
            PBXSourcesBuildPhase,
            PBXFrameworksBuildPhase,
            PBXResourcesBuildPhase,
            PBXCopyFilesBuildPhase,
            PBXShellScriptBuildPhase,
        ]
    ]
    configurations: List[XCBuildConfiguration]
    config_list: XCConfigurationList


@dataclass(frozen=True)
class TargetInfo:
    target: BuildTarget
    package: Package
    sources: List[str]  # Paths relative to workspace root
    headers: List[str]  # Paths relative to workspace root
    resources: List[Tuple[str, str]]  # (src, dst): dst is the in-bundle path
    product_type: ProductType
    file_type: FileType

    @staticmethod
    def from_target(
        base_config: Config,
        workspace: Workspace,
        package: Package,
        target: BuildTarget,
    ) -> TargetInfo:
        sources: List[str] = []
        headers: List[str] = []
        resources: List[Tuple[str, str]] = []

        if isinstance(target, (CCBinary, CCLibrary)):
            # Gather sources and headers across all configs
            source_set: Set[str] = set()
            header_set: Set[str] = set()

            # Sources and headers should be the same for all configs
            # Use base_config to verify this and get the values
            if isinstance(target, CCLibrary):
                # For libraries, headers are part of the public interface
                header_paths = resolve_conditionals(base_config, target.hdrs)
                header_set.update(str(p) for p in header_paths)

                # Sources are internal implementation
                source_paths = resolve_conditionals(base_config, target.srcs)
                source_set.update(str(p) for p in source_paths)
            else:
                # For binaries, all sources are implementation
                source_paths = resolve_conditionals(base_config, target.srcs)
                source_set.update(str(p) for p in source_paths)

            sources = sorted(source_set)
            headers = sorted(header_set)

            # Determine product type and file type
            if isinstance(target, CCLibrary):
                product_type = ProductType.STATIC_LIBRARY
                file_type = FileType.EXECUTABLE  # Static libraries use EXECUTABLE type
            else:
                product_type = ProductType.TOOL
                file_type = FileType.EXECUTABLE
        elif isinstance(target, (SwiftBinary, SwiftLibrary)):
            swift_source_set: Set[str] = set()
            swift_source_paths = resolve_conditionals(base_config, target.srcs)
            swift_source_set.update(str(p) for p in swift_source_paths)
            sources = sorted(swift_source_set)
            headers = []
            if isinstance(target, SwiftLibrary):
                product_type = ProductType.STATIC_LIBRARY
                file_type = FileType.EXECUTABLE
            else:
                product_type = ProductType.TOOL
                file_type = FileType.EXECUTABLE
        elif isinstance(target, AppleApplication):
            app_source_set: Set[str] = set()
            _, dep_binary = target.resolve_binary_target(workspace, package)
            binary_sources = resolve_conditionals(base_config, dep_binary.srcs)
            app_source_set.update(str(p) for p in binary_sources)
            sources = sorted(app_source_set)
            # Merged (src, dst) resource pairs from the app's file_groups.
            resources = target.resolve_resources(workspace, package)
            product_type = ProductType.APPLICATION
            file_type = FileType.APP
        elif isinstance(target, MetalLibrary):
            # A metal_library is its own Xcode Metal Library target
            # (com.apple.product-type.metal-library): its .metal files go in
            # Compile Sources and Xcode emits a bare <PRODUCT_NAME>.metallib
            # product. The consuming app embeds that file via Copy Bundle Resources.
            metal_source_set: Set[str] = set()
            metal_source_paths = resolve_conditionals(base_config, target.srcs)
            metal_source_set.update(str(p) for p in metal_source_paths)
            sources = sorted(metal_source_set)
            headers = []
            product_type = ProductType.METAL_LIBRARY
            file_type = FileType.METAL_LIBRARY
        else:
            raise ValueError(f"Unsupported target type: {type(target)}")

        return TargetInfo(
            target=target,
            package=package,
            sources=sources,
            headers=headers,
            resources=resources,
            product_type=product_type,
            file_type=file_type,
        )


@dataclass(frozen=True)
class ProjectInfo:
    targets: Dict[str, TargetInfo]  # target_name -> info
    dependencies: Dict[str, Set[str]]  # target_name -> dependent_target_names
    configs: List[Config]
    base_config: Config
    workspace_root: Path
    project_dir: Path
    workspace: Workspace  # Added for dependency resolution

    @staticmethod
    def gather(
        workspace: Workspace,
        base_config: Config,
        configs: List[Config],
    ) -> ProjectInfo:
        targets = {}
        dependencies = {}

        # Get project directory from config - this is the parent of the .xcodeproj
        project_dir = Path(
            os.path.dirname(os.path.join(workspace.root, base_config.build_root))
        )

        # First pass: gather all target info
        for package, target in workspace.targets:
            if not isinstance(target, BuildTarget):
                continue
            targets[target_full_name(package, target)] = TargetInfo.from_target(
                base_config=base_config,
                workspace=workspace,
                package=package,
                target=target,
            )

        # Second pass: gather dependencies
        for full_name, target_info in targets.items():
            deps = set()
            if isinstance(
                target_info.target,
                (CCBinary, CCLibrary, SwiftBinary, SwiftLibrary),
            ):
                for pkg, dep_target in workspace.all_dependencies(
                    target_info.package, target_info.target
                ):
                    if (
                        isinstance(dep_target, (CCLibrary, SwiftLibrary))
                        and dep_target.srcs
                    ):
                        deps.add(target_full_name(pkg, dep_target))
            elif isinstance(target_info.target, AppleApplication):
                dep_pkg, dep_target = target_info.target.resolve_binary_target(
                    workspace, target_info.package
                )
                deps.add(target_full_name(dep_pkg, dep_target))
                # metal_library deps: each is its own metal-library target the
                # app depends on (build order) and embeds its <name>.metallib
                # product (Copy Files -> Resources, third pass).
                for (
                    ml_pkg,
                    ml_target,
                ) in target_info.target.resolve_metal_library_targets(
                    workspace, target_info.package
                ):
                    deps.add(target_full_name(ml_pkg, ml_target))
            dependencies[full_name] = deps

        return ProjectInfo(
            targets=targets,
            dependencies=dependencies,
            configs=configs,
            base_config=base_config,
            workspace_root=workspace.root,
            project_dir=project_dir,
            workspace=workspace,  # Store the workspace
        )


def get_target_include_paths(
    target_info: TargetInfo,
    config: Config,
    project_info: ProjectInfo,
) -> List[str]:
    includes: List[str] = []

    # Add target's own include paths
    if isinstance(target_info.target, CCLibrary):
        for inc in str_iter(
            resolve_conditionals(config, target_info.target.public_includes)
        ):
            includes.append(os.path.normpath(inc))
        for inc in str_iter(
            resolve_conditionals(config, target_info.target.private_includes)
        ):
            includes.append(os.path.normpath(inc))
    elif isinstance(target_info.target, CCBinary):
        for inc in str_iter(
            resolve_conditionals(config, target_info.target.private_includes)
        ):
            includes.append(os.path.normpath(inc))
    elif isinstance(target_info.target, AppleApplication):
        _, dep_binary = target_info.target.resolve_binary_target(
            project_info.workspace, target_info.package
        )
        if isinstance(dep_binary, CCBinary):
            for inc in str_iter(
                resolve_conditionals(config, dep_binary.private_includes)
            ):
                includes.append(os.path.normpath(inc))
        # SwiftBinary has no *_includes fields; Swift gets clang search paths via -Xcc.
    elif isinstance(target_info.target, (SwiftBinary, SwiftLibrary)):
        # Swift targets have no *_includes of their own; transitive cc deps
        # contribute below.
        pass
    elif isinstance(target_info.target, MetalLibrary):
        # A metal_library compiles only .metal sources; it has no C include
        # paths of its own and no cc deps to inherit.
        pass
    else:
        raise ValueError(f"Unsupported target type: {type(target_info.target)}")

    # Add public include paths from all dependencies (for both libraries and binaries)
    for pkg, dep_target in project_info.workspace.all_dependencies(
        target_info.package, target_info.target
    ):
        if isinstance(dep_target, CCLibrary):
            for inc in str_iter(
                resolve_conditionals(config, dep_target.public_includes)
            ):
                includes.append(os.path.normpath(inc))

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: List[str] = []
    for path in includes:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def get_target_output_path(
    target_info: TargetInfo,
    config: Config,
    symroot_rel: str,
) -> str:
    _ = symroot_rel
    return get_target_artifact_subpath(
        config=config, package_name=target_info.package.name, target=target_info.target
    ).as_posix()


def build_package_group_hierarchy(
    project_info: ProjectInfo,
) -> Tuple[Dict[str, PBXGroup], List[PBXGroup]]:
    # Collect all unique package paths from targets
    package_paths: Set[Path] = set()
    for target_info in project_info.targets.values():
        package_paths.add(Path(target_info.package.name))
    # Also collect all parent directories to create intermediate groups
    all_paths: Set[Path] = set()
    for pkg_path in package_paths:
        all_paths.add(pkg_path)
        for parent in pkg_path.parents:
            if parent != Path(".") and parent != Path():
                all_paths.add(parent)
    # Sort paths by depth (parents before children), then alphabetically for determinism
    sorted_paths = sorted(all_paths, key=lambda p: (len(p.parts), str(p)))
    # Create groups for each path
    path_to_group: Dict[str, PBXGroup] = {}
    all_groups: List[PBXGroup] = []
    for path in sorted_paths:
        group = PBXGroup(
            name=path.name,
            sourceTree=SourceTree.GROUP,
            children=[],
            group_id=f"package:{path}",
        )
        path_to_group[str(path)] = group
        all_groups.append(group)
        # Add to parent group if it exists
        parent = path.parent
        if parent != Path(".") and parent != Path() and str(parent) in path_to_group:
            parent_group = path_to_group[str(parent)]
            parent_group.children.append(Reference(group.id, path.name))
    return path_to_group, all_groups


def create_xcode_project(project_info: ProjectInfo) -> XcodeProject:
    # Create base project structure
    main_group = PBXGroup(name="", sourceTree=SourceTree.GROUP, children=[])
    products_group = PBXGroup(
        name="Products", sourceTree=SourceTree.GROUP, children=[], group_id="products"
    )
    main_group.children.append(Reference(products_group.id, "Products"))

    # Build hierarchical package groups
    package_groups, package_group_list = build_package_group_hierarchy(project_info)

    # Add top-level package groups to main group
    top_level_paths = sorted(
        {str(Path(ti.package.name).parts[0]) for ti in project_info.targets.values()}
    )
    for top_path in top_level_paths:
        if top_path in package_groups:
            group = package_groups[top_path]
            main_group.children.append(Reference(group.id, top_path))

    # Compute custom build roots to avoid polluting workspace with default 'build'
    project_stem = Path(project_info.base_config.build_root).stem
    build_root_dir = os.path.dirname(project_info.base_config.build_root)
    # Paths are relative to workspace root in Xcode (SRCROOT is workspace root)
    objroot_rel = os.path.join(build_root_dir, ".xcode-obj", project_stem)
    symroot_rel = os.path.join(build_root_dir, ".xcode-sym", project_stem)

    # SDKROOT selects the base SDK; Xcode forms the compiler target from it plus
    # ARCHS and the deployment target, so builderer never bakes a -target. For
    # ios this is "iphoneos"; Xcode overlays the simulator SDK at build time for
    # a simulator destination.
    apple_platform = APPLE_PLATFORMS[project_info.base_config.platform]

    # Create project-level configuration list - one config per build config
    project_configs = []
    for build_cfg in str_iter(project_info.base_config.build_config):
        # Start with empty settings; do not inject defaults
        settings: Dict[str, BuildSetting] = {}
        # Relocate intermediates under Out/build (CONFIGURATION_BUILD_DIR set per-target)
        settings.update(
            {
                "SDKROOT": BuildSetting(value=apple_platform.sdkroot),
                "OBJROOT": BuildSetting(value=f"$(SRCROOT)/{objroot_rel}"),
                "SYMROOT": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "SHARED_PRECOMPS_DIR": BuildSetting(
                    value=f"$(OBJROOT)/SharedPrecompiledHeaders"
                ),
                "ALWAYS_SEARCH_USER_PATHS": BuildSetting(value=YesNo.NO),
                # Disable header maps: they cause include collisions
                "USE_HEADERMAP": BuildSetting(value=YesNo.NO),
                "CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
                "AD_HOC_CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
            }
        )
        # Apply defaults from settings table (prevents Xcode from injecting its own flags)
        for setting in XCODE_SETTINGS:
            settings[setting.name] = BuildSetting(value=setting.default)
        project_configs.append(
            XCBuildConfiguration(
                name=str(build_cfg),
                buildSettings=settings,
                owner="PROJECT",
            )
        )
    project_config_list = XCConfigurationList(
        buildConfigurations=[Reference(c.id) for c in project_configs],
        defaultConfigurationName=project_configs[0].name,  # Use first config's name
        owner="PROJECT",
    )

    # Calculate project directory path relative to .xcodeproj location
    # build_root is the .xcodeproj path, so we need the directory containing it
    xcodeproj_dir = os.path.dirname(
        os.path.join(project_info.workspace_root, project_info.base_config.build_root)
    )
    project_dir_path = os.path.relpath(str(project_info.workspace_root), xcodeproj_dir)

    # Create project
    project = PBXProject(
        name=Path(project_info.base_config.build_root).stem,
        buildConfigurationList=Reference(project_config_list.id),
        mainGroup=Reference(main_group.id),
        productRefGroup=Reference(products_group.id),
        targets=[],  # Will be filled in later
        projectDirPath=project_dir_path,
        projectRoot=project_dir_path,
    )

    # Create file reference registry to avoid duplicates
    file_ref_registry: Dict[str, PBXFileReference] = {}

    # Process each target
    native_targets = []
    file_references = []
    groups = [main_group, products_group] + package_group_list
    build_files = []
    build_phases = []
    build_configurations = project_configs  # Start with project configs
    configuration_lists = [project_config_list]
    target_dependencies = []
    container_item_proxies = []
    # Lookups for later wiring (keyed by target_full_name)
    native_target_by_name: Dict[str, PBXNativeTarget] = {}
    product_ref_by_target: Dict[str, PBXFileReference] = {}

    # First pass: create all targets and their file references
    for full_name, target_info in sorted(project_info.targets.items()):
        # Skip header-only libraries - they don't need Xcode targets
        if isinstance(target_info.target, CCLibrary) and not target_info.sources:
            continue

        target_result = create_target(
            target_info, project_info, file_ref_registry, symroot_rel
        )

        native_targets.append(target_result.target)
        native_target_by_name[full_name] = target_result.target
        file_references.extend(target_result.file_references)
        groups.extend(target_result.groups)
        build_files.extend(target_result.build_files)
        build_phases.extend(target_result.build_phases)
        build_configurations.extend(target_result.configurations)
        configuration_lists.append(target_result.config_list)

        # Add target's main group to its package group (hierarchical layout)
        package_path = target_info.package.name
        if package_path in package_groups:
            package_group = package_groups[package_path]
            package_group.children.append(
                Reference(target_result.groups[0].id, target_info.target.name)
            )
        else:
            # Fallback: add directly to main group if no package group
            main_group.children.append(Reference(target_result.groups[0].id, full_name))

        # Add product reference to Products group
        product_ref = target_result.file_references[0]
        products_group.children.append(Reference(product_ref.id, full_name))
        product_ref_by_target[full_name] = product_ref

        # Add target reference to project
        project.targets.append(Reference(target_result.target.id, full_name))

    # Second pass: add dependencies between targets
    for full_name, deps in sorted(project_info.dependencies.items()):
        # Skip if this target wasn't created (header-only library)
        if full_name not in native_target_by_name:
            continue
        target = native_target_by_name[full_name]

        for dep_full_name in deps:
            # Skip if dependency wasn't created (header-only library)
            if dep_full_name not in native_target_by_name:
                continue
            dep_target = native_target_by_name[dep_full_name]

            # Create container proxy
            container_proxy = PBXContainerItemProxy(
                containerPortal=project.id,
                proxyType=ProxyType.TARGET_DEPENDENCY,
                remoteGlobalIDString=dep_target.id,
                remoteInfo=dep_full_name,
            )
            container_item_proxies.append(container_proxy)

            # Create target dependency
            target_dependency = PBXTargetDependency(
                target=dep_target.id,
                targetProxy=Reference(container_proxy.id),
            )
            target_dependencies.append(target_dependency)

            # Add to target's dependencies (build order only - linking is via OTHER_LDFLAGS)
            target.dependencies.append(Reference(target_dependency.id))

    # Third pass: embed each app's metal_library product(s) via a Copy Files
    # (Resources) build phase. This must run after the first pass, since it
    # references each metal target's product file ref (created per-target and
    # recorded in product_ref_by_target). Each metal_library product is a bare
    # <target.name>.metallib file; Xcode copies it into the app's Resources root.
    # A dep named "default" lands as default.metallib and is loaded by
    # makeDefaultLibrary(); others are loaded by makeLibrary(URL:).
    # (Phase 0 on Xcode 26.5 verified this lands the metallibs at the resources
    # root and both load APIs resolve them.)
    for full_name, target_info in sorted(project_info.targets.items()):
        app = target_info.target
        if not isinstance(app, AppleApplication):
            continue
        if full_name not in native_target_by_name:
            continue
        metal_deps = app.resolve_metal_library_targets(
            project_info.workspace, target_info.package
        )
        if not metal_deps:
            continue
        app_target = native_target_by_name[full_name]
        copy_build_files = []
        for ml_pkg, ml_target in metal_deps:
            ml_full_name = target_full_name(ml_pkg, ml_target)
            metal_product_ref = product_ref_by_target.get(ml_full_name)
            if metal_product_ref is None:
                continue
            copy_build_files.append(
                PBXBuildFile(
                    fileRef=Reference(metal_product_ref.id),
                    name=metal_product_ref.name,
                    target_name=f"{full_name}:embed",
                )
            )
        if not copy_build_files:
            continue
        copy_phase = PBXCopyFilesBuildPhase(
            files=[Reference(bf.id) for bf in copy_build_files],
            dstPath="",
            dstSubfolderSpec=DstSubfolderSpec.RESOURCES,
            target_name=full_name,
        )
        build_files.extend(copy_build_files)
        build_phases.append(copy_phase)
        app_target.buildPhases.append(Reference(copy_phase.id))

    # Sort all list fields on all objects for deterministic output
    for group in groups:
        group.children.sort(key=lambda r: r.id)
    for target in native_targets:
        target.dependencies.sort(key=lambda r: r.id)
    for phase in build_phases:
        phase.files.sort(key=lambda r: r.id)
    project.targets.sort(key=lambda r: r.id)

    return XcodeProject(
        fileReferences=sorted(file_ref_registry.values(), key=lambda f: f.id)
        + sorted(product_ref_by_target.values(), key=lambda f: f.id),
        groups=groups,
        buildFiles=sorted(build_files, key=lambda b: b.id),
        buildPhases=build_phases,
        nativeTargets=sorted(native_targets, key=lambda t: t.id),
        project=project,
        buildConfigurations=sorted(build_configurations, key=lambda c: c.id),
        configurationLists=sorted(configuration_lists, key=lambda c: c.id),
        targetDependencies=sorted(target_dependencies, key=lambda t: t.id),
        containerItemProxies=sorted(container_item_proxies, key=lambda c: c.id),
    )


# Code-signing settings for one target, per SDK. Only the app bundle is signed;
# its static-library deps and standalone tool products are not (signing them
# wrongly demands a development team for a .a / bare binary). A simulator SDK
# must NOT sign (Xcode rejects even ad-hoc signing for it); a device SDK signs
# the bundle with automatic style, optionally using its development team.
# Settings are keyed per-SDK so a multi-SDK platform (device + simulator) gets
# the right behavior per destination. A single-SDK desktop platform (macOS)
# keeps the existing plain no-signing behavior.
def _signing_settings(
    platform: ApplePlatform, target_info: TargetInfo
) -> Dict[str, BuildSetting]:
    # The app bundle is the only signed product (its static-library deps and
    # standalone tools are not), and the only target type carrying a team.
    app = target_info.target
    settings: Dict[str, BuildSetting] = {}
    for sdk in platform.sdks:
        # A single-SDK platform emits plain (unconditioned) keys to preserve the
        # existing macOS output; a multi-SDK platform keys per SDK so each
        # destination signs correctly. Whether to sign is the SDK's `signed`
        # trait AND whether the product type signs at all, never inferred.
        cond = "" if not platform.multi_sdk else f"[{sdk.selector}]"
        if sdk.signed and isinstance(app, AppleApplication):
            # A device build of an app must be signed, which Apple requires a
            # team for; an unset team here is a misconfiguration, not a no-op.
            assert app.development_team is not None, (
                f"AppleApplication '{app.name}' must set development_team to "
                f"sign for {sdk.name}"
            )
            settings[f"CODE_SIGNING_ALLOWED{cond}"] = BuildSetting(value=YesNo.YES)
            settings[f"CODE_SIGN_STYLE{cond}"] = BuildSetting(value="Automatic")
            settings[f"DEVELOPMENT_TEAM{cond}"] = BuildSetting(
                value=app.development_team
            )
        else:
            settings[f"CODE_SIGNING_ALLOWED{cond}"] = BuildSetting(value=YesNo.NO)
            settings[f"AD_HOC_CODE_SIGNING_ALLOWED{cond}"] = BuildSetting(
                value=YesNo.NO
            )
    return settings


# One build matrix entry. A single-SDK platform (macos) varies by architecture
# (selector "arch=<arch>"); a multi-SDK platform (ios, single-arch) varies by SDK
# (selector "sdk=<sdk>*"). Either way a variant knows its conditional-setting
# selector and the directory tag for its intermediates, so all per-variant build
# settings are emitted by one generic loop rather than per-platform branches.
@dataclass(frozen=True)
class BuildVariant:
    selector: str  # e.g. "arch=arm64" or "sdk=iphonesimulator*"
    dir_tag: str  # intermediates segment, e.g. "arm64" or "iphonesimulator"
    config: Config  # baked config (single arch + build_config) for this variant
    is_deployable: bool  # product lands at the user's output_path (vs intermediates)


# The build variants for a target/build_config. A single-SDK platform (macos)
# yields one variant per architecture. A multi-SDK platform (ios) yields one per
# SDK. is_deployable is the GENERATOR's output policy (not an SDK attribute): a
# simulator variant's product is throwaway (-> intermediates), so it does not
# ship; every other variant's product ships to the user's output_path.
def _build_variants(
    platform: ApplePlatform, project_info: ProjectInfo, build_cfg: str
) -> List[BuildVariant]:
    archs = list(str_iter(project_info.base_config.architecture))
    if not platform.multi_sdk:
        return [
            BuildVariant(
                selector=f"arch={arch}",
                dir_tag=arch,
                config=bake_config(
                    project_info.base_config, architecture=arch, build_config=build_cfg
                ),
                is_deployable=True,
            )
            for arch in archs
        ]
    # Multi-SDK platforms are single-arch (the generator asserts one arch).
    arch = archs[0]
    config = bake_config(
        project_info.base_config, architecture=arch, build_config=build_cfg
    )
    return [
        BuildVariant(
            selector=sdk.selector,
            dir_tag=sdk.dir_tag,
            config=config,
            is_deployable=not sdk.is_simulator,
        )
        for sdk in platform.sdks
    ]


# The directory a target's product lands in for a build variant. A deployable
# variant (the device/desktop SDK) honors the user's declared output_path; a
# non-deployable one (the simulator) is never redistributed, so it goes to a
# per-variant intermediates directory. The product FILENAME is identical across
# variants (the user's choice); only the directory differs.
def _variant_product_dir(
    variant: BuildVariant,
    target_info: TargetInfo,
    build_cfg: str,
    symroot_rel: str,
) -> str:
    if variant.is_deployable:
        return os.path.dirname(
            get_target_output_path(target_info, variant.config, symroot_rel)
        )
    return os.path.join(
        symroot_rel, f"{variant.dir_tag}-{build_cfg}", target_info.package.name
    )


# Build-output directories for one target/build_config, emitted uniformly per
# variant. For a multi-SDK platform each SDK gets its own OBJROOT/SYMROOT so
# device and simulator intermediates never collide; for macOS the single-SDK,
# per-arch behavior is preserved (plain OBJROOT/SYMROOT plus per-arch
# CONFIGURATION_BUILD_DIR).
def _build_dir_settings(
    platform: ApplePlatform,
    target_info: TargetInfo,
    project_info: ProjectInfo,
    build_cfg: str,
    objroot_rel: str,
    symroot_rel: str,
) -> Dict[str, BuildSetting]:
    settings: Dict[str, BuildSetting] = {}
    variants = _build_variants(platform, project_info, build_cfg)

    if platform.multi_sdk:
        # Separate intermediates per variant (SDK).
        for variant in variants:
            cond = f"[{variant.selector}]"
            obj = os.path.join(objroot_rel, f"{variant.dir_tag}-{build_cfg}")
            sym = os.path.join(symroot_rel, f"{variant.dir_tag}-{build_cfg}")
            settings[f"OBJROOT{cond}"] = BuildSetting(value=f"$(SRCROOT)/{obj}")
            settings[f"SYMROOT{cond}"] = BuildSetting(value=f"$(SRCROOT)/{sym}")
    else:
        # Single-SDK: shared intermediates (per-arch dirs differ only by product).
        settings["OBJROOT"] = BuildSetting(value=f"$(SRCROOT)/{objroot_rel}")
        settings["SYMROOT"] = BuildSetting(value=f"$(SRCROOT)/{symroot_rel}")

    product_dirs = {
        variant.selector: _variant_product_dir(
            variant, target_info, build_cfg, symroot_rel
        )
        for variant in variants
    }
    for variant in variants:
        settings[f"CONFIGURATION_BUILD_DIR[{variant.selector}]"] = BuildSetting(
            value=f"$(SRCROOT)/{product_dirs[variant.selector]}"
        )
    # A base (unconditioned) value for steps that read it before resolving the
    # variant (e.g. universal-binary tooling); first variant is representative.
    settings["CONFIGURATION_BUILD_DIR"] = BuildSetting(
        value=f"$(SRCROOT)/{product_dirs[variants[0].selector]}"
    )
    return settings


# Dependency targets to link against, in correct link order (dependents before
# dependencies), filtered to the given target types that actually produce a
# library archive (i.e. have sources). Shared by the cc/apple/swift link blocks.
def _ordered_link_deps(
    target_info: TargetInfo,
    project_info: ProjectInfo,
    types: Tuple[type, ...],
) -> List[TargetInfo]:
    deps: List[TargetInfo] = []
    for dep_pkg, dep_target in reversed(
        list(
            project_info.workspace.all_dependencies(
                target_info.package, target_info.target
            )
        )
    ):
        # Only library targets carry sources to link; a header-only library
        # (no srcs) produces no archive and is skipped.
        if (
            isinstance(dep_target, types)
            and isinstance(dep_target, (CCLibrary, SwiftLibrary))
            and dep_target.srcs
        ):
            dep_ti = project_info.targets.get(target_full_name(dep_pkg, dep_target))
            if dep_ti:
                deps.append(dep_ti)
    return deps


# Emit OTHER_LDFLAGS per build variant: each variant links against that variant's
# dependency products, which live in the variant's product directory (see
# _variant_product_dir). The dependency product FILENAME is identical across
# variants; only its directory differs. One uniform loop covers macOS (per-arch)
# and multi-SDK (per-SDK). link_flags are the target's raw (conditional) user
# link flags, resolved per variant. Called once per target (not inside the
# per-arch loop) since it enumerates all variants itself.
def _emit_other_ldflags(
    settings: Dict[str, BuildSetting],
    platform: ApplePlatform,
    project_info: ProjectInfo,
    build_cfg: str,
    link_flags,
    dep_targets: List[TargetInfo],
    symroot_rel: str,
) -> None:
    for variant in _build_variants(platform, project_info, build_cfg):
        flags: List[str] = []
        if link_flags:
            flags.extend(resolve_conditionals(variant.config, link_flags))
        for dep_ti in dep_targets:
            dep_dir = _variant_product_dir(variant, dep_ti, build_cfg, symroot_rel)
            filename = os.path.basename(
                get_target_output_path(dep_ti, variant.config, symroot_rel)
            )
            flags.append(f"$(SRCROOT)/{os.path.join(dep_dir, filename)}")
        if flags:
            settings[f"OTHER_LDFLAGS[{variant.selector}]"] = BuildSetting(value=flags)


def _infoplist_scalar(value) -> SettingValue:
    if isinstance(value, bool):
        return YesNo.YES if value else YesNo.NO
    return str(value)


# Flatten one info_plist key/value into INFOPLIST_KEY_* build settings (Xcode
# generates the plist from these; GENERATE_INFOPLIST_FILE=YES). The prefix grows
# with each nesting level joined by "_", matching Xcode's convention (e.g.
# UILaunchScreen.UIColorName -> INFOPLIST_KEY_UILaunchScreen_UIColorName).
#   - scalar/bool -> INFOPLIST_KEY_<prefix> = value
#   - non-empty dict -> recurse into each sub-key
#   - empty dict -> INFOPLIST_KEY_<prefix>_Generation = YES (the only way to
#     express an empty dict through flat settings; Apple's documented escape
#     hatch, e.g. UILaunchScreen={} -> INFOPLIST_KEY_UILaunchScreen_Generation)
#   - list -> space-joined scalars (Xcode's list form for INFOPLIST_KEY_)
def _emit_infoplist_key(settings: Dict[str, BuildSetting], prefix: str, value) -> None:
    if isinstance(value, dict):
        if not value:
            settings[f"INFOPLIST_KEY_{prefix}_Generation"] = BuildSetting(
                value=YesNo.YES
            )
            return
        for sub_key in sorted(value):
            _emit_infoplist_key(settings, f"{prefix}_{sub_key}", value[sub_key])
    elif isinstance(value, list):
        # Xcode's INFOPLIST_KEY_ array form is a space-joined list of strings
        # (e.g. UISupportedInterfaceOrientations); elements are always strings.
        settings[f"INFOPLIST_KEY_{prefix}"] = BuildSetting(
            value=" ".join(str(v) for v in value)
        )
    else:
        settings[f"INFOPLIST_KEY_{prefix}"] = BuildSetting(
            value=_infoplist_scalar(value)
        )


# Emit the Info.plist + bundle build settings for an AppleApplication. Most keys
# become INFOPLIST_KEY_* (Xcode generates the plist). A few keys are consumed
# into their own build settings instead, because Xcode derives the plist key
# from the setting (re-emitting would double it) or they name the product:
#   - the platform's min-OS plist key -> *_DEPLOYMENT_TARGET (A6)
#   - CFBundleExecutable -> EXECUTABLE_NAME, CFBundleIdentifier -> PRODUCT_BUNDLE_IDENTIFIER
# device family comes from the bundle's device_families field (A7), not plist.
def _emit_infoplist_settings(
    settings: Dict[str, BuildSetting],
    platform: ApplePlatform,
    target: AppleApplication,
    plist_dict: dict,
    default_executable: str,
) -> None:
    validate_resolved_info_plist(target.name, plist_dict)
    consumed = {
        platform.plist_version_key,
        "CFBundleExecutable",
        "CFBundleIdentifier",
    }

    settings["GENERATE_INFOPLIST_FILE"] = BuildSetting(value=YesNo.YES)
    for key in sorted(plist_dict):
        if key not in consumed:
            _emit_infoplist_key(settings, key, plist_dict[key])

    if platform.plist_version_key in plist_dict:
        settings[platform.deploy_setting] = BuildSetting(
            value=str(plist_dict[platform.plist_version_key])
        )

    settings["EXECUTABLE_NAME"] = BuildSetting(
        value=str(plist_dict.get("CFBundleExecutable", default_executable))
    )
    if "CFBundleIdentifier" in plist_dict:
        settings["PRODUCT_BUNDLE_IDENTIFIER"] = BuildSetting(
            value=str(plist_dict["CFBundleIdentifier"])
        )

    # Device family (A7): from the bundle's device_families field, or the
    # platform default. Xcode writes UIDeviceFamily into the plist from this.
    # A platform without a device-family concept (e.g. macOS) must not be given
    # explicit device_families.
    explicit_family = target.targeted_device_family()
    if explicit_family and platform.default_device_families is None:
        raise ValueError(
            f"AppleApplication '{target.name}' sets device_families, but platform "
            f"'{platform.name}' has no device families"
        )
    device_family = explicit_family or platform.default_device_families
    if device_family:
        settings["TARGETED_DEVICE_FAMILY"] = BuildSetting(value=device_family)


def create_target(
    target_info: TargetInfo,
    project_info: ProjectInfo,
    file_ref_registry: Dict[str, PBXFileReference],
    symroot_rel: str,
) -> TargetResult:
    # Create groups for file organization
    # Use GROUP sourceTree without path for virtual organizational groups
    # (prevents Xcode from showing red "missing folder" indicators)
    full_name = target_full_name(target_info.package, target_info.target)
    target_group = PBXGroup(
        name=target_info.target.name,
        sourceTree=SourceTree.GROUP,
        children=[],
        group_id=f"target:{full_name}",
    )
    sources_group = PBXGroup(
        name="Sources",
        sourceTree=SourceTree.GROUP,
        children=[],
        group_id=f"sources:{full_name}",
    )
    headers_group = PBXGroup(
        name="Headers",
        sourceTree=SourceTree.GROUP,
        children=[],
        group_id=f"headers:{full_name}",
    )
    resources_group = PBXGroup(
        name="Resources",
        sourceTree=SourceTree.GROUP,
        children=[],
        group_id=f"resources:{full_name}",
    )
    target_group.children.extend(
        [
            Reference(sources_group.id, "Sources"),
            Reference(headers_group.id, "Headers"),
            Reference(resources_group.id, "Resources"),
        ]
    )

    # Create file references and build files for sources
    source_refs = []
    source_build_files = []

    # Only include this target's own sources (not dependencies)
    for src in target_info.sources:
        # Make paths relative to workspace root
        src_path = os.path.relpath(src, str(project_info.workspace_root))
        _, ext = os.path.splitext(src.lower())

        # Check if file reference already exists
        if src_path not in file_ref_registry:
            file_ref = PBXFileReference(
                name=os.path.basename(src),
                path=src_path,
                sourceTree=SourceTree.SOURCE_ROOT,
                fileType=FileType.from_extension(ext),
            )
            file_ref_registry[src_path] = file_ref
        else:
            file_ref = file_ref_registry[src_path]

        source_refs.append(file_ref)
        sources_group.children.append(Reference(file_ref.id))

        # Only add compilable files to the build phase
        if ext in COMPILABLE_EXTENSIONS:
            build_file = PBXBuildFile(
                fileRef=Reference(file_ref.id),
                name=os.path.basename(src),
                target_name=full_name,
            )
            source_build_files.append(build_file)

    # Create file references for headers (for IDE navigation only, not built)
    for hdr in target_info.headers:
        # Make paths relative to workspace root
        hdr_path = os.path.relpath(hdr, str(project_info.workspace_root))

        # Check if file reference already exists
        if hdr_path not in file_ref_registry:
            file_ref = PBXFileReference(
                name=os.path.basename(hdr),
                path=hdr_path,
                sourceTree=SourceTree.SOURCE_ROOT,
                fileType=FileType.from_extension(os.path.splitext(hdr)[1]),
            )
            file_ref_registry[hdr_path] = file_ref
        else:
            file_ref = file_ref_registry[hdr_path]

        headers_group.children.append(Reference(file_ref.id))

    # Resources come from file_groups as (src, dst) pairs (dst = path within the
    # bundle's resources dir). Root-level files use the standard Copy Bundle
    # Resources phase; files in subdirectories use a Copy Files phase per subdir
    # (dstPath) so layout is preserved -- the resources phase would flatten them.
    resource_build_files: List[PBXBuildFile] = []
    resource_copy_files: Dict[str, List[PBXBuildFile]] = defaultdict(list)
    for src, dst in target_info.resources:
        resource_path = os.path.relpath(src, str(project_info.workspace_root))
        _, ext = os.path.splitext(src.lower())
        if resource_path not in file_ref_registry:
            file_ref = PBXFileReference(
                name=os.path.basename(src),
                path=resource_path,
                sourceTree=SourceTree.SOURCE_ROOT,
                fileType=FileType.from_extension(ext),
            )
            file_ref_registry[resource_path] = file_ref
        else:
            file_ref = file_ref_registry[resource_path]
        resources_group.children.append(Reference(file_ref.id))
        subdir = os.path.dirname(dst)
        build_file = PBXBuildFile(
            fileRef=Reference(file_ref.id),
            name=os.path.basename(src),
            target_name=full_name if not subdir else f"{full_name}:resources:{subdir}",
        )
        if subdir:
            resource_copy_files[subdir].append(build_file)
        else:
            resource_build_files.append(build_file)

    # Create product reference - path includes package to ensure uniqueness.
    # Derive filename from shared artifact logic to avoid duplicating naming rules.
    product_config = bake_config(
        project_info.base_config,
        architecture=list(str_iter(project_info.base_config.architecture))[0],
        build_config=list(str_iter(project_info.base_config.build_config))[0],
    )
    product_filename = get_target_artifact_filename(
        config=product_config,
        package_name=target_info.package.name,
        target=target_info.target,
    )
    if isinstance(target_info.target, CCLibrary):
        product_type = FileType.ARCHIVE
    elif isinstance(target_info.target, AppleApplication):
        product_type = FileType.APP
    elif isinstance(target_info.target, MetalLibrary):
        product_type = FileType.METAL_LIBRARY
    else:
        product_type = FileType.EXECUTABLE
    product_path = f"{target_info.package.name}/{product_filename}"
    product_ref = PBXFileReference(
        name=target_info.target.name,
        path=product_path,
        sourceTree=SourceTree.SOURCE_ROOT,
        fileType=product_type,
    )

    # Each target compiles only its own source files
    all_source_build_files = sorted(source_build_files, key=lambda bf: bf.id)

    # Create build phases
    sources_phase = PBXSourcesBuildPhase(
        files=[Reference(bf.id) for bf in all_source_build_files],
        target_name=full_name,
    )

    # Create frameworks phase for dependencies
    frameworks_phase = PBXFrameworksBuildPhase(files=[], target_name=full_name)
    resources_phase = PBXResourcesBuildPhase(
        files=[
            Reference(bf.id)
            for bf in sorted(resource_build_files, key=lambda bf: bf.id)
        ],
        target_name=full_name,
    )
    # One Copy Files (Resources) phase per destination subdirectory; dstPath places
    # each group under Resources/<subdir>, preserving the file_group layout.
    resource_copy_phases = [
        PBXCopyFilesBuildPhase(
            files=[Reference(bf.id) for bf in sorted(bfs, key=lambda bf: bf.id)],
            dstPath=subdir,
            dstSubfolderSpec=DstSubfolderSpec.RESOURCES,
            target_name=f"{full_name}:resources:{subdir}",
        )
        for subdir, bfs in sorted(resource_copy_files.items())
    ]
    resource_copy_build_files = [
        bf for bfs in resource_copy_files.values() for bf in bfs
    ]

    # Create configurations - one per build config per target
    target_configs = []

    # Compute per-project build roots to keep intermediates out of workspace root
    project_stem = Path(project_info.base_config.build_root).stem
    build_root_dir = os.path.dirname(project_info.base_config.build_root)
    objroot_rel = os.path.join(build_root_dir, ".xcode-obj", project_stem)
    symroot_rel = os.path.join(build_root_dir, ".xcode-sym", project_stem)

    # Resolve the effective compile target once. For AppleApplication, this is the
    # wrapped binary (so the .app's compile/link settings match the binary it wraps).
    effective_target: Union[CCBinary, CCLibrary, SwiftBinary, SwiftLibrary, None]
    if isinstance(target_info.target, AppleApplication):
        _, effective_target = target_info.target.resolve_binary_target(
            project_info.workspace, target_info.package
        )
    elif isinstance(
        target_info.target, (CCBinary, CCLibrary, SwiftBinary, SwiftLibrary)
    ):
        effective_target = target_info.target
    else:
        effective_target = None

    apple_platform = APPLE_PLATFORMS[project_info.base_config.platform]

    for build_cfg in str_iter(project_info.base_config.build_config):
        # Start with empty settings; do not inject defaults
        settings: Dict[str, BuildSetting] = {}

        # Use exact user config names (don't force Debug/Release)
        config_name = str(build_cfg)

        target_temp_dir = f"$(OBJROOT)/$(PROJECT_NAME).build/$(CONFIGURATION)/{target_info.package.name}/{target_info.target.name}.build"

        # Basic build settings derived from workspace config
        settings.update(
            {
                "SDKROOT": BuildSetting(value=apple_platform.sdkroot),
                "ARCHS": BuildSetting(
                    value=[
                        str(a) for a in str_iter(project_info.base_config.architecture)
                    ]
                ),
                # Ensure Xcode build intermediates live under Out/build
                "BUILD_DIR": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "SHARED_PRECOMPS_DIR": BuildSetting(
                    value=f"$(OBJROOT)/SharedPrecompiledHeaders"
                ),
                # Per-target temp dir includes package path to avoid case-insensitive collisions
                "TARGET_TEMP_DIR": BuildSetting(value=target_temp_dir),
                # Xcode compatibility: disable legacy user paths headermap, enable separate headermaps
                "ALWAYS_SEARCH_USER_PATHS": BuildSetting(value=YesNo.NO),
                "ALWAYS_USE_SEPARATE_HEADERMAPS": BuildSetting(value=YesNo.YES),
            }
        )

        # Code signing. A non-simulator (device/desktop) SDK signs; simulator
        # SDKs never do (Xcode skips signing for them regardless). A bundle may
        # carry a development team for automatic device signing.
        settings.update(_signing_settings(apple_platform, target_info))

        # Build directories. A single-SDK platform (macos) keeps the per-arch
        # layout. A multi-SDK platform (ios) builds one project for several SDKs,
        # so intermediates and products are separated by SDK via [sdk=...]
        # conditional settings (the device SDK product lands at the user's
        # output_path; simulator products, never redistributed, go to
        # intermediates) — switching destinations never collides or invalidates.
        settings.update(
            _build_dir_settings(
                apple_platform,
                target_info,
                project_info,
                build_cfg,
                objroot_rel,
                symroot_rel,
            )
        )

        # For each architecture, create a conditional setting
        for arch in str_iter(project_info.base_config.architecture):
            # Create a baked config for this specific architecture and build_config
            arch_config = bake_config(
                project_info.base_config, architecture=arch, build_config=build_cfg
            )

            # Add include paths for this architecture
            include_paths = get_target_include_paths(
                target_info,
                arch_config,
                project_info,
            )
            if include_paths:
                settings[f"HEADER_SEARCH_PATHS[arch={arch}]"] = BuildSetting(
                    value=[f"$(SRCROOT)/{p}" for p in include_paths]
                )

            # Add target-specific compile flags (C and C++) — skip for Swift effective targets
            if isinstance(effective_target, (CCBinary, CCLibrary)):
                compile_target: Union[CCBinary, CCLibrary] = effective_target
                c_flags = (
                    resolve_conditionals(arch_config, compile_target.c_flags)
                    if compile_target.c_flags
                    else []
                )
                cxx_flags = (
                    resolve_conditionals(arch_config, compile_target.cxx_flags)
                    if compile_target.cxx_flags
                    else []
                )

                # Move -mmacosx-version-min=X into MACOSX_DEPLOYMENT_TARGET to prevent Xcode override warnings
                def extract_macos_min(
                    flags: List[str],
                ) -> Tuple[List[str], Optional[str]]:
                    min_ver: Optional[str] = None
                    kept: List[str] = []
                    for f in flags:
                        if f.startswith("-mmacosx-version-min="):
                            min_ver = f.split("=", 1)[1]
                        else:
                            kept.append(f)
                    return kept, min_ver

                c_flags, min_c = extract_macos_min(c_flags)
                cxx_flags, min_cxx = extract_macos_min(cxx_flags)
                min_ver = min_c or min_cxx
                if min_ver:
                    settings["MACOSX_DEPLOYMENT_TARGET"] = BuildSetting(value=min_ver)

                # Parse known flags into Xcode settings, pass unknown flags through
                # Combine c_flags and cxx_flags for settings extraction
                all_flags = c_flags + cxx_flags
                parsed_settings, _ = parse_compiler_flags(all_flags)
                for setting_name, setting_value in parsed_settings.items():
                    # Only set once (not per-arch) for language standards, etc.
                    if setting_name not in settings:
                        settings[setting_name] = BuildSetting(value=setting_value)

                # Unknown flags pass through to OTHER_CFLAGS/OTHER_CPLUSPLUSFLAGS
                _, c_remaining = parse_compiler_flags(c_flags)
                _, cxx_remaining = parse_compiler_flags(cxx_flags)

                if c_remaining:
                    settings[f"OTHER_CFLAGS[arch={arch}]"] = BuildSetting(
                        value=c_remaining
                    )
                if cxx_remaining:
                    settings[f"OTHER_CPLUSPLUSFLAGS[arch={arch}]"] = BuildSetting(
                        value=cxx_remaining
                    )

                # Add preprocessor defines
                defines: List[str] = []
                # Target's own defines
                if isinstance(compile_target, CCLibrary):
                    if compile_target.public_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, compile_target.public_defines
                            )
                        )
                    if compile_target.private_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, compile_target.private_defines
                            )
                        )
                else:
                    if compile_target.private_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, compile_target.private_defines
                            )
                        )
                # Add public defines from all dependencies (for both libraries and binaries)
                for pkg, dep_target in project_info.workspace.all_dependencies(
                    target_info.package, target_info.target
                ):
                    if isinstance(dep_target, CCLibrary) and dep_target.public_defines:
                        defines.extend(
                            resolve_conditionals(arch_config, dep_target.public_defines)
                        )
                if defines:
                    # Deduplicate while preserving order
                    seen_def = set()
                    ordered_defs: List[str] = []
                    for d in defines:
                        if d not in seen_def:
                            seen_def.add(d)
                            ordered_defs.append(d)
                    settings[f"GCC_PREPROCESSOR_DEFINITIONS[arch={arch}]"] = (
                        BuildSetting(value=ordered_defs)
                    )

                # Add linker flags for executable targets. _emit_other_ldflags
                # enumerates all build variants itself (per-arch on macOS, per-SDK
                # on iOS), so it is variant-complete; the single-arch invariant
                # means this runs once.
                if isinstance(target_info.target, CCBinary):
                    # Explicit paths to dependent libraries (avoids -l collisions).
                    # Reversed for correct link order (dependents before dependencies).
                    dep_targets = _ordered_link_deps(
                        target_info, project_info, (CCLibrary,)
                    )
                    _emit_other_ldflags(
                        settings,
                        apple_platform,
                        project_info,
                        build_cfg,
                        target_info.target.link_flags,
                        dep_targets,
                        symroot_rel,
                    )
                elif isinstance(target_info.target, AppleApplication):
                    _, app_binary = target_info.target.resolve_binary_target(
                        project_info.workspace, target_info.package
                    )
                    dep_targets = _ordered_link_deps(
                        target_info, project_info, (CCLibrary,)
                    )
                    _emit_other_ldflags(
                        settings,
                        apple_platform,
                        project_info,
                        build_cfg,
                        app_binary.link_flags,
                        dep_targets,
                        symroot_rel,
                    )

            elif isinstance(effective_target, (SwiftBinary, SwiftLibrary)):
                swift_target = effective_target

                # Pass user-provided swift flags through to swiftc
                user_swift_flags = list(
                    str_iter(
                        resolve_conditionals(arch_config, swift_target.swift_flags)
                    )
                )

                # For every swift_cc_module in transitive deps, pass its modulemap to
                # swiftc's embedded clang. The cc_library include paths come via
                # HEADER_SEARCH_PATHS (Xcode also forwards those as -Xcc -I to swiftc).
                xcc_flags: List[str] = []
                for dep_pkg, dep_target in project_info.workspace.all_dependencies(
                    target_info.package, target_info.target
                ):
                    if isinstance(dep_target, SwiftCcModule):
                        for modmap_abs in dep_target.module_maps:
                            modmap_rel = os.path.relpath(
                                modmap_abs, str(project_info.workspace_root)
                            )
                            xcc_flags += [
                                "-Xcc",
                                f"-fmodule-map-file=$(SRCROOT)/{modmap_rel}",
                            ]

                other_swift = user_swift_flags + xcc_flags
                if other_swift:
                    settings[f"OTHER_SWIFT_FLAGS[arch={arch}]"] = BuildSetting(
                        value=other_swift
                    )

                if swift_target.cxx_interop:
                    settings["SWIFT_OBJC_INTEROP_MODE"] = BuildSetting(value="objcxx")

                # Link flags: user-provided + transitive cc/swift dep .a files
                if isinstance(swift_target, SwiftBinary):
                    dep_targets = _ordered_link_deps(
                        target_info, project_info, (CCLibrary, SwiftLibrary)
                    )
                    _emit_other_ldflags(
                        settings,
                        apple_platform,
                        project_info,
                        build_cfg,
                        swift_target.link_flags,
                        dep_targets,
                        symroot_rel,
                    )

        # Swift target-level settings (not per-arch). Applies to direct swift_library/
        # swift_binary targets and to AppleApplications wrapping a swift_binary.
        if isinstance(effective_target, (SwiftBinary, SwiftLibrary)):
            settings["SWIFT_VERSION"] = BuildSetting(value="5.0")
            if isinstance(effective_target, SwiftLibrary):
                settings["DEFINES_MODULE"] = BuildSetting(value=YesNo.YES)
                settings["PRODUCT_MODULE_NAME"] = BuildSetting(
                    value=effective_target.name
                )
                if effective_target.swift_header:
                    settings["SWIFT_OBJC_INTERFACE_HEADER_NAME"] = BuildSetting(
                        value=effective_target.swift_header
                    )
            elif isinstance(target_info.target, AppleApplication):
                # Apple bundle wrapping a swift_binary: the .app's PRODUCT_NAME equals
                # the wrapped binary's PRODUCT_NAME (it IS that binary inside the
                # bundle), so the Swift module name would also collide. Rename the
                # ".app" suffix to "_app_bundle" so the .app's .swiftmodule is
                # clearly distinct from the wrapped binary's.
                app_name = target_info.target.name
                if app_name.endswith(".app"):
                    module_name = app_name[: -len(".app")] + "_app_bundle"
                else:
                    module_name = app_name.replace(".", "_").replace("-", "_")
                settings["PRODUCT_MODULE_NAME"] = BuildSetting(value=module_name)

        if isinstance(target_info.target, AppleApplication):
            _, dep_binary = target_info.target.resolve_binary_target(
                project_info.workspace, target_info.package
            )
            plist_config = bake_config(
                project_info.base_config,
                architecture=list(str_iter(project_info.base_config.architecture))[0],
                build_config=build_cfg,
            )
            plist_dict = resolve_conditionals(
                plist_config, target_info.target.info_plist
            )
            _emit_infoplist_settings(
                settings,
                apple_platform,
                target_info.target,
                plist_dict,
                dep_binary.name,
            )

        # Derive product naming from resolved artifact filename to avoid assuming
        # any relation between target.name and output artifact naming.
        settings["PRODUCT_NAME"] = BuildSetting(value=Path(product_filename).stem)
        settings["FULL_PRODUCT_NAME"] = BuildSetting(value=product_filename)
        if isinstance(target_info.target, MetalLibrary):
            # A com.apple.product-type.metal-library target: its product is a bare
            # <PRODUCT_NAME>.metallib file (no wrapper). Phase 0 (Xcode 26.5) proved
            # SDKROOT + PRODUCT_NAME suffice. Pass user metal_flags to the Metal
            # compiler verbatim (no magic MTL_* defaults).
            metal_flags = list(
                str_iter(
                    resolve_conditionals(
                        project_info.base_config, target_info.target.metal_flags
                    )
                )
            )
            if metal_flags:
                settings["MTL_COMPILER_FLAGS"] = BuildSetting(value=metal_flags)
        elif not isinstance(target_info.target, AppleApplication):
            settings["EXECUTABLE_NAME"] = BuildSetting(value=product_filename)

        target_configs.append(
            XCBuildConfiguration(
                name=config_name,
                buildSettings=settings,
                owner=full_name,
            )
        )

    # Create configuration list
    config_list = XCConfigurationList(
        buildConfigurations=[Reference(c.id) for c in target_configs],
        defaultConfigurationName=target_configs[0].name,
        owner=full_name,
    )

    # Create target - use full name for uniqueness
    target = PBXNativeTarget(
        name=full_name,
        productType=target_info.product_type,
        buildPhases=[
            Reference(sources_phase.id),
            Reference(frameworks_phase.id),
            Reference(resources_phase.id),
            *[Reference(p.id) for p in resource_copy_phases],
        ],
        buildConfigurationList=Reference(config_list.id),
        productReference=Reference(product_ref.id),
        productName=target_info.target.name,
        dependencies=[],  # Add empty dependencies list for now
    )

    return TargetResult(
        target=target,
        file_references=[
            product_ref
        ],  # Only return product ref, others are in registry
        groups=[target_group, sources_group, headers_group, resources_group],
        build_files=source_build_files
        + resource_build_files
        + resource_copy_build_files,  # Headers not in build files
        build_phases=[
            sources_phase,
            frameworks_phase,
            resources_phase,
            *resource_copy_phases,
        ],
        configurations=target_configs,
        config_list=config_list,
    )


def generate_xcode_project(config: Config, workspace: Workspace) -> XcodeProject:
    # Temp Hack: artifact paths are intended to be architecture-specific
    # (e.g. .../.artifacts/arm64/... vs .../.artifacts/x86_64/...), but in
    # multi-arch generation Xcode can switch/merge architecture outputs without
    # targeting the matching path for each architecture.
    # This can place universal or wrong-arch outputs in a single-arch path and
    # then cause link steps to look for artifacts in the other arch path.
    # TODO: Re-enable multiple architectures only after generator output paths
    # and build settings enforce strict single-arch outputs per invocation.
    arch_list = list(str_iter(config.architecture))
    assert len(arch_list) == 1, (
        "xcode generator currently requires exactly one configured architecture; "
        f"got {arch_list!r}"
    )

    # For Xcode's build matrix, we need to handle configs and architectures separately
    # We'll use the original config's build_config and architecture lists
    project_info = ProjectInfo.gather(workspace, config, [config])

    # Create and return project
    return create_xcode_project(project_info)
