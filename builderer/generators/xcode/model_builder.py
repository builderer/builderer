"""
Xcode project model builder.

This module provides functionality to convert a builderer target into an Xcode project model.
It extracts information from the workspace and converts it to the appropriate Xcode project model
structures defined in model.py.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import os

from builderer import Config
from builderer.details.package import Package
from builderer.details.targets.target import Target, BuildTarget
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.workspace import Workspace, target_full_name
from builderer.details.variable_expansion import resolve_conditionals
from builderer.details.as_iterator import str_iter
from builderer.generators.xcode.utils import xcode_project_path
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
)


class XcodeProjectBuilder:
    """
    Builds an Xcode project model from a builderer target.

    This class extracts information from a builderer target and converts it to
    the Xcode project model defined in model.py.
    """

    def __init__(
        self,
        workspace: Workspace,
        config: Config,
        package: Package,
        target: BuildTarget,
    ) -> None:
        """
        Initialize the Xcode project builder.

        Args:
            workspace: The workspace containing all packages and targets.
            config: The configuration to use.
            package: The package containing the target.
            target: The target to build.
        """
        self.workspace = workspace
        self.config = config
        self.package = package
        self.target = target
        self.project_name = target.name
        self.workspace_root = str(workspace.root)

        # Initialize collections
        self.file_references: Dict[str, PBXFileReference] = {}
        self.groups: List[PBXGroup] = []
        self.build_files: Dict[str, PBXBuildFile] = {}
        self.targets: Dict[str, PBXNativeTarget] = {}
        self.build_configurations: List[XCBuildConfiguration] = []
        self.configuration_lists: List[XCConfigurationList] = []
        self.target_dependencies: List[PBXTargetDependency] = []
        self.container_item_proxies: List[PBXContainerItemProxy] = []
        self.build_phases: List[
            Union[
                PBXSourcesBuildPhase,
                PBXHeadersBuildPhase,
                PBXFrameworksBuildPhase,
                PBXResourcesBuildPhase,
                PBXCopyFilesBuildPhase,
                PBXShellScriptBuildPhase,
            ]
        ] = []

        # Create root groups
        self.main_group = self.create_group("", is_root=True)
        self.products_group = self.create_group("Products", is_root=True)

        # Create configurations based on config.build_config using list comprehension
        config_names = list(str_iter(self.config.build_config))

        # Create all configurations with their settings in a single comprehension
        build_configs = [
            self._create_build_configuration(config_name, {**DEFAULT_BUILD_SETTINGS})
            for config_name in config_names
        ]

        # Use the first config as default
        default_config_name = config_names[0]

        # Create configuration list
        config_list = self._create_config_list(build_configs, default_config_name)

        # Create project object
        self.project = PBXProject(
            name=self.project_name,
            buildConfigurationList=self.create_reference(
                config_list,
                f'Build configuration list for PBXProject "{self.project_name}"',
            ),
            mainGroup=self.create_reference(self.main_group),
            productRefGroup=self.create_reference(self.products_group),
            targets=[],
        )

        # Create target
        self.process_target()

    def create_reference(
        self, obj: XcodeObject, comment: Optional[str] = None
    ) -> Reference:
        """
        Create a reference to an Xcode object.

        Args:
            obj: The object to reference.
            comment: An optional comment for the reference.

        Returns:
            A Reference object.
        """
        if comment is None:
            # Try to generate a comment based on the object type
            if isinstance(
                obj, (PBXFileReference, PBXGroup, PBXNativeTarget, XCBuildConfiguration)
            ):
                comment = obj.name
            elif isinstance(obj, PBXBuildFile):
                # fileRef is a Reference which always has a comment attribute
                comment = obj.fileRef.comment

        return Reference(id=obj.id, comment=comment)

    def create_file_reference(
        self,
        path: str,
        name: Optional[str] = None,
        file_type: Optional[FileType] = None,
    ) -> PBXFileReference:
        """
        Create a file reference.

        Args:
            path: The path to the file.
            name: The name of the file.
            file_type: The type of the file.

        Returns:
            The PBXFileReference object.
        """
        if path in self.file_references:
            return self.file_references[path]

        if name is None:
            name = os.path.basename(path)

        if file_type is None:
            ext = os.path.splitext(path)[1].lower()
            file_type = FileType.from_extension(ext)

        file_ref = PBXFileReference(
            name=name,
            path=path,
            sourceTree=SourceTree.SOURCE_ROOT,
            fileType=file_type,
        )

        self.file_references[path] = file_ref
        return file_ref

    def create_build_file(self, file_ref: PBXFileReference) -> PBXBuildFile:
        """
        Create a build file.

        Args:
            file_ref: The file reference to create a build file for.

        Returns:
            The PBXBuildFile object.
        """
        # Check if we already have a build file for this file reference
        file_ref_id = file_ref.id
        if file_ref_id in self.build_files:
            return self.build_files[file_ref_id]

        # Create a new build file
        build_file = PBXBuildFile(
            fileRef=self.create_reference(file_ref),
        )

        self.build_files[file_ref_id] = build_file
        return build_file

    def create_group(
        self, name: str, path: Optional[str] = None, is_root: bool = False
    ) -> PBXGroup:
        """
        Create a group.

        Args:
            name: The name of the group.
            path: The path to the group.
            is_root: Whether this is a root group.

        Returns:
            The PBXGroup object.
        """
        source_tree = SourceTree.GROUP
        if is_root:
            source_tree = SourceTree.SOURCE_ROOT

        group = PBXGroup(
            name=name,
            sourceTree=source_tree,
            children=[],
            path=path,
        )

        self.groups.append(group)
        return group

    def _create_build_configuration(
        self, name: str, build_settings: Dict[str, BuildSetting]
    ) -> XCBuildConfiguration:
        """
        Create a build configuration.

        Args:
            name: The name of the configuration.
            build_settings: The build settings for the configuration.

        Returns:
            The XCBuildConfiguration object.
        """
        config = XCBuildConfiguration(
            name=name,
            buildSettings=build_settings,
        )

        self.build_configurations.append(config)
        return config

    def _create_config_list(
        self, configs: List[XCBuildConfiguration], default_config_name: str
    ) -> XCConfigurationList:
        """
        Create a configuration list.

        Args:
            configs: The configurations to include.
            default_config_name: The name of the default configuration.

        Returns:
            The XCConfigurationList object.
        """
        config_list = XCConfigurationList(
            buildConfigurations=[self.create_reference(config) for config in configs],
            defaultConfigurationName=default_config_name,
        )

        self.configuration_lists.append(config_list)
        return config_list

    def get_source_files(self) -> List[str]:
        if isinstance(self.target, (CCBinary, CCLibrary)):
            # CCBinary and CCLibrary have srcs attribute
            sources = str_iter(resolve_conditionals(self.config, self.target.srcs))
            project_dir = (
                Path(self.workspace.root) / self.config.build_root / self.package.root
            )
            return [os.path.relpath(src, project_dir) for src in sources]
        else:
            return []

    def get_header_files(self) -> List[str]:
        if isinstance(self.target, CCLibrary):
            headers = str_iter(resolve_conditionals(self.config, self.target.hdrs))
            project_dir = (
                Path(self.workspace.root) / self.config.build_root / self.package.root
            )
            return [os.path.relpath(hdr, project_dir) for hdr in headers]
        else:
            return []

    def get_dependency_files(self) -> List[str]:
        """
        Get the dependency files (frameworks, libraries) for the target.

        Returns:
            A list of dependency file paths.
        """
        # All Target classes have deps attribute
        target_deps = resolve_conditionals(self.config, self.target.deps)
        if not isinstance(target_deps, list):
            return []

        # Find matching targets for each dependency and determine appropriate file paths
        dependency_files = []

        for dep in target_deps:
            # Find the target in all packages
            for pkg in self.workspace.packages.values():
                matching_targets = [t for t in pkg.targets.values() if t.name == dep]

                for pkg_target in matching_targets:
                    if isinstance(pkg_target, CCLibrary):
                        dependency_files.append(f"lib{pkg_target.name}.a")
                    elif isinstance(pkg_target, BuildTarget):
                        # For other build targets, determine type
                        dependency_files.append(f"lib{pkg_target.name}.a")

        return dependency_files

    def _get_product_type_for_target(self, target: BuildTarget) -> ProductType:
        """
        Determine the product type for a target.

        Args:
            target: The target to determine the product type for.

        Returns:
            The appropriate ProductType.

        Raises:
            ValueError: If the target type cannot be determined.
        """
        if isinstance(target, CCBinary):
            return ProductType.TOOL
        elif isinstance(target, CCLibrary):
            return ProductType.STATIC_LIBRARY
        else:
            # For unknown target types, raise an error
            raise ValueError(
                f"Cannot determine product type for target of type {type(target).__name__}"
            )

    def process_target(self) -> None:
        """Process the target and add it to the Xcode project."""
        target_name = self.target.name

        # Determine product type - let exceptions propagate
        product_type = self._get_product_type_for_target(self.target)

        # Get source and header files
        source_files = self.get_source_files()
        header_files = self.get_header_files()
        dependency_files = self.get_dependency_files()

        # Create file references using list comprehensions
        source_refs = [self.create_file_reference(src) for src in source_files]
        header_refs = [self.create_file_reference(hdr) for hdr in header_files]
        dependency_refs = [self.create_file_reference(dep) for dep in dependency_files]

        # Create build files using list comprehensions
        source_build_files = [self.create_build_file(ref) for ref in source_refs]
        dependency_build_files = [
            self.create_build_file(ref) for ref in dependency_refs
        ]

        # Create build phases
        sources_phase = PBXSourcesBuildPhase(
            files=[self.create_reference(file) for file in source_build_files],
        )

        frameworks_phase = PBXFrameworksBuildPhase(
            files=[self.create_reference(file) for file in dependency_build_files],
        )

        resources_phase = PBXResourcesBuildPhase(
            files=[],  # TODO: Add resource files
        )

        # Create product reference
        product_name = target_name
        if product_type == ProductType.APPLICATION:
            product_path = f"{product_name}.app"
        elif product_type == ProductType.FRAMEWORK:
            product_path = f"{product_name}.framework"
        elif product_type == ProductType.STATIC_LIBRARY:
            product_path = f"lib{product_name}.a"
        elif product_type == ProductType.BUNDLE:
            product_path = f"{product_name}.bundle"
        else:
            product_path = product_name

        product_ref = self.create_file_reference(
            product_path, file_type=self._get_file_type_for_product(product_type)
        )

        # Add product to Products group
        self.products_group.children.append(self.create_reference(product_ref))

        # Create target-specific configurations using list comprehension
        config_names = list(str_iter(self.config.build_config))

        # Create all target-specific configurations with product name setting
        build_configs = [
            self._create_build_configuration(
                config_name,
                {
                    **DEFAULT_BUILD_SETTINGS,
                    "PRODUCT_NAME": BuildSetting(value=product_name),
                },
            )
            for config_name in config_names
        ]

        # Use the first config as default
        default_config_name = config_names[0]

        # Create configuration list
        config_list = self._create_config_list(build_configs, default_config_name)

        # Create target
        xcode_target = PBXNativeTarget(
            name=target_name,
            productName=product_name,
            productType=product_type,
            buildPhases=[
                self.create_reference(sources_phase),
                self.create_reference(frameworks_phase),
                self.create_reference(resources_phase),
            ],
            buildConfigurationList=self.create_reference(config_list),
            productReference=self.create_reference(product_ref),
        )

        # Create source group
        source_group = self.create_group("Source", path="Source")
        self.main_group.children.append(self.create_reference(source_group))

        # Add sources to source group
        for src_ref in source_refs:
            source_group.children.append(self.create_reference(src_ref))

        # Create headers group if needed
        if header_refs:
            headers_group = self.create_group("Headers", path="Headers")
            self.main_group.children.append(self.create_reference(headers_group))
            # Add headers to headers group
            for hdr_ref in header_refs:
                headers_group.children.append(self.create_reference(hdr_ref))

        # Create frameworks group if needed
        if dependency_refs:
            frameworks_group = self.create_group("Frameworks", path="Frameworks")
            self.main_group.children.append(self.create_reference(frameworks_group))
            # Add dependencies to frameworks group
            for dep_ref in dependency_refs:
                frameworks_group.children.append(self.create_reference(dep_ref))

        # Store build phases
        self.build_phases.extend([sources_phase, frameworks_phase, resources_phase])

        # Create target dependencies using direct_dependencies
        for dep_package, dep_target in self.workspace.direct_dependencies(
            self.package, self.target
        ):
            if not isinstance(dep_target, BuildTarget):
                continue
            full_name = target_full_name(dep_package, dep_target)
            container_proxy = PBXContainerItemProxy(
                containerPortal=self.create_reference(self.project),
                proxyType=1,  # 1 indicates a target proxy
                remoteGlobalIDString=generate_id(full_name),
                remoteInfo=os.path.relpath(
                    xcode_project_path(dep_package, dep_target),
                    xcode_project_path(self.package, self.target),
                ),
            )
            self.container_item_proxies.append(container_proxy)
            target_dependency = PBXTargetDependency(
                targetProxy=self.create_reference(container_proxy)
            )
            self.target_dependencies.append(target_dependency)
            self.project.targetDependencies.append(
                self.create_reference(target_dependency)
            )
            xcode_target.dependencies.append(self.create_reference(target_dependency))

        self.targets[target_full_name(self.package, self.target)] = xcode_target
        self.project.targets.append(self.create_reference(xcode_target))

    def _get_file_type_for_product(self, product_type: ProductType) -> FileType:
        """Map product type to file type."""
        mapping = {
            ProductType.APPLICATION: FileType.APP,
            ProductType.FRAMEWORK: FileType.FRAMEWORK,
            ProductType.STATIC_LIBRARY: FileType.DYLIB,
            ProductType.DYNAMIC_LIBRARY: FileType.DYLIB,
            ProductType.BUNDLE: FileType.BUNDLE,
            ProductType.TOOL: FileType.EXECUTABLE,
        }

        # Direct dictionary access will raise KeyError if product_type is not found
        return mapping[product_type]

    def build(self) -> XcodeProject:
        """
        Build the Xcode project from the information collected.

        Returns:
            An XcodeProject instance that can be serialized to a .pbxproj file.
        """
        return XcodeProject(
            fileReferences=list(self.file_references.values()),
            groups=self.groups,
            buildFiles=list(self.build_files.values()),
            buildPhases=self.build_phases,  # Add stored build phases
            nativeTargets=list(self.targets.values()),
            project=self.project,
            buildConfigurations=self.build_configurations,
            configurationLists=self.configuration_lists,
            targetDependencies=self.target_dependencies,
            containerItemProxies=self.container_item_proxies,
        )


def create_xcode_project(
    config: Config, workspace: Workspace, package: Package, target: BuildTarget
) -> XcodeProject:
    """
    Create an Xcode project for a specific builderer target.

    Args:
        config: The configuration to use.
        workspace: The builderer workspace.
        package: The package containing the target.
        target: The target to create a project for.

    Returns:
        An XcodeProject object.
    """
    builder = XcodeProjectBuilder(workspace, config, package, target)
    return builder.build()
