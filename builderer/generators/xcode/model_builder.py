# Xcode project model builder.
#
# This module provides functionality to convert a builderer target into an Xcode project model.
# It extracts information from the workspace and converts it to the appropriate Xcode project model
# structures defined in model.py.

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import os
from dataclasses import dataclass, field

from builderer import Config
from builderer.details.package import Package
from builderer.details.targets.target import BuildTarget
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.workspace import Workspace, target_full_name
from builderer.details.variable_expansion import resolve_conditionals, bake_config
from builderer.details.as_iterator import str_iter
from builderer.generators.xcode.model import (
    BuildSetting,
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
    product_type: ProductType
    file_type: FileType

    @staticmethod
    def from_target(
        base_config: Config,
        package: Package,
        target: BuildTarget,
    ) -> "TargetInfo":
        sources: List[str] = []
        headers: List[str] = []

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

            sources = list(source_set)
            headers = list(header_set)

            # Determine product type and file type
            if isinstance(target, CCLibrary):
                product_type = ProductType.STATIC_LIBRARY
                file_type = FileType.EXECUTABLE  # Static libraries use EXECUTABLE type
            else:
                product_type = ProductType.TOOL
                file_type = FileType.EXECUTABLE
        else:
            raise ValueError(f"Unsupported target type: {type(target)}")

        return TargetInfo(
            target=target,
            package=package,
            sources=sources,
            headers=headers,
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
    ) -> "ProjectInfo":
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
                package=package,
                target=target,
            )

        # Second pass: gather dependencies
        for full_name, target_info in targets.items():
            deps = set()
            if isinstance(target_info.target, (CCBinary, CCLibrary)):
                for pkg, dep_target in workspace.all_dependencies(
                    target_info.package, target_info.target
                ):
                    if isinstance(dep_target, CCLibrary):
                        deps.add(target_full_name(pkg, dep_target))
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
    target = target_info.target
    # User-provided path takes precedence
    if target.output_path is not None:
        return resolve_conditionals(config=config, value=target.output_path)
    # Generate path: {symroot_rel}/{build_config}/{package}/{filename}
    if isinstance(target, CCLibrary):
        product_filename = f"lib{target.name}.a"
    else:
        product_filename = target.name
    return f"{symroot_rel}/{config.build_config}/{target_info.package.name}/{product_filename}"


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
    # Sort paths by depth (parents before children)
    sorted_paths = sorted(all_paths, key=lambda p: len(p.parts))
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

    # Create project-level configuration list - one config per build config
    project_configs = []
    for build_cfg in str_iter(project_info.base_config.build_config):
        # Start with empty settings; do not inject defaults
        settings: Dict[str, BuildSetting] = {}
        # Relocate intermediates under Out/build (CONFIGURATION_BUILD_DIR set per-target)
        settings.update(
            {
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
    for full_name, target_info in project_info.targets.items():
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
    for full_name, deps in project_info.dependencies.items():
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

    return XcodeProject(
        fileReferences=list(file_ref_registry.values())
        + list(product_ref_by_target.values()),
        groups=groups,
        buildFiles=build_files,
        buildPhases=build_phases,
        nativeTargets=native_targets,
        project=project,
        buildConfigurations=build_configurations,
        configurationLists=configuration_lists,
        targetDependencies=target_dependencies,
        containerItemProxies=container_item_proxies,
    )


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
    target_group.children.extend(
        [
            Reference(sources_group.id, "Sources"),
            Reference(headers_group.id, "Headers"),
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

    # Create product reference - path includes package to ensure uniqueness
    if isinstance(target_info.target, CCLibrary):
        product_filename = f"lib{target_info.target.name}.a"
        product_type = FileType.ARCHIVE
    else:
        product_filename = target_info.target.name
        product_type = FileType.EXECUTABLE
    product_path = f"{target_info.package.name}/{product_filename}"
    product_ref = PBXFileReference(
        name=target_info.target.name,
        path=product_path,
        sourceTree=SourceTree.SOURCE_ROOT,
        fileType=product_type,
    )

    # Each target compiles only its own source files
    all_source_build_files = list(source_build_files)

    # Create build phases
    sources_phase = PBXSourcesBuildPhase(
        files=[Reference(bf.id) for bf in all_source_build_files],
        target_name=full_name,
    )

    # Create frameworks phase for dependencies
    frameworks_phase = PBXFrameworksBuildPhase(files=[], target_name=full_name)

    # Create configurations - one per build config per target
    target_configs = []

    # Compute per-project build roots to keep intermediates out of workspace root
    project_stem = Path(project_info.base_config.build_root).stem
    build_root_dir = os.path.dirname(project_info.base_config.build_root)
    objroot_rel = os.path.join(build_root_dir, ".xcode-obj", project_stem)
    symroot_rel = os.path.join(build_root_dir, ".xcode-sym", project_stem)

    for build_cfg in str_iter(project_info.base_config.build_config):
        # Start with empty settings; do not inject defaults
        settings: Dict[str, BuildSetting] = {}

        # Use exact user config names (don't force Debug/Release)
        config_name = str(build_cfg)

        target_temp_dir = f"$(OBJROOT)/$(PROJECT_NAME).build/$(CONFIGURATION)/{target_info.package.name}/{target_info.target.name}.build"

        # Basic build settings derived from workspace config
        settings.update(
            {
                "ARCHS": BuildSetting(
                    value=[
                        str(a) for a in str_iter(project_info.base_config.architecture)
                    ]
                ),
                # Ensure Xcode build intermediates live under Out/build
                "BUILD_DIR": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "OBJROOT": BuildSetting(value=f"$(SRCROOT)/{objroot_rel}"),
                "SYMROOT": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "SHARED_PRECOMPS_DIR": BuildSetting(
                    value=f"$(OBJROOT)/SharedPrecompiledHeaders"
                ),
                # Per-target temp dir includes package path to avoid case-insensitive collisions
                "TARGET_TEMP_DIR": BuildSetting(value=target_temp_dir),
                # Xcode compatibility: disable legacy user paths headermap, enable separate headermaps
                "ALWAYS_SEARCH_USER_PATHS": BuildSetting(value=YesNo.NO),
                "ALWAYS_USE_SEPARATE_HEADERMAPS": BuildSetting(value=YesNo.YES),
                # Avoid ad-hoc code signing flags leaking into tool invocations
                "CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
                "AD_HOC_CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
            }
        )

        # Determine CONFIGURATION_BUILD_DIR for each architecture
        arch_output_dirs: Dict[str, str] = {}
        for arch in str_iter(project_info.base_config.architecture):
            baked_cfg = bake_config(
                project_info.base_config, architecture=arch, build_config=build_cfg
            )
            output_path = get_target_output_path(target_info, baked_cfg, symroot_rel)
            output_dir = os.path.dirname(output_path)
            arch_output_dirs[arch] = f"$(SRCROOT)/{output_dir}"

        # Set base value (used for universal binary steps) and per-arch values
        first_dir = next(iter(arch_output_dirs.values()))
        settings["CONFIGURATION_BUILD_DIR"] = BuildSetting(value=first_dir)
        for arch, output_dir in arch_output_dirs.items():
            settings[f"CONFIGURATION_BUILD_DIR[arch={arch}]"] = BuildSetting(
                value=output_dir
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

            # Add target-specific compile flags (C and C++)
            if isinstance(target_info.target, (CCBinary, CCLibrary)):
                c_flags = (
                    resolve_conditionals(arch_config, target_info.target.c_flags)
                    if target_info.target.c_flags
                    else []
                )
                cxx_flags = (
                    resolve_conditionals(arch_config, target_info.target.cxx_flags)
                    if target_info.target.cxx_flags
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
                if isinstance(target_info.target, CCLibrary):
                    if target_info.target.public_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, target_info.target.public_defines
                            )
                        )
                    if target_info.target.private_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, target_info.target.private_defines
                            )
                        )
                elif isinstance(target_info.target, CCBinary):
                    if target_info.target.private_defines:
                        defines.extend(
                            resolve_conditionals(
                                arch_config, target_info.target.private_defines
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

                # Add linker flags for binaries
                if isinstance(target_info.target, CCBinary):
                    ldflags: List[str] = []

                    # Add user-provided link flags
                    if target_info.target.link_flags:
                        ldflags.extend(
                            resolve_conditionals(
                                arch_config, target_info.target.link_flags
                            )
                        )

                    # Add explicit paths to all dependent libraries (avoids -l collisions)
                    # Reversed for correct link order (dependents before dependencies)
                    for dep_pkg, dep_target in reversed(
                        list(
                            project_info.workspace.all_dependencies(
                                target_info.package, target_info.target
                            )
                        )
                    ):
                        if isinstance(dep_target, CCLibrary) and dep_target.srcs:
                            dep_full_name = target_full_name(dep_pkg, dep_target)
                            dep_target_info = project_info.targets.get(dep_full_name)
                            if dep_target_info:
                                dep_output = get_target_output_path(
                                    dep_target_info, arch_config, symroot_rel
                                )
                                ldflags.append(f"$(SRCROOT)/{dep_output}")

                    if ldflags:
                        settings[f"OTHER_LDFLAGS[arch={arch}]"] = BuildSetting(
                            value=ldflags
                        )

        # Use short target name for product (TARGET_NAME contains full_name with colon, invalid in paths)
        settings["PRODUCT_NAME"] = BuildSetting(value=target_info.target.name)
        if isinstance(target_info.target, CCLibrary):
            settings["EXECUTABLE_PREFIX"] = BuildSetting(value="lib")
            settings["EXECUTABLE_SUFFIX"] = BuildSetting(value=".a")

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
        groups=[target_group, sources_group, headers_group],
        build_files=source_build_files,  # Headers not in build files
        build_phases=[sources_phase, frameworks_phase],
        configurations=target_configs,
        config_list=config_list,
    )


def generate_xcode_project(config: Config, workspace: Workspace) -> XcodeProject:
    # For Xcode's build matrix, we need to handle configs and architectures separately
    # We'll use the original config's build_config and architecture lists
    project_info = ProjectInfo.gather(workspace, config, [config])

    # Create and return project
    return create_xcode_project(project_info)
