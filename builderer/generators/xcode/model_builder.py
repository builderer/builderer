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
from builderer.details.variable_expansion import resolve_conditionals, bake_config
from builderer.details.as_iterator import str_iter
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
class TargetInfo:
    """Immutable information about a target."""

    target: BuildTarget
    package: Package
    sources: List[str]  # Paths relative to workspace root
    headers: List[str]  # Paths relative to workspace root
    output_paths: Dict[str, str]  # config_name -> path relative to project file
    include_paths: Dict[str, List[str]]  # config_name -> paths relative to project file
    product_type: ProductType
    file_type: FileType

    @staticmethod
    def from_target(
        target: BuildTarget,
        package: Package,
        configs: List[Config],
        workspace_root: Path,
        project_dir: Path,
        workspace: Workspace,
    ) -> "TargetInfo":
        """Create TargetInfo from a target and its configurations."""
        sources: List[str] = []
        headers: List[str] = []
        output_paths: Dict[str, str] = {}
        include_paths: Dict[str, List[str]] = {}

        if isinstance(target, (CCBinary, CCLibrary)):
            # Gather sources and headers across all configs
            source_set: Set[str] = set()
            header_set: Set[str] = set()
            for config in configs:
                config_name = str(config.build_config)  # Ensure config name is str
                if isinstance(target, CCLibrary):
                    # For libraries, headers are part of the public interface
                    header_paths = resolve_conditionals(config, target.hdrs)
                    header_set.update(
                        str(p) for p in header_paths
                    )  # Ensure paths are str

                    # Sources are internal implementation
                    source_paths = resolve_conditionals(config, target.srcs)
                    source_set.update(
                        str(p) for p in source_paths
                    )  # Ensure paths are str

                    # Public includes are for dependencies
                    include_paths[config_name] = [
                        os.path.relpath(str(inc), str(project_dir))
                        for inc in target.public_includes
                    ]
                    include_paths[config_name].extend(
                        [
                            os.path.relpath(str(inc), str(project_dir))
                            for inc in target.private_includes
                        ]
                    )
                elif isinstance(target, CCBinary):
                    # For binaries, all sources are implementation
                    source_paths = resolve_conditionals(config, target.srcs)
                    source_set.update(
                        str(p) for p in source_paths
                    )  # Ensure paths are str

                    # Private includes are for this target only
                    include_paths[config_name] = []

                    # Add this target's private includes
                    for i in resolve_conditionals(config, target.private_includes):
                        include_paths[config_name].append(
                            os.path.relpath(
                                str(os.path.join(target.root, i)), str(project_dir)
                            )
                        )

                    # Add include paths from dependencies
                    for pkg, dep_target in workspace.all_dependencies(package, target):
                        if isinstance(dep_target, CCLibrary):
                            # Add public includes from library dependencies
                            for i in resolve_conditionals(
                                config, dep_target.public_includes
                            ):
                                include_paths[config_name].append(
                                    os.path.relpath(
                                        str(os.path.join(dep_target.root, i)),
                                        str(project_dir),
                                    )
                                )

                # Get output path for this config
                output_path = _get_target_output_path(
                    target, config, package, workspace_root, project_dir
                )
                output_paths[config_name] = str(output_path)

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
            output_paths=output_paths,
            include_paths=include_paths,
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
                target=target,
                package=package,
                configs=configs,
                workspace_root=workspace.root,
                project_dir=project_dir,
                workspace=workspace,
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
        )


def _get_target_output_path(
    target: BuildTarget,
    config: Config,
    package: Package,
    workspace_root: Path,
    project_dir: Path,
) -> str:
    """Get the output path for a target for a specific configuration."""
    # For explicit output paths, use resolve_conditionals
    if target.output_path is not None:
        output_path = resolve_conditionals(config=config, value=target.output_path)
        # Make path relative to project directory
        return os.path.relpath(os.path.join(workspace_root, output_path), project_dir)

    # For implicit output paths, put them in intermediates directory next to the project
    intermediates_dir = os.path.join(
        os.path.dirname(project_dir),
        f"{config.platform}-xcode-obj",
        target.name,  # Ensure unique path per target
        str(config.build_config).lower(),  # Ensure string and convert to lower
    )

    # Make path relative to project directory
    intermediates_dir = os.path.relpath(intermediates_dir, project_dir)

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

    # Create project-level configuration list
    project_configs = [
        XCBuildConfiguration(
            name=str(config.build_config),  # Ensure string
            buildSettings={**DEFAULT_BUILD_SETTINGS},
        )
        for config in project_info.configs
    ]
    project_config_list = XCConfigurationList(
        buildConfigurations=[Reference(c.id) for c in project_configs],
        defaultConfigurationName=str(
            project_info.configs[0].build_config
        ),  # Ensure string
    )

    # Create project
    project = PBXProject(
        name=project_info.base_config.build_root,
        buildConfigurationList=Reference(project_config_list.id),
        mainGroup=Reference(main_group.id),
        productRefGroup=Reference(products_group.id),
        targets=[],  # Will be filled in later
    )

    # Process each target
    native_targets = []
    file_references = []
    groups = [main_group, products_group]
    build_files = []
    build_phases = []
    build_configurations = project_configs
    configuration_lists = [project_config_list]
    target_dependencies = []
    container_item_proxies = []

    # First pass: create all targets without dependencies
    for target_name, target_info in project_info.targets.items():
        target_result = create_target(target_info, project_info)

        native_targets.append(target_result.target)
        file_references.extend(target_result.file_references)
        groups.extend(target_result.groups)
        build_files.extend(target_result.build_files)
        build_phases.extend(target_result.build_phases)
        build_configurations.extend(target_result.configurations)
        configuration_lists.append(target_result.config_list)

        # Add target's main group to project main group
        main_group.children.append(Reference(target_result.groups[0].id, target_name))

        # Add target reference to project
        project.targets.append(Reference(target_result.target.id, target_name))

    # Second pass: add dependencies between targets
    for target_name, deps in project_info.dependencies.items():
        target = next(t for t in native_targets if t.name == target_name)
        for dep_name in deps:
            dep_target = next(t for t in native_targets if t.name == dep_name)

            # Create container proxy
            container_proxy = PBXContainerItemProxy(
                containerPortal=project.id,  # Use string ID directly
                proxyType=ProxyType.TARGET_DEPENDENCY,
                remoteGlobalIDString=dep_target.id,
                remoteInfo=dep_name,
            )
            container_item_proxies.append(container_proxy)

            # Create target dependency
            target_dependency = PBXTargetDependency(
                target=dep_target.id,  # Use string ID directly
                targetProxy=Reference(container_proxy.id),
            )
            target_dependencies.append(target_dependency)

            # Add to target's dependencies
            target.dependencies.append(Reference(target_dependency.id))

    return XcodeProject(
        fileReferences=file_references,
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


def create_target(target_info: TargetInfo, project_info: ProjectInfo) -> TargetResult:
    """Create a target and all its associated objects."""
    # Create groups for file organization
    target_group = PBXGroup(
        name=target_info.target.name, sourceTree=SourceTree.GROUP, children=[]
    )
    sources_group = PBXGroup(name="Sources", sourceTree=SourceTree.GROUP, children=[])
    headers_group = PBXGroup(name="Headers", sourceTree=SourceTree.GROUP, children=[])
    target_group.children.extend(
        [
            Reference(sources_group.id, "Sources"),
            Reference(headers_group.id, "Headers"),
        ]
    )

    # Create file references and build files for sources
    source_refs = []
    source_build_files = []
    for src in target_info.sources:
        src_path = os.path.relpath(src, project_info.project_dir)
        file_ref = PBXFileReference(
            name=os.path.basename(src),
            path=src_path,
            sourceTree=SourceTree.SOURCE_ROOT,
            fileType=FileType.from_extension(os.path.splitext(src)[1]),
        )
        source_refs.append(file_ref)
        sources_group.children.append(Reference(file_ref.id))

        build_file = PBXBuildFile(
            fileRef=Reference(file_ref.id), name=os.path.basename(src)
        )
        source_build_files.append(build_file)

    # Create file references and build files for headers
    header_refs = []
    header_build_files = []
    for hdr in target_info.headers:
        hdr_path = os.path.relpath(hdr, project_info.project_dir)
        file_ref = PBXFileReference(
            name=os.path.basename(hdr),
            path=hdr_path,
            sourceTree=SourceTree.SOURCE_ROOT,
            fileType=FileType.from_extension(os.path.splitext(hdr)[1]),
        )
        header_refs.append(file_ref)
        headers_group.children.append(Reference(file_ref.id))

        build_file = PBXBuildFile(
            fileRef=Reference(file_ref.id), name=os.path.basename(hdr)
        )
        header_build_files.append(build_file)

    # Create build phases
    sources_phase = PBXSourcesBuildPhase(
        files=[Reference(bf.id) for bf in source_build_files]
    )
    headers_phase = PBXHeadersBuildPhase(
        files=[Reference(bf.id) for bf in header_build_files]
    )
    frameworks_phase = PBXFrameworksBuildPhase(files=[])

    # Create product reference
    product_ref = PBXFileReference(
        name=target_info.target.name,
        path="$(CONFIGURATION_BUILD_DIR)/$(PRODUCT_NAME)",
        sourceTree=SourceTree.SOURCE_ROOT,
        fileType=target_info.file_type,
    )

    # Create configurations
    target_configs = []
    for config in project_info.configs:
        settings = {**DEFAULT_BUILD_SETTINGS}

        # Add configuration-specific settings
        config_name = str(config.build_config)  # Ensure string
        output_path = target_info.output_paths[config_name]
        output_dir = os.path.dirname(output_path)
        settings["CONFIGURATION_BUILD_DIR"] = BuildSetting(
            value=f"$(SRCROOT)/{output_dir}"
        )
        settings["PRODUCT_NAME"] = BuildSetting(value=os.path.basename(output_path))

        # Add include paths
        if config_name in target_info.include_paths:
            settings["HEADER_SEARCH_PATHS"] = BuildSetting(
                value=[
                    f"$(SRCROOT)/{p}" for p in target_info.include_paths[config_name]
                ]
            )

        target_configs.append(
            XCBuildConfiguration(
                name=config_name,
                buildSettings=settings,
            )
        )

    # Create configuration list
    config_list = XCConfigurationList(
        buildConfigurations=[Reference(c.id) for c in target_configs],
        defaultConfigurationName=str(
            project_info.configs[0].build_config
        ),  # Ensure string
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
        file_references=[*source_refs, *header_refs, product_ref],
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
    # Gather configurations
    configs = [
        bake_config(config, architecture=arch, build_config=build_cfg)
        for arch in str_iter(config.architecture)
        for build_cfg in str_iter(config.build_config)
    ]

    # Gather all project information
    project_info = ProjectInfo.gather(workspace, config, configs)

    # Create and return project
    return create_xcode_project(project_info)
