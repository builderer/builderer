"""
Xcode project model builder.

This module provides functionality to convert a builderer target into an Xcode project model.
It extracts information from the workspace and converts it to the appropriate Xcode project model
structures defined in model.py.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from builderer import Config
from builderer.details.package import Package
from builderer.details.targets.target import Target, BuildTarget
from builderer.details.workspace import Workspace
from builderer.details.variable_expansion import resolve_conditionals
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
    ProductType,
    Reference,
    SourceTree,
    XCBuildConfiguration,
    XCConfigurationList,
    XcodeObject,
    XcodeProject,
    YesNo,
    DEFAULT_BUILD_SETTINGS,
)


class XcodeProjectBuilder:
    """
    Builds an Xcode project model from a builderer target.
    
    This class extracts information from a builderer target and converts it to
    the Xcode project model defined in model.py.
    """
    
    def __init__(self, workspace: Workspace, config: Config, package: Package, target: BuildTarget):
        """
        Initialize the Xcode project builder.
        
        Args:
            workspace: The builderer workspace.
            config: The configuration to use.
            package: The package containing the target.
            target: The target to create a project for.
        """
        self.workspace = workspace
        self.config = config
        self.package = package
        self.target = target
        self.project_name = f"{target.name}"
        self.workspace_root = str(workspace.workspace_root) if hasattr(workspace, 'workspace_root') else ""
        
        # Collections of created Xcode objects
        self.file_references: Dict[str, PBXFileReference] = {}
        self.groups: List[PBXGroup] = []
        self.build_files: Dict[str, PBXBuildFile] = {}
        self.targets: Dict[str, PBXNativeTarget] = {}
        self.build_configurations: List[XCBuildConfiguration] = []
        self.configuration_lists: List[XCConfigurationList] = []
        
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
        config_list = self._create_config_list(
            build_configs,
            default_config_name
        )
        
        # Create project object
        self.project = PBXProject(
            name=self.project_name,
            build_config_list=self.create_reference(config_list, "Build configuration list for PBXProject"),
            main_group=self.create_reference(self.main_group),
            product_ref_group=self.create_reference(self.products_group),
            targets=[],
        )
        
        # Create target
        self.process_target()
    
    def create_reference(self, obj: XcodeObject, comment: Optional[str] = None) -> Reference:
        """
        Create a reference to an Xcode object.
        
        Args:
            obj: The object to reference.
            comment: An optional comment for the reference.
            
        Returns:
            A Reference object.
        """
        if comment is None and hasattr(obj, 'name'):
            comment = getattr(obj, 'name')
        return Reference(id=obj.id, comment=comment)
    
    def create_file_reference(self, path: str, file_type: Optional[FileType] = None) -> PBXFileReference:
        """
        Create a file reference or return an existing one for the given path.
        
        Args:
            path: The path to the file, relative to the workspace root.
            file_type: The type of the file (auto-detected if not provided).
            
        Returns:
            The PBXFileReference object.
        """
        if path in self.file_references:
            return self.file_references[path]
        
        # Extract filename from path
        filename = Path(path).name
        
        # Determine file type if not provided
        if file_type is None:
            extension = Path(path).suffix.lower()[1:] if Path(path).suffix else ""
            # Simplified mapping - expand as needed
            ext_to_type = {
                "c": FileType.C,
                "cpp": FileType.CPP,
                "h": FileType.C_HEADER,
                "hpp": FileType.CPP_HEADER,
                "swift": FileType.SWIFT,
                "m": FileType.OBJC,
                "mm": FileType.OBJCPP,
                "xib": FileType.XIB,
                "storyboard": FileType.STORYBOARD,
                "plist": FileType.PLIST,
                "xcconfig": FileType.XCCONFIG,
                "strings": FileType.STRINGS,
                "xcassets": FileType.ASSET_CATALOG,
                "framework": FileType.FRAMEWORK,
                "bundle": FileType.BUNDLE,
                "app": FileType.APP,
                "dylib": FileType.DYLIB,
            }
            file_type = ext_to_type.get(extension, FileType.TEXT)
        
        # Create file reference
        file_ref = PBXFileReference(
            name=filename,
            path=path,
            file_type=file_type,
            source_tree=SourceTree.SOURCE_ROOT,
        )
        
        self.file_references[path] = file_ref
        return file_ref
    
    def create_build_file(self, file_ref: PBXFileReference) -> PBXBuildFile:
        """
        Create a build file for a file reference or return an existing one.
        
        Args:
            file_ref: The file reference.
            
        Returns:
            The PBXBuildFile object.
        """
        key = file_ref.id
        if key in self.build_files:
            return self.build_files[key]
        
        build_file = PBXBuildFile(
            name=file_ref.name,
            file_ref=self.create_reference(file_ref),
        )
        
        self.build_files[key] = build_file
        return build_file
    
    def create_group(self, name: str, path: Optional[str] = None, is_root: bool = False) -> PBXGroup:
        """
        Create a group for files.
        
        Args:
            name: The name of the group.
            path: The path of the group.
            is_root: Whether this is a root group (no path component).
            
        Returns:
            The PBXGroup object.
        """
        group = PBXGroup(
            name=name,
            source_tree=SourceTree.GROUP,
            children=[],
            path=None if is_root else path,
        )
        
        self.groups.append(group)
        return group
    
    def _create_build_configuration(
        self, 
        name: str, 
        build_settings: Dict[str, BuildSetting]
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
            build_settings=build_settings,
        )
        
        self.build_configurations.append(config)
        return config
    
    def _create_config_list(
        self,
        configs: List[XCBuildConfiguration],
        default_config_name: str
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
            build_configurations=[self.create_reference(config) for config in configs],
            default_configuration_name=default_config_name,
        )
        
        self.configuration_lists.append(config_list)
        return config_list
    
    def get_source_files(self) -> List[str]:
        """
        Get the source files for the target.
        
        Returns:
            A list of source file paths.
        """
        # Extract files from target sources if available
        sources = []
        if hasattr(self.target, 'sources'):
            # The sources attribute should be resolved by builderer
            target_sources = resolve_conditionals(self.config, self.target.sources)
            if isinstance(target_sources, list):
                sources = target_sources
        
        # Resolve paths relative to package root using list comprehension
        return [str(self.package.root / src) for src in sources]
    
    def get_header_files(self) -> List[str]:
        """
        Get the header files for the target.
        
        Returns:
            A list of header file paths.
        """
        # Extract files from target headers if available
        headers = []
        if hasattr(self.target, 'headers'):
            # The headers attribute should be resolved by builderer
            target_headers = resolve_conditionals(self.config, self.target.headers)
            if isinstance(target_headers, list):
                headers = target_headers
        
        # Resolve paths relative to package root using list comprehension
        return [str(self.package.root / hdr) for hdr in headers]
    
    def get_dependency_files(self) -> List[str]:
        """
        Get the dependency files (frameworks, libraries) for the target.
        
        Returns:
            A list of dependency file paths.
        """
        # Return empty list if target has no dependencies
        if not hasattr(self.target, 'dependencies'):
            return []
            
        # Resolve conditionals for dependencies
        target_deps = resolve_conditionals(self.config, self.target.dependencies)
        if not isinstance(target_deps, list):
            return []
        
        # Find matching targets for each dependency and determine appropriate file paths
        dependency_files = []
        
        for dep in target_deps:
            # Find the target in all packages
            for pkg in self.workspace.packages:
                matching_targets = [
                    t for t in pkg.targets.values()
                    if t.name == dep and hasattr(t, 'type')
                ]
                
                for pkg_target in matching_targets:
                    target_type = resolve_conditionals(self.config, pkg_target.type)
                    if target_type == 'library':
                        dependency_files.append(f"lib{pkg_target.name}.a")
                    elif target_type == 'framework':
                        dependency_files.append(f"{pkg_target.name}.framework")
        
        return dependency_files
    
    def process_target(self) -> None:
        """Process the target and add it to the Xcode project."""
        target_name = self.target.name
        
        # Determine target type and product type
        if hasattr(self.target, 'type'):
            target_type = resolve_conditionals(self.config, self.target.type)
            product_type = {
                'executable': ProductType.TOOL,
                'application': ProductType.APPLICATION,
                'library': ProductType.STATIC_LIBRARY,
                'framework': ProductType.FRAMEWORK,
                'bundle': ProductType.BUNDLE,
            }.get(target_type, ProductType.TOOL)
        else:
            # Default to executable
            product_type = ProductType.TOOL
        
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
        dependency_build_files = [self.create_build_file(ref) for ref in dependency_refs]
        
        # Create build phases with references
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
            product_path,
            file_type=self._get_file_type_for_product(product_type)
        )
        
        # Add product to Products group
        self.products_group.children.append(self.create_reference(product_ref))
        
        # Create target-specific configurations using list comprehension
        config_names = list(str_iter(self.config.build_config))
        
        # Create all target-specific configurations with product name setting
        build_configs = [
            self._create_build_configuration(
                config_name, 
                {**DEFAULT_BUILD_SETTINGS, "PRODUCT_NAME": BuildSetting(value=product_name)}
            )
            for config_name in config_names
        ]
        
        # Use the first config as default
        default_config_name = config_names[0]
        
        # Create configuration list
        config_list = self._create_config_list(
            build_configs,
            default_config_name
        )
        
        # Create target
        xcode_target = PBXNativeTarget(
            name=target_name,
            product_name=product_name,
            product_type=product_type,
            build_phases=[
                self.create_reference(sources_phase),
                self.create_reference(frameworks_phase),
                self.create_reference(resources_phase),
            ],
            build_config_list=self.create_reference(config_list),
            product_reference=self.create_reference(product_ref),
        )
        
        self.targets[target_name] = xcode_target
        
        # Add target to project
        self.project.targets.append(self.create_reference(xcode_target))
        
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
        return mapping.get(product_type, FileType.TEXT)
    
    def build(self) -> XcodeProject:
        """
        Build the Xcode project from the information collected.
        
        Returns:
            An XcodeProject instance that can be serialized to a .pbxproj file.
        """
        return XcodeProject(
            file_references=list(self.file_references.values()),
            groups=self.groups,
            build_files=list(self.build_files.values()),
            build_phases=[],  # Build phases are referenced from targets
            native_targets=list(self.targets.values()),
            project=self.project,
            build_configurations=self.build_configurations,
            configuration_lists=self.configuration_lists,
        )


def create_xcode_project(
    config: Config,
    workspace: Workspace,
    package: Package,
    target: BuildTarget
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