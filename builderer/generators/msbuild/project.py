import os

from copy import deepcopy
from pathlib import Path
from typing import TextIO, List
from xml.dom.minidom import Node, Document, Element

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.package import Package
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import BuildTarget
from builderer.details.variable_expansion import resolve_conditionals
from builderer.details.workspace import Workspace
from builderer.generators.msbuild.utils import as_msft_path, make_guid, msvc_file_rule


def owner_doc(xnode: Node) -> Document:
    if isinstance(xnode, Document):
        return xnode
    else:
        assert xnode.ownerDocument
        return xnode.ownerDocument


def append_comment(xparent: Node, value: str):
    xparent.appendChild(owner_doc(xparent).createComment(value))


def append_text(xparent: Node, value: str) -> Node:
    xtext = owner_doc(xparent).createTextNode(value)
    xparent.appendChild(xtext)
    return xtext


def append_element(xparent: Node, name: str) -> Element:
    xelement = owner_doc(xparent).createElement(name)
    xparent.appendChild(xelement)
    return xelement


def append_text_element(xparent: Node, name: str, value: str) -> Element:
    xelement = append_element(xparent, name)
    append_text(xelement, value)
    return xelement


def write_xml_to_path(xdoc, path: Path):
    # Generate new XML file contents...
    new_xml = xdoc.toprettyxml(indent="  ", newl="\n", encoding="utf-8")
    # Check if previous version matches and early exit to avoid bumping timestamps unnecessarily...
    try:
        with path.open("rb") as f:
            old_xml = f.read()
        if old_xml == new_xml:
            return
    except FileNotFoundError:
        pass
    # Write new XML contents if needed...
    with path.open("wb") as f:
        f.write(new_xml)


def get_project_guid(target: BuildTarget):
    return make_guid(os.path.join(target.workspace_root, target.name))


def get_project_root(config: Config, target: BuildTarget):
    return Path(config.build_root).joinpath(target.workspace_root)


def get_project_to_target(config: Config, target: BuildTarget):
    return Path(os.path.relpath(target.root, get_project_root(config, target)))


def get_vcxproj_path(config: Config, target: BuildTarget):
    return get_project_root(config, target).joinpath(f"{target.name}.vcxproj")


def get_filters_path(config: Config, target: BuildTarget):
    return get_project_root(config, target).joinpath(f"{target.name}.vcxproj.filters")


def bake_config(config: Config, architecture: str, build_config: str):
    config = deepcopy(config)
    config.architecture = architecture
    config.build_config = build_config
    return config


def unique_list(l: list):
    seen: set = set()

    def visit(x):
        if x not in seen:
            seen.add(x)
            return True
        return False

    return [x for x in l if visit(x)]


# Mapping of known compiler flags to MSBuild settings...
CFLAG_MAPPING = {
    # C version
    "/stc:c11": ("LanguageStandard_C", "stdc11"),
    "/stc:c17": ("LanguageStandard_C", "stdc17"),
    # C++ version
    "/std:c++14": ("LanguageStandard", "stdcpp14"),
    "/std:c++17": ("LanguageStandard", "stdcpp17"),
    "/std:c++20": ("LanguageStandard", "stdcpp20"),
    "/std:c++latest": ("LanguageStandard", "stdcpplatest"),
    # Warnings
    "/W0": ("WarningLevel", "TurnOffAllWarnings"),
    "/W1": ("WarningLevel", "Level1"),
    "/W2": ("WarningLevel", "Level2"),
    "/W3": ("WarningLevel", "Level3"),
    "/W4": ("WarningLevel", "Level4"),
    "/Wall": ("WarningLevel", "EnableAllWarnings"),
    "/WX": ("TreatWarningAsError", "true"),
    "/WX-": ("TreatWarningAsError", "false"),
    # Optimization
    "/Od": ("Optimization", "Disabled"),
    "/O1": ("Optimization", "MinSpace"),
    "/O2": ("Optimization", "MaxSpeed"),
    "/Ox": ("Optimization", "Full"),
    "/GL": ("WholeProgramOptimization", "true"),
    # Runtime Library
    "/MD": ("RuntimeLibrary", "MultiThreadedDLL"),
    "/MD": ("RuntimeLibrary", "MultiThreadedDebugDLL"),
    "/MT": ("RuntimeLibrary", "MultiThreaded"),
    "/MTd": ("RuntimeLibrary", "MultiThreadedDebug"),
    # Security Development Lifecycle checks
    "/sdl": ("SDLCheck", "true"),
    "/sdl-": ("SDLCheck", "false"),
    # Security Checks
    "/GS": ("BufferSecurityCheck", "true"),
    "/GS-": ("BufferSecurityCheck", "false"),
    # Runtime Checks
    "/RTCs": ("BasicRuntimeChecks", "StackFrameRuntimeCheck"),
    "/RTCu": ("BasicRuntimeChecks", "UninitializedLocalUsageCheck"),
    "/RTC1": ("BasicRuntimeChecks", "EnableFastChecks"),
    # Conformance
    "/permissive": ("ConformanceMode", "false"),
    "/permissive-": ("ConformanceMode", "true"),
    # Debug info
    "/Z7": ("DebugInformationFormat", "OldStyle"),
    "/Zi": ("DebugInformationFormat", "ProgramDatabase"),
    "/ZI": ("DebugInformationFormat", "EditAndContinue"),
    # FPU Precision
    "/fp:fast": ("FloatingPointModel", "Fast"),
    "/fp:precise": ("FloatingPointModel", "Precise"),
    "/fp:strict": ("FloatingPointModel", "Strict"),
    # Exceptions
    "/EHsc": ("ExceptionHandling", "Sync"),
    "/EHa": ("ExceptionHandling", "Async"),
    "/EHs": ("ExceptionHandling", "SyncCThrow"),
}

# Mapping of known linker flags to MSBuild settings...
LFLAG_MAPPING = {
    # Subsystem
    "/SUBSYSTEM:CONSOLE": ("SubSystem", "Console"),
    "/SUBSYSTEM:WINDOWS": ("SubSystem", "Windows"),
    "/SUBSYSTEM:NATIVE": ("SubSystem", "Native"),
    "/SUBSYSTEM:POSIX": ("SubSystem", "POSIX"),
    "/SUBSYSTEM:EFI_APPLICATION": ("SubSystem", "EFI Application"),
    "/SUBSYSTEM:EFI_BOOT_SERVICE_DRIVER": ("SubSystem", "EFI Boot Service Driver"),
    "/SUBSYSTEM:EFI_RUNTIME_DRIVER": ("SubSystem", "EFI Runtime"),
    # Debug info
    "/DEBUG": ("GenerateDebugInformation", "true"),
    "/DEBUG:FASTLINK": ("GenerateDebugInformation", "DebugFastLink"),
    "/DEBUG:FULL": ("GenerateDebugInformation", "DebugFull"),
}

# Default compiler settings, these override msbuild defaults either because the
# flag lags disable flags (can turn on but not off), or to otherwise provide
# sensibe defaults...
DEFAULT_COMPILE_SETTINGS = {
    # These lack explicit disable flags...
    "WholeProgramOptimization": "false",
    "DebugInformationFormat": "None",
    "BasicRuntimeChecks": "Default",
    "ExceptionHandling": "false",
    # Just sensible defaults...
    "MultiProcessorCompilation": "true",
}

# Default linker settings, because some options have no explicit disable flag...
DEFAULT_LINK_SETTINGS = {
    "GenerateDebugInformation": "false",
}


class MsBuildProject:
    PROJECT_TOOLS_VERSION = "17.0"
    FILTERS_TOOLS_VERSION = "4.0"
    VC_PROJECT_VERSION = "16.0"
    PLATFORM_TOOLSET = "v143"
    WINDOWS_TARGET_PLATFORM_VERSION = "10.0"
    CHARACTER_SET = "Unicode"

    def __init__(
        self,
        config: Config,
        workspace: Workspace,
        package: Package,
        target: BuildTarget,
    ):
        self.base_config = config
        self.workspace = workspace
        self.package = package
        self.target = target
        self.project_root = get_project_root(config, target)
        self.target_root = get_project_to_target(config, target)
        self.vcxproj_path = get_vcxproj_path(config, target)
        self.filters_path = get_filters_path(config, target)
        self.project_guid = get_project_guid(target)
        self.build_configs = [
            bake_config(config=self.base_config, architecture=a, build_config=c)
            for a in str_iter(self.base_config.architecture)
            for c in str_iter(self.base_config.build_config)
        ]

    def __call__(self):
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.generate_project()
        self.generate_filters()

    def generate_project(self):
        xdoc = Document()
        append_comment(xdoc, "Generated Automatically by Builderer")
        self._append_project(xdoc)
        write_xml_to_path(xdoc, self.vcxproj_path)

    def generate_filters(self):
        xdoc = Document()
        xproj = append_element(xdoc, "Project")
        xproj.setAttribute("ToolsVersion", self.FILTERS_TOOLS_VERSION)
        xproj.setAttribute(
            "xmlns", "http://schemas.microsoft.com/developer/msbuild/2003"
        )
        # build lists for files and filters
        all_files = sorted(
            [
                Path(file)
                for _, files in self.target.get_file_path_fields()
                for file in files
            ]
        )
        common_dir = Path(os.path.commonpath(all_files))
        filter_dirs = sorted(
            {
                dir
                for file in all_files
                for dir in Path(os.path.relpath(file, common_dir)).parents
                if dir != Path(".")
            }
        )
        # filters
        xgroup = append_element(xproj, "ItemGroup")
        for filter in filter_dirs:
            xfilter = append_element(xgroup, "Filter")
            xfilter.setAttribute("Include", as_msft_path(filter))
        # files
        xgroup = append_element(xproj, "ItemGroup")
        for file in all_files:
            xfile = append_element(xgroup, msvc_file_rule(file))
            xfile.setAttribute(
                "Include", as_msft_path(os.path.relpath(file, self.project_root))
            )
            append_text_element(
                xfile, "Filter", as_msft_path(os.path.relpath(file.parent, common_dir))
            )
        # write
        write_xml_to_path(xdoc, self.filters_path)

    @property
    def configuration_type(self):
        if isinstance(self.target, CCLibrary):
            # If no source files, use empty string to represent header-only library
            return "StaticLibrary" if self.target.srcs else ""
        elif isinstance(self.target, CCBinary):
            return "Application"
        else:
            raise RuntimeError("Unsupported target type")

    @property
    def requires_comnpiling(self):
        return isinstance(self.target, (CCLibrary, CCBinary))

    @property
    def requires_linking(self):
        return isinstance(self.target, CCBinary)

    ### vcxproj support

    def _append_project_configurations(self, xparent: Node):
        xgroup = append_element(xparent, "ItemGroup")
        xgroup.setAttribute("Label", "ProjectConfigurations")
        for config in self.build_configs:
            xprojconfig = append_element(xgroup, "ProjectConfiguration")
            xprojconfig.setAttribute(
                "Include", f"{config.build_config}|{config.architecture}"
            )
            xconfig = append_element(xprojconfig, "Configuration")
            append_text(xconfig, config.build_config)
            xplatform = append_element(xprojconfig, "Platform")
            append_text(xplatform, config.architecture)

    def _append_globals(self, xparent: Node):
        xgroup = append_element(xparent, "PropertyGroup")
        xgroup.setAttribute("Label", "Globals")
        append_text_element(xgroup, "VCProjectVersion", self.VC_PROJECT_VERSION)
        append_text_element(xgroup, "ProjectGuid", self.project_guid)

    def _append_dependencies(self, xparent: Node):
        deps = [
            dep
            for _, dep in self.workspace.direct_dependencies(self.package, self.target)
            if isinstance(dep, BuildTarget)
        ]
        if not deps:
            return
        xgroup = append_element(xparent, "ItemGroup")
        append_comment(xgroup, "deps")
        for dep in deps:
            xref = append_element(xgroup, "ProjectReference")
            xref.setAttribute(
                "Include",
                as_msft_path(
                    os.path.relpath(
                        get_vcxproj_path(self.base_config, dep), self.project_root
                    )
                ),
            )

    def _append_source_files(self, xparent: Node, group_name: str, files: List[str]):
        xgroup = append_element(xparent, "ItemGroup")
        append_comment(xgroup, group_name)
        for file in files:
            append_element(xgroup, msvc_file_rule(Path(file))).setAttribute(
                "Include", as_msft_path(os.path.relpath(file, self.project_root))
            )

    def _append_config_properties(self, xparent: Node, config: Config):
        xgroup = append_element(xparent, "PropertyGroup")
        xgroup.setAttribute(
            "Condition",
            f"'$(Configuration)|$(Platform)'=='{config.build_config}|{config.architecture}'",
        )
        xgroup.setAttribute("Label", "Configuration")
        append_text_element(xgroup, "ConfigurationType", self.configuration_type)
        append_text_element(xgroup, "UseDebugLibraries", "true")  # TODO
        append_text_element(xgroup, "PlatformToolset", self.PLATFORM_TOOLSET)
        append_text_element(xgroup, "CharacterSet", self.CHARACTER_SET)
        if isinstance(self.target, CCBinary):
            out_path = as_msft_path(
                os.path.relpath(
                    os.path.dirname(
                        resolve_conditionals(
                            config=config, value=self.target.output_path
                        )
                    ),
                    self.project_root,
                )
            )
            append_text_element(xgroup, "OutDir", f"$(ProjectDir)\\{out_path}\\")
        else:
            append_text_element(
                xgroup,
                "OutDir",
                "$(ProjectDir)\\.lib\\$(MSBuildProjectName)\\$(Platform)-$(Configuration)\\",
            )
        append_text_element(
            xgroup,
            "IntDir",
            "$(ProjectDir)\\.obj\\$(MSBuildProjectName)\\$(Platform)-$(Configuration)\\",
        )

    def _append_local_app_data_platform(self, xparent: Node, config: Config):
        xsheet = append_element(xparent, "ImportGroup")
        xsheet.setAttribute("Label", "PropertySheets")
        xsheet.setAttribute(
            "Condition",
            f"'$(Configuration)|$(Platform)'=='{config.build_config}|{config.architecture}'",
        )
        xprop = append_element(xsheet, "Import")
        xprop.setAttribute(
            "Project", "$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props"
        )
        xprop.setAttribute(
            "Condition", "exists('$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props')"
        )
        xprop.setAttribute("Label", "LocalAppDataPlatform")

    def _append_config_definition_group(self, xparent: Node, config: Config):
        xgroup = append_element(xparent, "ItemDefinitionGroup")
        xgroup.setAttribute(
            "Condition",
            f"'$(Configuration)|$(Platform)'=='{config.build_config}|{config.architecture}'",
        )
        if self.requires_comnpiling:
            self._append_compile_config(xgroup, config=config)
        if self.requires_linking:
            self._append_link_config(xgroup, config=config)

    def _append_compile_config(self, xparent: Node, config: Config):
        assert isinstance(self.target, (CCLibrary, CCBinary))
        xcompile = append_element(xparent, "ClCompile")
        # Parse out compiler flags into settings when possible...
        compile_settings = DEFAULT_COMPILE_SETTINGS.copy()
        unknown_cflags = []
        compile_flags = unique_list(
            resolve_conditionals(config=config, value=self.target.c_flags)
            + resolve_conditionals(config=config, value=self.target.cxx_flags)
        )
        for cflag in compile_flags:
            if cflag in CFLAG_MAPPING:
                opt_name, opt_value = CFLAG_MAPPING[cflag]
                compile_settings[opt_name] = opt_value
            else:
                unknown_cflags.append(cflag)
        # Apply compiler settings...
        for k, v in compile_settings.items():
            append_text_element(xcompile, k, v)
        # Remaining unknown compiler flags get passed through...
        append_text_element(xcompile, "AdditionalOptions", " ".join(unknown_cflags))
        # Defines...
        defines = [
            *resolve_conditionals(config=config, value=self.target.private_defines)
        ]
        if isinstance(self.target, CCLibrary):
            defines.extend(
                resolve_conditionals(config=config, value=self.target.public_defines)
            )
        defines.extend(
            [
                define
                for _, dep_target in self.workspace.all_dependencies(
                    self.package, self.target
                )
                if isinstance(dep_target, CCLibrary)
                for define in resolve_conditionals(
                    config=config, value=dep_target.public_defines
                )
            ]
        )
        append_text_element(xcompile, "PreprocessorDefinitions", ";".join(defines))
        # Header search paths...
        includes = []
        if isinstance(self.target, (CCLibrary, CCBinary)):
            includes.extend(
                [
                    as_msft_path(os.path.relpath(include, self.project_root))
                    for include in resolve_conditionals(
                        config=config, value=self.target.private_includes
                    )
                ]
            )
        if isinstance(self.target, CCLibrary):
            includes.extend(
                [
                    as_msft_path(os.path.relpath(include, self.project_root))
                    for include in resolve_conditionals(
                        config=config, value=self.target.public_includes
                    )
                ]
            )
        includes.extend(
            [
                as_msft_path(os.path.relpath(include, self.project_root))
                for _, dep_target in self.workspace.all_dependencies(
                    self.package, self.target
                )
                if isinstance(dep_target, CCLibrary)
                for include in resolve_conditionals(
                    config=config, value=dep_target.public_includes
                )
            ]
        )
        append_text_element(
            xcompile, "AdditionalIncludeDirectories", ";".join(includes)
        )

    def _append_link_config(self, xparent: Node, config: Config):
        assert isinstance(self.target, CCBinary)
        xlink = append_element(xparent, "Link")
        # Parse out compiler flags into settings when possible...
        link_settings = DEFAULT_LINK_SETTINGS.copy()
        unknown_lflags = []
        for cflag in resolve_conditionals(config=config, value=self.target.link_flags):
            if cflag in LFLAG_MAPPING:
                opt_name, opt_value = LFLAG_MAPPING[cflag]
                link_settings[opt_name] = opt_value
            else:
                unknown_lflags.append(cflag)
        # Apply compiler settings...
        for k, v in link_settings.items():
            append_text_element(xlink, k, v)
        # Remaining unknown compiler flags get passed through...
        append_text_element(xlink, "AdditionalOptions", " ".join(unknown_lflags))
        # Ensure we link to our dependencies
        xprojref = append_element(xparent, "ProjectReference")
        append_text_element(xprojref, "LinkLibraryDependencies", "true")

    def _append_project(self, xparent: Node):
        xproj = append_element(xparent, "Project")
        xproj.setAttribute("DefaultTargets", "Build")
        xproj.setAttribute("ToolsVersion", self.PROJECT_TOOLS_VERSION)
        xproj.setAttribute(
            "xmlns", "http://schemas.microsoft.com/developer/msbuild/2003"
        )
        # Config
        self._append_project_configurations(xproj)
        self._append_globals(xproj)
        # Dependencies
        self._append_dependencies(xproj)
        # Source Files
        for group_name, files in self.target.get_file_path_fields():
            self._append_source_files(xproj, group_name, files)
        # Import default cpp properties
        append_element(xproj, "Import").setAttribute(
            "Project", "$(VCTargetsPath)\\Microsoft.Cpp.Default.props"
        )
        # Configuration properties
        for config in self.build_configs:
            self._append_config_properties(xproj, config=config)
        # Disable VCPKG
        xvcpkg = append_element(xproj, "PropertyGroup")
        xvcpkg.setAttribute("Label", "Vcpkg")
        append_text_element(xvcpkg, "VcpkgEnabled", "false")
        # Import cpp properties
        append_element(xproj, "Import").setAttribute(
            "Project", "$(VCTargetsPath)\\Microsoft.Cpp.props"
        )
        # Import app data platform properties
        # TODO: is this needed?
        for config in self.build_configs:
            self._append_local_app_data_platform(xproj, config=config)
        # ItemDefinitionGroup
        for config in self.build_configs:
            self._append_config_definition_group(xproj, config=config)
        # Import cpp targets
        append_element(xproj, "Import").setAttribute(
            "Project", "$(VCTargetsPath)\\Microsoft.Cpp.targets"
        )
