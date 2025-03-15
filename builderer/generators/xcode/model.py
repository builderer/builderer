"""
Xcode project file model.

This module defines the data model for an Xcode project file (.pbxproj).
It includes classes that accurately represent the object types and their relationships
as documented in the Xcode project file format.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Union, NewType, ClassVar, Set
from abc import ABC, abstractmethod

import uuid

# Type definition for Xcode object identifiers
class XcodeID(str):
    """
    A specialized string class for Xcode object identifiers.
    
    This is used to distinguish Xcode IDs from regular strings,
    allowing for proper formatting in pbxproj files.
    """
    pass

def generate_id(key: str) -> XcodeID:
    """
    Generate a deterministic ID based on a key using UUID5.
    
    Args:
        key: The key to use for ID generation.
        
    Returns:
        A 24-character hexadecimal ID as an XcodeID type.
    """
    return XcodeID(uuid.uuid5(uuid.NAMESPACE_X500, key).hex.upper()[:24])

# Source Tree values used in PBXFileReference and PBXGroup
class SourceTree(Enum):
    """Possible values for the sourceTree property."""
    GROUP = "<group>"  # Path is relative to the group's folder
    SOURCE_ROOT = "SOURCE_ROOT"  # Path is relative to the project's root directory
    BUILT_PRODUCTS_DIR = "BUILT_PRODUCTS_DIR"  # Path is relative to the build products directory
    DEVELOPER_DIR = "DEVELOPER_DIR"  # Path is relative to the developer directory
    SDKROOT = "SDKROOT"  # Path is relative to the SDK directory
    ABSOLUTE = "ABSOLUTE"  # Path is an absolute filesystem path


# Destination subfolder specifications used in PBXCopyFilesBuildPhase
class DstSubfolderSpec(Enum):
    """Possible values for the dstSubfolderSpec property in PBXCopyFilesBuildPhase."""
    ABSOLUTE_PATH = 0            # Absolute path
    WRAPPER = 1                  # App bundle
    EXECUTABLES = 2              # Executables
    RESOURCES = 3                # Resources
    JAVA_RESOURCES = 4           # Java Resources
    FRAMEWORKS = 5               # Frameworks
    SHARED_FRAMEWORKS = 6        # Shared Frameworks
    PLUGINS = 10                 # Plug-ins
    SCRIPTS = 11                 # Scripts
    JAVA_RESOURCES_ALT = 12      # Java Resources (alternate)
    PRODUCTS_DIRECTORY = 13      # Products Directory
    WRAPPER_ALT = 16             # Wrapper (app bundle, alternate)


# File types used in PBXFileReference
class FileType(Enum):
    """File type identifiers used in lastKnownFileType or explicitFileType."""
    # Source code
    C = "sourcecode.c.c"
    CPP = "sourcecode.cpp.cpp"
    C_HEADER = "sourcecode.c.h"
    CPP_HEADER = "sourcecode.cpp.h"
    SWIFT = "sourcecode.swift"
    OBJC = "sourcecode.c.objc"
    OBJCPP = "sourcecode.cpp.objcpp"
    
    # Resources
    XIB = "file.xib"
    STORYBOARD = "file.storyboard"
    PLIST = "text.plist"
    XCCONFIG = "text.xcconfig"
    STRINGS = "text.plist.strings"
    
    # Compiled
    EXECUTABLE = "compiled.mach-o.executable"
    DYLIB = "compiled.mach-o.dylib"
    FRAMEWORK = "wrapper.framework"
    BUNDLE = "wrapper.bundle"
    APP = "wrapper.application"
    
    # Other
    FOLDER = "folder"
    TEXT = "text"
    ASSET_CATALOG = "folder.assetcatalog"


# Product types used in PBXNativeTarget
class ProductType(Enum):
    """Possible values for the productType property."""
    APPLICATION = "com.apple.product-type.application"
    FRAMEWORK = "com.apple.product-type.framework"
    STATIC_LIBRARY = "com.apple.product-type.library.static"
    DYNAMIC_LIBRARY = "com.apple.product-type.library.dynamic"
    BUNDLE = "com.apple.product-type.bundle"
    TOOL = "com.apple.product-type.tool"
    UNIT_TEST_BUNDLE = "com.apple.product-type.unit-test.bundle"
    APP_EXTENSION = "com.apple.product-type.app-extension"


# Boolean-like values used in build settings
class YesNo(Enum):
    """Boolean-like values used in build settings."""
    YES = "YES"
    NO = "NO"
    YES_ERROR = "YES_ERROR"
    YES_AGGRESSIVE = "YES_AGGRESSIVE"


# Build setting with type-safe value
@dataclass
class BuildSetting:
    """A build setting value."""
    value: Union[YesNo, int, float, str, List[str]]


# Reference to another object with optional comment
@dataclass
class Reference:
    """A reference to another object in the project file."""
    id: XcodeID
    comment: Optional[str] = None


# Base class for all Xcode objects
@dataclass
class XcodeObject(ABC):
    """Base class for all Xcode objects."""
    # ID will be generated in __post_init__
    id: XcodeID = field(init=False)
    
    def __post_init__(self) -> None:
        """Generate a unique ID based on the object's key."""
        self.id = generate_id(self.key())
    
    @abstractmethod
    def key(self) -> str:
        """
        Generate a unique key string for this object.
        
        Each subclass MUST override this method to provide a specific key.
        The key should be deterministic and unique for the object.
        
        Returns:
            A string key that uniquely identifies this object.
        """
        pass

# PBX* object types
@dataclass
class PBXBuildFile(XcodeObject):
    """A build file in the project. Represents a file used in a build phase."""
    name: str
    file_ref: Reference
    
    def key(self) -> str:
        """Use file reference ID as the primary key for build files."""
        return f"PBXBuildFile:{self.file_ref.id}"


@dataclass
class PBXFileReference(XcodeObject):
    """A file reference in the project. Describes a reference to a file on disk."""
    name: str
    file_type: FileType
    path: str
    source_tree: SourceTree
    explicit_file_type: Optional[FileType] = None
    last_known_file_type: Optional[FileType] = None
    
    def key(self) -> str:
        """Use path as the primary key for file references."""
        return f"PBXFileReference:{self.path}"


@dataclass
class PBXSourcesBuildPhase(XcodeObject):
    """
    Sources build phase. Compiles source files.
    
    Attributes:
        files: List of references to PBXBuildFile objects
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    
    def key(self) -> str:
        """Use class name and first file ID (if available) for build phase key."""
        class_name = self.__class__.__name__
        if self.files:
            return f"{class_name}:{self.files[0].id}"
        return class_name


@dataclass
class PBXHeadersBuildPhase(XcodeObject):
    """
    Headers build phase. Copies headers to the product directory.
    
    Attributes:
        files: List of references to PBXBuildFile objects
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    
    def key(self) -> str:
        """Use class name and first file ID (if available) for build phase key."""
        class_name = self.__class__.__name__
        if self.files:
            return f"{class_name}:{self.files[0].id}"
        return class_name


@dataclass
class PBXFrameworksBuildPhase(XcodeObject):
    """
    Frameworks build phase. Links with frameworks and libraries.
    
    Attributes:
        files: List of references to PBXBuildFile objects
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    
    def key(self) -> str:
        """Use class name and first file ID (if available) for build phase key."""
        class_name = self.__class__.__name__
        if self.files:
            return f"{class_name}:{self.files[0].id}"
        return class_name


@dataclass
class PBXResourcesBuildPhase(XcodeObject):
    """
    Resources build phase. Copies resources to the product directory.
    
    Attributes:
        files: List of references to PBXBuildFile objects
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    
    def key(self) -> str:
        """Use class name and first file ID (if available) for build phase key."""
        class_name = self.__class__.__name__
        if self.files:
            return f"{class_name}:{self.files[0].id}"
        return class_name


@dataclass
class PBXCopyFilesBuildPhase(XcodeObject):
    """
    Copy files build phase. Copies files to a specified location during the build process.
    
    Attributes:
        dst_path: The destination path for copying the files
        dst_subfolder_spec: The standard location within the bundle to copy files to
        files: List of references to PBXBuildFile objects
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    dst_path: str
    dst_subfolder_spec: DstSubfolderSpec
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    
    def key(self) -> str:
        """Use class name, destination path and subfolder spec for build phase key."""
        return f"{self.__class__.__name__}:{self.dst_path}:{self.dst_subfolder_spec.name}"


@dataclass
class PBXShellScriptBuildPhase(XcodeObject):
    """
    Shell script build phase. Runs a shell script.
    
    Attributes:
        files: List of references to PBXBuildFile objects
        input_paths: List of input file paths
        output_paths: List of output file paths
        shell_path: Path to the shell to use (default: /bin/sh)
        shell_script: The script to run
        build_action_mask: Usually set to 2147483647 (2^32-1)
        run_only_for_deployment_postprocessing: Flag (0 or 1) indicating whether to run only when installing
    """
    files: List[Reference]
    shell_script: str
    build_action_mask: int = 2147483647  # Default value used by Xcode
    run_only_for_deployment_postprocessing: int = 0
    input_paths: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    shell_path: str = "/bin/sh"
    
    def key(self) -> str:
        """Use class name and script for build phase key."""
        return f"{self.__class__.__name__}:{hash(self.shell_script)}"


@dataclass
class PBXGroup(XcodeObject):
    """A group in the project. Represents a group or folder in the project navigator."""
    name: str
    source_tree: SourceTree
    children: List[Reference]
    path: Optional[str] = None
    
    def key(self) -> str:
        """Use name and path (if available) for group keys."""
        if self.path:
            return f"PBXGroup:{self.name}:{self.path}"
        return f"PBXGroup:{self.name}"


@dataclass
class PBXVariantGroup(XcodeObject):
    """
    A variant group in the project. For localized resources.
    
    Attributes:
        name: Name of the group
        children: List of references to localized resources
        source_tree: How the path is resolved (see Source Tree Constants)
        path: Path to the group
    """
    name: str
    children: List[Reference]
    source_tree: SourceTree
    path: Optional[str] = None
    
    def key(self) -> str:
        """Use name and path (if available) for variant group keys."""
        if self.path:
            return f"PBXVariantGroup:{self.name}:{self.path}"
        return f"PBXVariantGroup:{self.name}"


@dataclass
class XCVersionGroup(XcodeObject):
    """
    A version group in the project. Represents a versioned Core Data model.
    
    Attributes:
        name: Name of the model group
        children: List of references to PBXFileReference objects for each model version
        current_version: Reference to the current version of the model
        path: Path to the model group
        source_tree: How the path is resolved (see Source Tree Constants)
        version_group_type: Type of the version group, typically "wrapper.xcdatamodel"
    """
    name: str
    children: List[Reference]
    current_version: Reference
    source_tree: SourceTree
    path: Optional[str] = None
    version_group_type: str = "wrapper.xcdatamodel"
    
    def key(self) -> str:
        """Use name, path, and version group type for version group key."""
        path_part = f":{self.path}" if self.path else ""
        return f"XCVersionGroup:{self.name}{path_part}:{self.version_group_type}"


@dataclass
class PBXTargetDependency(XcodeObject):
    """Target dependency. Indicates that one target depends on another."""
    target: Reference
    target_proxy: Reference


@dataclass
class PBXContainerItemProxy(XcodeObject):
    """Container item proxy. Refers to an item in another target."""
    container_portal: Reference
    proxy_type: int
    remote_global_id_string: str
    remote_info: str


@dataclass
class PBXReferenceProxy(XcodeObject):
    """Reference proxy. Refers to a product of another target."""
    file_type: FileType
    path: str
    remote_ref: Reference
    source_tree: SourceTree


@dataclass
class PBXBuildRule(XcodeObject):
    """Build rule. Defines how to process a file of a given type."""
    compiler_spec: str
    file_type: str
    is_editable: int
    file_patterns: Optional[str] = None
    input_files: List[str] = field(default_factory=list)
    output_files: List[str] = field(default_factory=list)
    script: Optional[str] = None
    run_once_per_architecture: Optional[int] = None


@dataclass
class PBXNativeTarget(XcodeObject):
    """
    A native target in the project. Represents a build target.
    
    Attributes:
        name: Name of the target
        build_config_list: Reference to the XCConfigurationList
        build_phases: List of references to build phases
        product_reference: Reference to the product file
        product_type: The type of product being built
        dependencies: List of references to target dependencies
        build_rules: List of references to build rules
        product_name: Name of the product being built
        product_install_path: Path for installing the product
    """
    name: str
    build_config_list: Reference
    build_phases: List[Reference]
    product_reference: Reference
    product_type: ProductType
    dependencies: List[Reference] = field(default_factory=list)
    build_rules: List[Reference] = field(default_factory=list)
    product_name: Optional[str] = None
    product_install_path: Optional[str] = None
    
    def key(self) -> str:
        """Use name and product type for target key."""
        return f"PBXNativeTarget:{self.name}:{self.product_type.name}"


@dataclass
class PBXAggregateTarget(XcodeObject):
    """
    An aggregate target in the project. Groups several targets.
    
    Attributes:
        name: Name of the target
        build_config_list: Reference to the XCConfigurationList
        build_phases: List of references to build phases
        dependencies: List of references to target dependencies
        build_rules: List of references to build rules
        product_name: Name of the product being built
    """
    name: str
    build_config_list: Reference
    build_phases: List[Reference]
    dependencies: List[Reference] = field(default_factory=list)
    build_rules: List[Reference] = field(default_factory=list)
    product_name: Optional[str] = None
    
    def key(self) -> str:
        """Use name for aggregate target key."""
        return f"PBXAggregateTarget:{self.name}"


@dataclass
class PBXLegacyTarget(XcodeObject):
    """
    A legacy target in the project. Uses an external build system.
    
    Attributes:
        name: Name of the target
        build_config_list: Reference to the XCConfigurationList
        build_phases: List of references to build phases
        build_tool_path: Path to the external build tool (e.g., /usr/bin/make)
        build_arguments_string: Arguments to pass to the build tool
        pass_build_settings_in_environment: Flag (0 or 1) indicating whether to pass build settings as environment variables
        dependencies: List of references to target dependencies
        build_rules: List of references to build rules
        product_name: Name of the product being built
        build_working_directory: Working directory for the build tool
    """
    name: str
    build_config_list: Reference
    build_phases: List[Reference]
    build_tool_path: str
    build_arguments_string: str
    pass_build_settings_in_environment: int
    dependencies: List[Reference] = field(default_factory=list)
    build_rules: List[Reference] = field(default_factory=list)
    product_name: Optional[str] = None
    build_working_directory: str = ""
    
    def key(self) -> str:
        """Use name and build tool path for target key."""
        return f"PBXLegacyTarget:{self.name}:{self.build_tool_path}"


@dataclass
class PBXProject(XcodeObject):
    """The project object. The root object of the project."""
    name: str
    build_config_list: Reference
    main_group: Reference
    product_ref_group: Reference
    targets: List[Reference]
    compatibility_version: str = "Xcode 14.0"
    development_region: str = "en"
    has_scanned_for_encodings: int = 1
    known_regions: List[str] = field(default_factory=lambda: ["en", "Base"])
    project_dir_path: str = ""
    project_root: str = ""
    
    def key(self) -> str:
        """Use name for project key."""
        return f"PBXProject:{self.name}"


@dataclass
class XCBuildConfiguration(XcodeObject):
    """A build configuration in the project. Contains build settings."""
    name: str
    build_settings: Dict[str, BuildSetting]
    base_configuration_reference: Optional[Reference] = None
    
    def key(self) -> str:
        """Use name for configuration key."""
        return f"XCBuildConfiguration:{self.name}"


@dataclass
class XCConfigurationList(XcodeObject):
    """A configuration list in the project. Holds a list of build configurations."""
    build_configurations: List[Reference]
    default_configuration_is_visible: int = 0
    default_configuration_name: str = "Release"
    
    def key(self) -> str:
        """Use configurations and default name for config list key."""
        if self.build_configurations:
            return f"XCConfigurationList:{self.build_configurations[0].id}:{self.default_configuration_name}"
        return f"XCConfigurationList:{self.default_configuration_name}"


# Complete project representation
@dataclass
class XcodeProject:
    """An Xcode project. Contains all objects needed to generate a project file."""
    file_references: List[PBXFileReference]
    groups: List[PBXGroup]
    build_files: List[PBXBuildFile]
    build_phases: List[Union[
        PBXSourcesBuildPhase, 
        PBXHeadersBuildPhase, 
        PBXFrameworksBuildPhase, 
        PBXResourcesBuildPhase,
        PBXCopyFilesBuildPhase,
        PBXShellScriptBuildPhase
    ]]
    native_targets: List[PBXNativeTarget]
    project: PBXProject
    build_configurations: List[XCBuildConfiguration]
    configuration_lists: List[XCConfigurationList]
    variant_groups: List[PBXVariantGroup] = field(default_factory=list)
    version_groups: List[XCVersionGroup] = field(default_factory=list)
    target_dependencies: List[PBXTargetDependency] = field(default_factory=list)
    container_item_proxies: List[PBXContainerItemProxy] = field(default_factory=list)
    reference_proxies: List[PBXReferenceProxy] = field(default_factory=list)
    build_rules: List[PBXBuildRule] = field(default_factory=list)
    aggregate_targets: List[PBXAggregateTarget] = field(default_factory=list)
    legacy_targets: List[PBXLegacyTarget] = field(default_factory=list)


# Default build settings that apply to all targets
DEFAULT_BUILD_SETTINGS = {
    # Compiler settings
    "CLANG_ANALYZER_NONNULL": BuildSetting(value=YesNo.YES),
    "CLANG_ANALYZER_NUMBER_OBJECT_CONVERSION": BuildSetting(value=YesNo.YES_AGGRESSIVE),
    "CLANG_ENABLE_MODULES": BuildSetting(value=YesNo.YES),
    "CLANG_ENABLE_OBJC_ARC": BuildSetting(value=YesNo.YES),
    "CLANG_ENABLE_OBJC_WEAK": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_BOOL_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_COMMA": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_CONSTANT_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_DIRECT_OBJC_ISA_USAGE": BuildSetting(value=YesNo.YES_ERROR),
    "CLANG_WARN_DOCUMENTATION_COMMENTS": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_EMPTY_BODY": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_ENUM_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_INFINITE_RECURSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_INT_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_NON_LITERAL_NULL_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_OBJC_LITERAL_CONVERSION": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_OBJC_ROOT_CLASS": BuildSetting(value=YesNo.YES_ERROR),
    "CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_RANGE_LOOP_ANALYSIS": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_STRICT_PROTOTYPES": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_SUSPICIOUS_MOVE": BuildSetting(value=YesNo.YES),
    "CLANG_WARN_UNGUARDED_AVAILABILITY": BuildSetting(value=YesNo.YES_AGGRESSIVE),
    "CLANG_WARN_UNREACHABLE_CODE": BuildSetting(value=YesNo.YES),
    "CLANG_WARN__DUPLICATE_METHOD_MATCH": BuildSetting(value=YesNo.YES),
    
    # Build settings
    "COPY_PHASE_STRIP": BuildSetting(value=YesNo.NO),
    "DEBUG_INFORMATION_FORMAT": BuildSetting(value="dwarf"),
    "ENABLE_STRICT_OBJC_MSGSEND": BuildSetting(value=YesNo.YES),
    "ENABLE_TESTABILITY": BuildSetting(value=YesNo.YES),
    "ENABLE_USER_SCRIPT_SANDBOXING": BuildSetting(value=YesNo.YES),
    "GCC_DYNAMIC_NO_PIC": BuildSetting(value=YesNo.NO),
    "GCC_NO_COMMON_BLOCKS": BuildSetting(value=YesNo.YES),
    "GCC_OPTIMIZATION_LEVEL": BuildSetting(value=0),
    "GCC_WARN_64_TO_32_BIT_CONVERSION": BuildSetting(value=YesNo.YES),
    "GCC_WARN_ABOUT_RETURN_TYPE": BuildSetting(value=YesNo.YES_ERROR),
    "GCC_WARN_UNDECLARED_SELECTOR": BuildSetting(value=YesNo.YES),
    "GCC_WARN_UNINITIALIZED_AUTOS": BuildSetting(value=YesNo.YES_AGGRESSIVE),
    "GCC_WARN_UNUSED_FUNCTION": BuildSetting(value=YesNo.YES),
    "GCC_WARN_UNUSED_VARIABLE": BuildSetting(value=YesNo.YES),
    
    # Metal settings
    "MTL_ENABLE_DEBUG_INFO": BuildSetting(value="INCLUDE_SOURCE"),
    "MTL_FAST_MATH": BuildSetting(value=YesNo.YES),
    "ONLY_ACTIVE_ARCH": BuildSetting(value=YesNo.YES),
}


# Language standard mapping for compiler flags
LANGUAGE_STANDARDS = {
    "c": "GCC_C_LANGUAGE_STANDARD",
    "gnu": "GCC_C_LANGUAGE_STANDARD",
    "c++": "CLANG_CXX_LANGUAGE_STANDARD",
    "gnu++": "CLANG_CXX_LANGUAGE_STANDARD",
} 