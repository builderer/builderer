"""
Xcode project model builder.

This module provides functionality to convert a builderer target into an Xcode project model.
It extracts information from the workspace and converts it to the appropriate Xcode project model
structures defined in model.py.
"""

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
from builderer.details.variable_expansion import resolve_conditionals
from builderer.details.as_iterator import str_iter, str_scalar
from builderer.generators.xcode.model import (
    BuildSetting,
    FileType,
    PBXBuildFile,
    PBXFileReference,
    PBXFrameworksBuildPhase,
    PBXGroup,
    PBXNativeTarget,
    PBXProject,
    PBXResourcesBuildPhase,
    PBXSourcesBuildPhase,
    PBXHeadersBuildPhase,
    PBXCopyFilesBuildPhase,
    PBXShellScriptBuildPhase,
    ProductType,
    Reference,
    SourceTree,
    XCBuildConfiguration,
    XCConfigurationList,
    XcodeObject,
    XcodeProject,
    YesNo,
    DEFAULT_BUILD_SETTINGS,
    PBXTargetDependency,
    PBXContainerItemProxy,
    generate_id,
    ProxyType,
)


@dataclass(frozen=True)
class TargetResult:
    """Result of creating a target."""

    target: PBXNativeTarget
    file_references: List[PBXFileReference]
    groups: List[PBXGroup]
    build_files: List[PBXBuildFile]
    build_phases: List[
        Union[
            PBXSourcesBuildPhase,
            PBXHeadersBuildPhase,
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
    """Immutable information about a target."""

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
        """Create TargetInfo from a target and its configurations.

        Args:
            base_config: The base configuration to resolve conditionals with
            package: The package containing the target
            target: The target to create info for
        """
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
    """Immutable information about the entire project."""

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
        """Gather all project information."""
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
            targets[target.name] = TargetInfo.from_target(
                base_config=base_config,
                package=package,
                target=target,
            )

        # Second pass: gather dependencies
        for target_name, target_info in targets.items():
            deps = set()
            if isinstance(target_info.target, (CCBinary, CCLibrary)):
                for pkg, dep_target in workspace.all_dependencies(
                    target_info.package, target_info.target
                ):
                    if isinstance(dep_target, CCLibrary):
                        deps.add(dep_target.name)
            dependencies[target_name] = deps

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
    """Get include paths for a specific config."""
    # Collect include paths from the target and, for binaries, from dependent libraries
    if isinstance(target_info.target, CCLibrary):
        # For libraries, includes are the same for all configs
        includes_lib: List[str] = []
        # Add target's own include paths
        for inc in target_info.target.public_includes:
            resolved = resolve_conditionals(config, inc)
            if isinstance(resolved, str):
                normalized_path = os.path.normpath(resolved)
                includes_lib.append(normalized_path)
            else:
                for p in resolved:
                    normalized_path = os.path.normpath(str(p))
                    includes_lib.append(normalized_path)
        for inc in target_info.target.private_includes:
            resolved = resolve_conditionals(config, inc)
            if isinstance(resolved, str):
                normalized_path = os.path.normpath(resolved)
                includes_lib.append(normalized_path)
            else:
                for p in resolved:
                    normalized_path = os.path.normpath(str(p))
                    includes_lib.append(normalized_path)
        # Deduplicate and stabilize
        seen_lib = set()
        deduped_includes_lib: List[str] = []
        for path in includes_lib:
            if path not in seen_lib:
                seen_lib.add(path)
                deduped_includes_lib.append(path)
        return deduped_includes_lib
    elif isinstance(target_info.target, CCBinary):
        # For binaries, includes are config-specific
        includes_bin: List[str] = []
        for i in resolve_conditionals(config, target_info.target.private_includes):
            if isinstance(i, str):
                includes_bin.append(os.path.normpath(i))
            else:
                for p in i:
                    includes_bin.append(os.path.normpath(str(p)))

        # Add include paths from dependencies
        for pkg, dep_target in project_info.workspace.all_dependencies(
            target_info.package, target_info.target
        ):
            if isinstance(dep_target, CCLibrary):
                for i in resolve_conditionals(config, dep_target.public_includes):
                    if isinstance(i, str):
                        includes_bin.append(os.path.normpath(i))
                    else:
                        for p in i:
                            includes_bin.append(os.path.normpath(str(p)))
        # Deduplicate and stabilize
        seen_bin = set()
        deduped_includes_bin: List[str] = []
        for path in includes_bin:
            if path not in seen_bin:
                seen_bin.add(path)
                deduped_includes_bin.append(path)
        return deduped_includes_bin
    else:
        raise ValueError(f"Unsupported target type: {type(target_info.target)}")


def get_target_output_path(
    target_info: TargetInfo,
    config: Config,
    project_info: ProjectInfo,
) -> str:
    package = target_info.package
    target = target_info.target
    """Get the output path for a target for a specific configuration."""
    # For explicit output paths, use resolve_conditionals
    if target.output_path is not None:
        # Create a temporary config with the current build_config value
        temp_config = Config(
            platform=config.platform,
            build_config=config.build_config,  # This is already a single value from str_iter
            architecture=config.architecture,
            buildtool=config.buildtool,
            toolchain=config.toolchain,
            sandbox_root=config.sandbox_root,
            build_root=config.build_root,
        )
        output_path = str_scalar(
            resolve_conditionals(config=temp_config, value=target.output_path)
        )
        # Make path relative to project directory
        return os.path.relpath(
            os.path.join(project_info.workspace_root, output_path),
            project_info.project_dir,
        )

    # For implicit output paths, put them in intermediates directory next to the project
    intermediates_dir = os.path.join(
        os.path.dirname(project_info.project_dir),
        f"xcode-obj-{config.platform}-{config.build_config}-{config.architecture}",
        package.name,
        target.name,  # Ensure unique path per target
    )

    # Make path relative to project directory
    intermediates_dir = os.path.relpath(intermediates_dir, project_info.project_dir)

    # For libraries, add lib prefix and .a suffix
    if isinstance(target, CCLibrary):
        return os.path.join(intermediates_dir, f"lib{target.name}.a")
    else:
        return os.path.join(intermediates_dir, target.name)


def create_xcode_project(project_info: ProjectInfo) -> XcodeProject:
    """Create an Xcode project from gathered project information."""
    # Create base project structure
    main_group = PBXGroup(name="", sourceTree=SourceTree.GROUP, children=[])
    products_group = PBXGroup(name="Products", sourceTree=SourceTree.GROUP, children=[])
    main_group.children.append(Reference(products_group.id, "Products"))

    # Optional global overrides from Config (dict of key->value or per-config dict)
    project_overrides = getattr(
        project_info.base_config, "xcode_project_build_settings", None
    )

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
        # Relocate intermediates and built products under Out/build
        settings.update(
            {
                "OBJROOT": BuildSetting(value=f"$(SRCROOT)/{objroot_rel}"),
                "SYMROOT": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "SHARED_PRECOMPS_DIR": BuildSetting(
                    value=f"$(OBJROOT)/SharedPrecompiledHeaders"
                ),
                # Ensure products live under SYMROOT/$(CONFIGURATION)
                "CONFIGURATION_BUILD_DIR": BuildSetting(
                    value="$(SYMROOT)/$(CONFIGURATION)"
                ),
                # Xcode compatibility: disable legacy user paths headermap, enable separate headermaps
                "ALWAYS_SEARCH_USER_PATHS": BuildSetting(value=YesNo.NO),
                "ALWAYS_USE_SEPARATE_HEADERMAPS": BuildSetting(value=YesNo.YES),
                # Avoid ad-hoc code signing flags leaking into tool invocations
                "CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
                "AD_HOC_CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
            }
        )
        # Merge global overrides for this config if provided
        if isinstance(project_overrides, dict):
            for k, v in project_overrides.items():
                # Allow per-config dict: { key: {"debug": [...], "release": [...] } }
                if isinstance(v, dict):
                    if str(build_cfg) in v:
                        settings[k] = BuildSetting(value=v[str(build_cfg)])
                else:
                    settings[k] = BuildSetting(value=v)
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
    groups = [main_group, products_group]
    build_files = []
    build_phases = []
    build_configurations = project_configs  # Start with project configs
    configuration_lists = [project_config_list]
    target_dependencies = []
    container_item_proxies = []
    # Lookups for later wiring
    product_ref_by_target: Dict[str, PBXFileReference] = {}
    frameworks_phase_by_target: Dict[str, PBXFrameworksBuildPhase] = {}

    # First pass: create all targets and their file references
    for target_name, target_info in project_info.targets.items():
        # Skip header-only libraries - they don't need Xcode targets
        if isinstance(target_info.target, CCLibrary) and not target_info.sources:
            continue

        target_result = create_target(target_info, project_info, file_ref_registry)

        native_targets.append(target_result.target)
        file_references.extend(target_result.file_references)
        groups.extend(target_result.groups)
        build_files.extend(target_result.build_files)
        build_phases.extend(target_result.build_phases)
        build_configurations.extend(target_result.configurations)
        configuration_lists.append(target_result.config_list)

        # Add target's main group to project main group
        main_group.children.append(Reference(target_result.groups[0].id, target_name))

        # Add product reference to Products group and record lookups
        product_ref = target_result.file_references[0]
        products_group.children.append(Reference(product_ref.id, target_name))
        product_ref_by_target[target_name] = product_ref
        # Find this target's frameworks phase
        for bp in target_result.build_phases:
            if isinstance(bp, PBXFrameworksBuildPhase):
                frameworks_phase_by_target[target_name] = bp
                break

        # Add target reference to project
        project.targets.append(Reference(target_result.target.id, target_name))

    # Second pass: add dependencies between targets
    for target_name, deps in project_info.dependencies.items():
        # Skip if this target wasn't created (header-only library)
        try:
            target = next(t for t in native_targets if t.name == target_name)
        except StopIteration:
            continue

        for dep_name in deps:
            # Skip if dependency wasn't created (header-only library)
            try:
                dep_target = next(t for t in native_targets if t.name == dep_name)
            except StopIteration:
                continue

            # Create container proxy
            container_proxy = PBXContainerItemProxy(
                containerPortal=project.id,
                proxyType=ProxyType.TARGET_DEPENDENCY,
                remoteGlobalIDString=dep_target.id,
                remoteInfo=dep_name,
            )
            container_item_proxies.append(container_proxy)

            # Create target dependency
            target_dependency = PBXTargetDependency(
                target=dep_target.id,
                targetProxy=Reference(container_proxy.id),
            )
            target_dependencies.append(target_dependency)

            # Add to target's dependencies
            target.dependencies.append(Reference(target_dependency.id))

            # Link the dependent product into the consuming target's Frameworks phase
            if (
                target_name in frameworks_phase_by_target
                and dep_name in product_ref_by_target
            ):
                dep_product_ref = product_ref_by_target[dep_name]
                link_bf = PBXBuildFile(
                    fileRef=Reference(dep_product_ref.id),
                    name=dep_name,
                    target_name=target_name,
                )
                build_files.append(link_bf)
                frameworks_phase = frameworks_phase_by_target[target_name]
                frameworks_phase.files.append(Reference(link_bf.id))

    return XcodeProject(
        fileReferences=list(file_ref_registry.values()),
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
) -> TargetResult:
    """Create a target and all its associated objects."""
    # Create groups for file organization
    target_group = PBXGroup(
        name=target_info.target.name, sourceTree=SourceTree.GROUP, children=[]
    )
    sources_group = PBXGroup(
        name="Sources",
        sourceTree=SourceTree.GROUP,
        children=[],
        path=None,  # No path - this is just an organizational group
        group_id=f"{target_info.target.name}_Sources",  # Make key unique per target
    )
    headers_group = PBXGroup(
        name="Headers",
        sourceTree=SourceTree.GROUP,
        children=[],
        path=None,  # No path - this is just an organizational group
        group_id=f"{target_info.target.name}_Headers",  # Make key unique per target
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

        # Check if file reference already exists
        if src_path not in file_ref_registry:
            file_ref = PBXFileReference(
                name=os.path.basename(src),
                path=src_path,
                sourceTree=SourceTree.SOURCE_ROOT,
                fileType=FileType.from_extension(os.path.splitext(src)[1]),
            )
            file_ref_registry[src_path] = file_ref
        else:
            file_ref = file_ref_registry[src_path]

        source_refs.append(file_ref)
        sources_group.children.append(Reference(file_ref.id))

        build_file = PBXBuildFile(
            fileRef=Reference(file_ref.id),
            name=os.path.basename(src),
            target_name=target_info.target.name,
        )
        source_build_files.append(build_file)

    # Create file references and build files for headers
    header_refs = []
    header_build_files = []

    # Only include this target's own headers (not dependencies)
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

        header_refs.append(file_ref)
        headers_group.children.append(Reference(file_ref.id))

        build_file = PBXBuildFile(
            fileRef=Reference(file_ref.id),
            name=os.path.basename(hdr),
            target_name=target_info.target.name,
        )
        header_build_files.append(build_file)

    # Create product reference in built products dir
    if isinstance(target_info.target, CCLibrary):
        product_filename = f"lib{target_info.target.name}.a"
        product_type = FileType.ARCHIVE
    else:
        product_filename = target_info.target.name
        product_type = FileType.EXECUTABLE
    product_ref = PBXFileReference(
        name=target_info.target.name,
        path=product_filename,
        sourceTree=SourceTree.BUILT_PRODUCTS_DIR,
        fileType=product_type,
    )
    file_ref_registry[product_filename] = product_ref

    # Each target compiles only its own source files
    all_source_build_files = list(source_build_files)

    # Create build phases
    sources_phase = PBXSourcesBuildPhase(
        files=[Reference(bf.id) for bf in all_source_build_files],
        target_name=target_info.target.name,
    )
    headers_phase = PBXHeadersBuildPhase(
        files=[Reference(bf.id) for bf in header_build_files],
        target_name=target_info.target.name,
    )

    # Create frameworks phase for dependencies
    frameworks_phase = PBXFrameworksBuildPhase(
        files=[], target_name=target_info.target.name
    )

    # Create configurations - one per build config per target
    target_configs = []
    # Optional per-target overrides from Config
    target_overrides_global = getattr(
        project_info.base_config, "xcode_target_build_settings", None
    )
    target_overrides_by_name = getattr(
        project_info.base_config, "xcode_target_overrides", None
    )

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

        # Basic build settings derived from workspace config
        settings.update(
            {
                "ARCHS": BuildSetting(
                    value=[
                        str(a) for a in str_iter(project_info.base_config.architecture)
                    ]
                ),
                # Ensure Xcode build intermediates and products live under Out/build
                "BUILD_DIR": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "OBJROOT": BuildSetting(value=f"$(SRCROOT)/{objroot_rel}"),
                "SYMROOT": BuildSetting(value=f"$(SRCROOT)/{symroot_rel}"),
                "SHARED_PRECOMPS_DIR": BuildSetting(
                    value=f"$(OBJROOT)/SharedPrecompiledHeaders"
                ),
                "CONFIGURATION_BUILD_DIR": BuildSetting(
                    value="$(SYMROOT)/$(CONFIGURATION)"
                ),
                # Xcode compatibility: disable legacy user paths headermap, enable separate headermaps
                "ALWAYS_SEARCH_USER_PATHS": BuildSetting(value=YesNo.NO),
                "ALWAYS_USE_SEPARATE_HEADERMAPS": BuildSetting(value=YesNo.YES),
                # Avoid ad-hoc code signing flags leaking into tool invocations
                "CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
                "AD_HOC_CODE_SIGNING_ALLOWED": BuildSetting(value=YesNo.NO),
            }
        )

        # Apply target-level overrides
        def _apply_overrides(overrides: Dict[str, object]):
            for k, v in overrides.items():
                if isinstance(v, dict):
                    if str(build_cfg) in v:
                        settings[k] = BuildSetting(value=v[str(build_cfg)])
                else:
                    # Enforce allowed types for BuildSetting
                    allowed: object
                    if isinstance(v, (str, int, float)):
                        allowed = v
                    elif isinstance(v, list) and all(isinstance(i, str) for i in v):
                        allowed = v  # type: ignore[assignment]
                    elif isinstance(v, YesNo):
                        allowed = v
                    else:
                        allowed = str(v)
                    settings[k] = BuildSetting(value=allowed)  # type: ignore[arg-type]

        if isinstance(target_overrides_global, dict):
            _apply_overrides(target_overrides_global)
        if isinstance(target_overrides_by_name, dict):
            per_target = target_overrides_by_name.get(target_info.target.name)
            if isinstance(per_target, dict):
                _apply_overrides(per_target)

        # No project-structure assumptions: all behavior is driven by flags/defines/includes emitted by rules

        # Create a base config with just the build config
        base_config = Config(
            platform=project_info.base_config.platform,
            build_config=build_cfg,
            architecture=project_info.base_config.architecture,
            buildtool=project_info.base_config.buildtool,
            toolchain=project_info.base_config.toolchain,
            sandbox_root=project_info.base_config.sandbox_root,
            build_root=project_info.base_config.build_root,
        )

        # For each architecture, create a conditional setting
        for arch in str_iter(project_info.base_config.architecture):
            # Create a config with specific architecture
            arch_config = Config(
                platform=project_info.base_config.platform,
                build_config=build_cfg,
                architecture=arch,
                buildtool=project_info.base_config.buildtool,
                toolchain=project_info.base_config.toolchain,
                sandbox_root=project_info.base_config.sandbox_root,
                build_root=project_info.base_config.build_root,
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
                if c_flags:
                    settings[f"OTHER_CFLAGS[arch={arch}]"] = BuildSetting(value=c_flags)
                if cxx_flags:
                    settings[f"OTHER_CPLUSPLUSFLAGS[arch={arch}]"] = BuildSetting(
                        value=cxx_flags
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
                    # Add public defines from dependent libraries
                    for pkg, dep_target in project_info.workspace.all_dependencies(
                        target_info.package, target_info.target
                    ):
                        if (
                            isinstance(dep_target, CCLibrary)
                            and dep_target.public_defines
                        ):
                            defines.extend(
                                resolve_conditionals(
                                    arch_config, dep_target.public_defines
                                )
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

                # Add linker flags from target
                if (
                    isinstance(target_info.target, CCBinary)
                    and target_info.target.link_flags
                ):
                    linkopts = resolve_conditionals(
                        arch_config, target_info.target.link_flags
                    )
                    if linkopts:
                        settings[f"OTHER_LDFLAGS[arch={arch}]"] = BuildSetting(
                            value=linkopts
                        )

        # Ensure correct product naming so Xcode emits proper output filenames and -l<name> during link
        settings["PRODUCT_NAME"] = BuildSetting(value="$(TARGET_NAME)")
        if isinstance(target_info.target, CCLibrary):
            settings["EXECUTABLE_PREFIX"] = BuildSetting(value="lib")
            settings["EXECUTABLE_SUFFIX"] = BuildSetting(value=".a")

        target_configs.append(
            XCBuildConfiguration(
                name=config_name,
                buildSettings=settings,
                owner=target_info.target.name,
            )
        )

    # Create configuration list
    config_list = XCConfigurationList(
        buildConfigurations=[Reference(c.id) for c in target_configs],
        defaultConfigurationName=target_configs[0].name,
        owner=target_info.target.name,
    )

    # Create target
    target = PBXNativeTarget(
        name=target_info.target.name,
        productType=target_info.product_type,
        buildPhases=[
            Reference(sources_phase.id),
            Reference(headers_phase.id),
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
        build_files=[*source_build_files, *header_build_files],
        build_phases=[sources_phase, headers_phase, frameworks_phase],
        configurations=target_configs,
        config_list=config_list,
    )


def generate_xcode_project(config: Config, workspace: Workspace) -> XcodeProject:
    """Generate an Xcode project.

    Args:
        config: The configuration to use.
        workspace: The workspace to generate from.

    Returns:
        The generated XcodeProject.
    """
    # For Xcode's build matrix, we need to handle configs and architectures separately
    # We'll use the original config's build_config and architecture lists
    project_info = ProjectInfo.gather(workspace, config, [config])

    # Create and return project
    return create_xcode_project(project_info)
