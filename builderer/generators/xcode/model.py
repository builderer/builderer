"""
Xcode project file model.

This module defines the data model for an Xcode project file (.pbxproj).
It includes classes that accurately represent the object types and their relationships
as documented in the Xcode project file format.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Union, NewType, ClassVar, Set, TypeVar, Generic
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
    BUILT_PRODUCTS_DIR = (
        "BUILT_PRODUCTS_DIR"  # Path is relative to the build products directory
    )
    DEVELOPER_DIR = "DEVELOPER_DIR"  # Path is relative to the developer directory
    SDKROOT = "SDKROOT"  # Path is relative to the SDK directory
    ABSOLUTE = "ABSOLUTE"  # Path is an absolute filesystem path


# Destination subfolder specifications used in PBXCopyFilesBuildPhase
class DstSubfolderSpec(Enum):
    """Possible values for the dstSubfolderSpec property in PBXCopyFilesBuildPhase."""

    ABSOLUTE_PATH = 0  # Absolute path
    WRAPPER = 1  # App bundle
    EXECUTABLES = 2  # Executables
    RESOURCES = 3  # Resources
    JAVA_RESOURCES = 4  # Java Resources
    FRAMEWORKS = 5  # Frameworks
    SHARED_FRAMEWORKS = 6  # Shared Frameworks
    PLUGINS = 10  # Plug-ins
    SCRIPTS = 11  # Scripts
    JAVA_RESOURCES_ALT = 12  # Java Resources (alternate)
    PRODUCTS_DIRECTORY = 13  # Products Directory
    WRAPPER_ALT = 16  # Wrapper (app bundle, alternate)


# File types used in PBXFileReference
class FileType(Enum):
    """Possible file types for PBXFileReference."""

    C = "sourcecode.c.c"
    CPP = "sourcecode.cpp.cpp"
    C_HEADER = "sourcecode.c.h"
    CPP_HEADER = "sourcecode.cpp.h"
    SWIFT = "sourcecode.swift"
    OBJC = "sourcecode.c.objc"
    OBJCPP = "sourcecode.cpp.objcpp"
    XIB = "file.xib"
    STORYBOARD = "file.storyboard"
    PLIST = "text.plist.xml"
    XCCONFIG = "text.xcconfig"
    STRINGS = "text.plist.strings"
    ASSET_CATALOG = "folder.assetcatalog"
    FRAMEWORK = "wrapper.framework"
    BUNDLE = "wrapper.bundle"
    APP = "wrapper.application"
    DYLIB = "compiled.mach-o.dylib"
    TEXT = "text"
    FOLDER = "folder"
    EXECUTABLE = "compiled.mach-o.executable"

    @staticmethod
    def from_extension(ext: str) -> "FileType":
        """
        Get the file type from a file extension.

        Args:
            ext: The file extension (with or without the dot).

        Returns:
            The corresponding FileType.
        """
        if ext.startswith("."):
            ext = ext[1:]

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

        return ext_to_type.get(ext.lower(), FileType.TEXT)


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


class ProxyType(Enum):
    """Possible values for the proxyType property in PBXContainerItemProxy."""

    TARGET_DEPENDENCY = 1  # For target dependencies
    PRODUCT_REFERENCE = 2  # For product references

    def to_xcode(self) -> int:
        """Convert to Xcode's native integer representation."""
        return self.value


# Build setting with type-safe value
@dataclass
class BuildSetting:
    """A build setting value."""

    value: Union[YesNo, int, float, str, List[str]]


ReferenceT = TypeVar("ReferenceT", bound="XcodeObject")


@dataclass
class Reference(Generic[ReferenceT]):
    """
    A reference to another object in the project file.

    Type Args:
        ReferenceT: The type of object being referenced. Must be a subclass of XcodeObject.
    """

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
class PBXFileReference(XcodeObject):
    """A file reference in the project. Represents a file on disk."""

    name: str
    path: str
    sourceTree: SourceTree
    fileType: Optional[FileType] = None
    fileEncoding: int = 4  # UTF-8 encoding, required by Xcode format

    def key(self) -> str:
        """Use path for file reference key."""
        return f"PBXFileReference:{self.path}"


@dataclass
class PBXBuildFile(XcodeObject):
    """A build file entry in the project.

    This represents a file that is included in a target's build phase.
    """

    fileRef: Reference[PBXFileReference]  # Reference to the file
    name: str  # Name of the file
    settings: Optional[Dict[str, str]] = None  # Build settings for this file
    explicitFileType: Optional[FileType] = None  # Explicit file type

    def key(self) -> str:
        return f"PBXBuildFile:{self.fileRef.id}:{self.name}"


@dataclass
class PBXSourcesBuildPhase(XcodeObject):
    """A sources build phase in the project. Compiles source files."""

    files: List[Reference[PBXFileReference]]
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        """Use class name for build phase key."""
        return f"{self.__class__.__name__}"


@dataclass
class PBXHeadersBuildPhase(XcodeObject):
    """A headers build phase in the project. Copies header files."""

    files: List[Reference[PBXFileReference]]
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        """Use class name for build phase key."""
        return f"{self.__class__.__name__}"


@dataclass
class PBXFrameworksBuildPhase(XcodeObject):
    """A frameworks build phase in the project. Links with frameworks."""

    files: List[Reference[PBXFileReference]]
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        """Use class name for build phase key."""
        return f"{self.__class__.__name__}"


@dataclass
class PBXResourcesBuildPhase(XcodeObject):
    """A resources build phase in the project. Copies resource files."""

    files: List[Reference[PBXFileReference]]
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        """Use class name for build phase key."""
        return f"{self.__class__.__name__}"


@dataclass
class PBXCopyFilesBuildPhase(XcodeObject):
    """A copy files build phase in the project. Copies files to a specified location."""

    files: List[Reference[PBXFileReference]]
    dstPath: str
    dstSubfolderSpec: DstSubfolderSpec
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        """Use class name, destination path and subfolder spec for build phase key."""
        return f"{self.__class__.__name__}:{self.dstPath}:{self.dstSubfolderSpec.name}"


@dataclass
class PBXShellScriptBuildPhase(XcodeObject):
    """A shell script build phase in the project. Runs a shell script."""

    files: List[Reference[PBXFileReference]]
    shellScript: str
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0
    inputPaths: List[str] = field(default_factory=list)
    outputPaths: List[str] = field(default_factory=list)
    shellPath: str = "/bin/sh"

    def key(self) -> str:
        """Use class name and script for build phase key."""
        return f"{self.__class__.__name__}:{hash(self.shellScript)}"


@dataclass
class PBXGroup(XcodeObject):
    """A group in the project. Represents a group or folder in the project navigator."""

    name: str
    sourceTree: SourceTree
    children: List[Reference[PBXFileReference]]
    path: Optional[str] = None
    group_id: Optional[str] = None  # Optional unique identifier for the group

    def key(self) -> str:
        """Use name, path (if available), and group_id (if available) for group keys."""
        if self.path:
            return f"PBXGroup:{self.name}:{self.path}"
        elif self.group_id:
            return f"PBXGroup:{self.name}:{self.group_id}"
        return f"PBXGroup:{self.name}"


@dataclass
class PBXVariantGroup(XcodeObject):
    """A variant group in the project. For localized resources."""

    name: str
    children: List[Reference[PBXFileReference]]
    sourceTree: SourceTree
    path: Optional[str] = None

    def key(self) -> str:
        """Use name and path (if available) for variant group keys."""
        if self.path:
            return f"PBXVariantGroup:{self.name}:{self.path}"
        return f"PBXVariantGroup:{self.name}"


@dataclass
class XCVersionGroup(XcodeObject):
    """A version group in the project. Represents a versioned Core Data model."""

    name: str
    children: List[Reference[PBXFileReference]]
    currentVersion: Reference[PBXFileReference]
    sourceTree: SourceTree
    path: Optional[str] = None
    versionGroupType: str = "wrapper.xcdatamodel"

    def key(self) -> str:
        """Use name, path, and version group type for version group key."""
        path_part = f":{self.path}" if self.path else ""
        return f"XCVersionGroup:{self.name}{path_part}:{self.versionGroupType}"


@dataclass
class PBXContainerItemProxy(XcodeObject):
    """A proxy for referencing items in other projects.

    This represents a reference to an item in another project, such as a target
    or a product.
    """

    containerPortal: str  # ID of the PBXProject
    remoteGlobalIDString: str  # ID of the referenced item
    remoteInfo: str  # Name of the referenced item
    proxyType: ProxyType = ProxyType.TARGET_DEPENDENCY  # Type of proxy

    def key(self) -> str:
        return f"PBXContainerItemProxy:{self.containerPortal}:{self.remoteGlobalIDString}:{self.remoteInfo}"


@dataclass
class PBXReferenceProxy(XcodeObject):
    """A proxy for referencing products from other projects.

    This represents a reference to a product (like a library or framework) that
    is built by another project.
    """

    remoteRef: Reference[
        PBXContainerItemProxy
    ]  # Points to proxy that describes how to get the file
    path: str  # Path to the product
    sourceTree: SourceTree = SourceTree.BUILT_PRODUCTS_DIR
    fileType: Optional[FileType] = None  # Type of the referenced file

    def key(self) -> str:
        file_type = self.fileType.name if self.fileType else "None"
        return f"PBXReferenceProxy:{self.remoteRef.id}:{self.path}:{self.sourceTree.name}:{file_type}"


@dataclass
class PBXTargetDependency(XcodeObject):
    """A dependency between targets.

    This represents that one target depends on another target, either in the
    same project or in another project.
    """

    targetProxy: Reference[
        PBXContainerItemProxy
    ]  # Points to proxy that describes the target
    target: Optional[str] = (
        None  # Optional ID of local target (only if in same project)
    )

    def key(self) -> str:
        target_id = self.target if self.target else "None"
        return f"PBXTargetDependency:{self.targetProxy.id}:{target_id}"


@dataclass
class PBXBuildRule(XcodeObject):
    """Build rule. Defines how to process a file of a given type."""

    compilerSpec: str
    fileType: str
    isEditable: int
    filePatterns: Optional[str] = None
    inputFiles: List[str] = field(default_factory=list)
    outputFiles: List[str] = field(default_factory=list)
    script: Optional[str] = None
    runOncePerArchitecture: Optional[int] = None

    def key(self) -> str:
        """Use compiler spec and file type for build rule key."""
        return f"PBXBuildRule:{self.compilerSpec}:{self.fileType}"


@dataclass
class XCBuildConfiguration(XcodeObject):
    """A build configuration in the project. Contains build settings."""

    name: str
    buildSettings: Dict[str, BuildSetting]
    baseConfigurationReference: Optional[Reference[PBXFileReference]] = None

    def key(self) -> str:
        """Use name for build configuration key."""
        return f"XCBuildConfiguration:{self.name}"


@dataclass
class PBXNativeTarget(XcodeObject):
    """A native target in the project. Represents a build target."""

    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    buildPhases: List[
        Reference[
            Union[
                PBXSourcesBuildPhase,
                PBXHeadersBuildPhase,
                PBXFrameworksBuildPhase,
                PBXResourcesBuildPhase,
                PBXCopyFilesBuildPhase,
                PBXShellScriptBuildPhase,
            ]
        ]
    ]
    dependencies: List[Reference[PBXTargetDependency]]
    productName: str
    productReference: Reference[PBXFileReference]
    productType: ProductType

    def key(self) -> str:
        """Use name for native target key."""
        return f"PBXNativeTarget:{self.name}"


@dataclass
class PBXAggregateTarget(XcodeObject):
    """An aggregate target in the project. Groups several targets."""

    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    buildPhases: List[Reference[PBXBuildFile]]
    dependencies: List[Reference[PBXTargetDependency]] = field(default_factory=list)
    buildRules: List[Reference[PBXBuildRule]] = field(default_factory=list)
    productName: Optional[str] = None

    def key(self) -> str:
        """Use name for aggregate target key."""
        return f"PBXAggregateTarget:{self.name}"


@dataclass
class PBXLegacyTarget(XcodeObject):
    """A legacy target in the project. Uses an external build system."""

    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    buildPhases: List[Reference[PBXBuildFile]]
    buildToolPath: str
    buildArgumentsString: str
    passBuildSettingsInEnvironment: int
    dependencies: List[Reference[PBXTargetDependency]] = field(default_factory=list)
    buildRules: List[Reference[PBXBuildRule]] = field(default_factory=list)
    productName: Optional[str] = None
    buildWorkingDirectory: str = ""

    def key(self) -> str:
        """Use name and build tool path for target key."""
        return f"PBXLegacyTarget:{self.name}:{self.buildToolPath}"


@dataclass
class PBXProject(XcodeObject):
    """The project object. The root object of the project."""

    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    mainGroup: Reference[PBXGroup]
    productRefGroup: Reference[PBXGroup]
    targets: List[
        Reference[Union[PBXNativeTarget, PBXAggregateTarget, PBXLegacyTarget]]
    ]
    compatibilityVersion: str = "Xcode 14.0"
    developmentRegion: str = "en"
    hasScannedForEncodings: int = 1
    knownRegions: List[str] = field(default_factory=lambda: ["en", "Base"])
    projectDirPath: str = ""
    projectRoot: str = ""
    targetDependencies: List[Reference[PBXTargetDependency]] = field(
        default_factory=list
    )

    def key(self) -> str:
        """Use name for project key."""
        return f"PBXProject:{self.name}"


@dataclass
class XCConfigurationList(XcodeObject):
    """A configuration list in the project. Holds a list of build configurations."""

    buildConfigurations: List[Reference[XCBuildConfiguration]]
    defaultConfigurationIsVisible: int = 0
    defaultConfigurationName: str = "Release"

    def key(self) -> str:
        """Use configurations and default name for config list key."""
        if self.buildConfigurations:
            return f"XCConfigurationList:{self.buildConfigurations[0].id}:{self.defaultConfigurationName}"
        return f"XCConfigurationList:{self.defaultConfigurationName}"


# Complete project representation
@dataclass
class XcodeProject:
    """An Xcode project. Contains all objects needed to generate a project file."""

    fileReferences: List[PBXFileReference]
    groups: List[PBXGroup]
    buildFiles: List[PBXBuildFile]
    buildPhases: List[
        Union[
            PBXSourcesBuildPhase,
            PBXHeadersBuildPhase,
            PBXFrameworksBuildPhase,
            PBXResourcesBuildPhase,
            PBXCopyFilesBuildPhase,
            PBXShellScriptBuildPhase,
        ]
    ]
    nativeTargets: List[PBXNativeTarget]
    project: PBXProject
    buildConfigurations: List[XCBuildConfiguration]
    configurationLists: List[XCConfigurationList]
    variantGroups: List[PBXVariantGroup] = field(default_factory=list)
    versionGroups: List[XCVersionGroup] = field(default_factory=list)
    targetDependencies: List[PBXTargetDependency] = field(default_factory=list)
    containerItemProxies: List[PBXContainerItemProxy] = field(default_factory=list)
    referenceProxies: List[PBXReferenceProxy] = field(default_factory=list)
    buildRules: List[PBXBuildRule] = field(default_factory=list)
    aggregateTargets: List[PBXAggregateTarget] = field(default_factory=list)
    legacyTargets: List[PBXLegacyTarget] = field(default_factory=list)


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
