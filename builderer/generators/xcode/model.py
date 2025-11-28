# Xcode project file model.
#
# This module defines the data model for an Xcode project file (.pbxproj).
# It includes classes that accurately represent the object types and their relationships
# as documented in the Xcode project file format.

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Union, NewType, ClassVar, Set, TypeVar, Generic
from abc import ABC, abstractmethod

import uuid


# Type definition for Xcode object identifiers
class XcodeID(str):
    pass


def generate_id(key: str) -> XcodeID:
    return XcodeID(uuid.uuid5(uuid.NAMESPACE_X500, key).hex.upper()[:24])


# Source Tree values used in PBXFileReference and PBXGroup
# Only safe values are enabled - others are commented out to prevent misuse
class SourceTree(Enum):
    # GROUP - ONLY for project-level singletons (main_group, products_group)
    # NEVER use for per-target items as paths would collide
    GROUP = "<group>"
    # SOURCE_ROOT - the safe default for all file references
    # Paths must be relative to workspace root and include package/target for uniqueness
    SOURCE_ROOT = "SOURCE_ROOT"
    # BUILT_PRODUCTS_DIR - for product references only
    # Paths must include package prefix for uniqueness
    BUILT_PRODUCTS_DIR = "BUILT_PRODUCTS_DIR"
    # Disabled - these are error-prone:
    # DEVELOPER_DIR = "DEVELOPER_DIR"  # Relative to Xcode install - not portable
    # SDKROOT = "SDKROOT"  # Relative to SDK - not for user files
    # ABSOLUTE = "ABSOLUTE"  # Not portable across machines


# Destination subfolder specifications used in PBXCopyFilesBuildPhase
class DstSubfolderSpec(Enum):
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
    ARCHIVE = "archive.ar"

    @staticmethod
    def from_extension(ext: str) -> "FileType":
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
    YES = "YES"
    NO = "NO"
    YES_ERROR = "YES_ERROR"
    YES_AGGRESSIVE = "YES_AGGRESSIVE"


class ProxyType(Enum):
    TARGET_DEPENDENCY = 1  # For target dependencies
    PRODUCT_REFERENCE = 2  # For product references

    def to_xcode(self) -> int:
        return self.value


# Build setting with type-safe value
@dataclass
class BuildSetting:
    value: Union[YesNo, int, float, str, List[str]]


ReferenceT = TypeVar("ReferenceT", bound="XcodeObject")


@dataclass
class Reference(Generic[ReferenceT]):
    id: XcodeID
    comment: Optional[str] = None


# Base class for all Xcode objects
@dataclass
class XcodeObject(ABC):
    # ID will be generated in __post_init__
    id: XcodeID = field(init=False)

    def __post_init__(self) -> None:
        self.id = generate_id(self.key())

    @abstractmethod
    def key(self) -> str:
        pass


# PBX* object types
@dataclass
class PBXFileReference(XcodeObject):
    name: str
    path: str
    sourceTree: SourceTree
    fileType: Optional[FileType] = None
    fileEncoding: int = 4  # UTF-8 encoding, required by Xcode format

    def key(self) -> str:
        return f"PBXFileReference:{self.path}"


@dataclass
class PBXBuildFile(XcodeObject):
    fileRef: Reference[PBXFileReference]  # Reference to the file
    name: str  # Name of the file
    target_name: str  # Name of the target this build file belongs to
    settings: Optional[Dict[str, str]] = None  # Build settings for this file
    explicitFileType: Optional[FileType] = None  # Explicit file type

    def key(self) -> str:
        return f"PBXBuildFile:{self.fileRef.id}:{self.name}:{self.target_name}"


@dataclass
class PBXSourcesBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    target_name: str  # Name of the target this build phase belongs to
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        return f"{self.__class__.__name__}:{self.target_name}"


@dataclass
class PBXHeadersBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    target_name: str  # Name of the target this build phase belongs to
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        return f"{self.__class__.__name__}:{self.target_name}"


@dataclass
class PBXFrameworksBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    target_name: str  # Name of the target this build phase belongs to
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        return f"{self.__class__.__name__}:{self.target_name}"


@dataclass
class PBXResourcesBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        return f"{self.__class__.__name__}"


@dataclass
class PBXCopyFilesBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    dstPath: str
    dstSubfolderSpec: DstSubfolderSpec
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0

    def key(self) -> str:
        return f"{self.__class__.__name__}:{self.dstPath}:{self.dstSubfolderSpec.name}"


@dataclass
class PBXShellScriptBuildPhase(XcodeObject):
    files: List[Reference[PBXBuildFile]]
    shellScript: str
    buildActionMask: int = 2147483647
    runOnlyForDeploymentPostprocessing: int = 0
    inputPaths: List[str] = field(default_factory=list)
    outputPaths: List[str] = field(default_factory=list)
    shellPath: str = "/bin/sh"

    def key(self) -> str:
        return f"{self.__class__.__name__}:{hash(self.shellScript)}"


@dataclass
class PBXGroup(XcodeObject):
    name: str
    sourceTree: SourceTree
    children: List[Reference[Union["PBXGroup", PBXFileReference]]]
    path: Optional[str] = None
    group_id: Optional[str] = None  # Optional unique identifier for the group

    def key(self) -> str:
        if self.path:
            return f"PBXGroup:{self.name}:{self.path}"
        elif self.group_id:
            return f"PBXGroup:{self.name}:{self.group_id}"
        return f"PBXGroup:{self.name}"


@dataclass
class PBXVariantGroup(XcodeObject):
    name: str
    children: List[Reference[PBXFileReference]]
    sourceTree: SourceTree
    path: Optional[str] = None

    def key(self) -> str:
        if self.path:
            return f"PBXVariantGroup:{self.name}:{self.path}"
        return f"PBXVariantGroup:{self.name}"


@dataclass
class XCVersionGroup(XcodeObject):
    name: str
    children: List[Reference[PBXFileReference]]
    currentVersion: Reference[PBXFileReference]
    sourceTree: SourceTree
    path: Optional[str] = None
    versionGroupType: str = "wrapper.xcdatamodel"

    def key(self) -> str:
        path_part = f":{self.path}" if self.path else ""
        return f"XCVersionGroup:{self.name}{path_part}:{self.versionGroupType}"


@dataclass
class PBXContainerItemProxy(XcodeObject):
    containerPortal: str  # ID of the PBXProject
    remoteGlobalIDString: str  # ID of the referenced item
    remoteInfo: str  # Name of the referenced item
    proxyType: ProxyType = ProxyType.TARGET_DEPENDENCY  # Type of proxy

    def key(self) -> str:
        return f"PBXContainerItemProxy:{self.containerPortal}:{self.remoteGlobalIDString}:{self.remoteInfo}"


@dataclass
class PBXReferenceProxy(XcodeObject):
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
    compilerSpec: str
    fileType: str
    isEditable: int
    filePatterns: Optional[str] = None
    inputFiles: List[str] = field(default_factory=list)
    outputFiles: List[str] = field(default_factory=list)
    script: Optional[str] = None
    runOncePerArchitecture: Optional[int] = None

    def key(self) -> str:
        return f"PBXBuildRule:{self.compilerSpec}:{self.fileType}"


@dataclass
class XCBuildConfiguration(XcodeObject):
    name: str
    buildSettings: Dict[str, BuildSetting]
    baseConfigurationReference: Optional[Reference[PBXFileReference]] = None
    owner: Optional[str] = None  # disambiguate configs across project/targets

    def key(self) -> str:
        owner_part = self.owner if self.owner else "GLOBAL"
        return f"XCBuildConfiguration:{owner_part}:{self.name}"


@dataclass
class PBXNativeTarget(XcodeObject):
    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    buildPhases: List[
        Reference[
            Union[
                PBXSourcesBuildPhase,
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
        return f"PBXNativeTarget:{self.name}"


@dataclass
class PBXAggregateTarget(XcodeObject):
    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    buildPhases: List[Reference[PBXBuildFile]]
    dependencies: List[Reference[PBXTargetDependency]] = field(default_factory=list)
    buildRules: List[Reference[PBXBuildRule]] = field(default_factory=list)
    productName: Optional[str] = None

    def key(self) -> str:
        return f"PBXAggregateTarget:{self.name}"


@dataclass
class PBXLegacyTarget(XcodeObject):
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
        return f"PBXLegacyTarget:{self.name}:{self.buildToolPath}"


@dataclass
class PBXProject(XcodeObject):
    name: str
    buildConfigurationList: Reference[XCBuildConfiguration]
    mainGroup: Reference[PBXGroup]
    productRefGroup: Reference[PBXGroup]
    targets: List[
        Reference[Union[PBXNativeTarget, PBXAggregateTarget, PBXLegacyTarget]]
    ]
    buildIndependentTargetsInParallel: int = 1
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
        return f"PBXProject:{self.name}"


@dataclass
class XCConfigurationList(XcodeObject):
    buildConfigurations: List[Reference[XCBuildConfiguration]]
    defaultConfigurationIsVisible: int = 0
    defaultConfigurationName: str = "Release"
    owner: Optional[str] = None  # disambiguate lists across project/targets

    def key(self) -> str:
        owner_part = self.owner if self.owner else "GLOBAL"
        if self.buildConfigurations:
            ids = ",".join(ref.id for ref in self.buildConfigurations)
            return f"XCConfigurationList:{owner_part}:{ids}:{self.defaultConfigurationName}"
        return f"XCConfigurationList:{owner_part}:{self.defaultConfigurationName}"


# Complete project representation
@dataclass
class XcodeProject:
    fileReferences: List[PBXFileReference]
    groups: List[PBXGroup]
    buildFiles: List[PBXBuildFile]
    buildPhases: List[
        Union[
            PBXSourcesBuildPhase,
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
