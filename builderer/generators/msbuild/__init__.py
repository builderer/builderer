from typing import List

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace, target_full_name
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.solution import MsBuildSolution
from builderer.generators.msbuild.version import VS_VERSIONS, VisualStudioVersion

SUPPORTED_TOOLCHAINS = ["msvc"]
SUPPORTED_PLATFORMS = ["windows"]
SUPPORTED_ARCHITECTURES = ["x64", "Win32", "ARM64"]


class MsBuildGenerator:
    _version: VisualStudioVersion = VS_VERSIONS[2022]  # Default to VS 2022

    @classmethod
    def __class_getitem__(cls, vs_year: int) -> type["MsBuildGenerator"]:
        if vs_year not in VS_VERSIONS:
            raise ValueError(f"Unsupported Visual Studio version: {vs_year}")
        version = VS_VERSIONS[vs_year]
        # Create a new class dynamically for this version
        class_name = f"MsBuildGenerator_{vs_year}"
        bases = (cls,)
        namespace = {
            "_version": version,
            "__module__": cls.__module__,
        }
        return type(class_name, bases, namespace)

    def __init__(self, config: Config, workspace: Workspace):
        self.config = config
        self.workspace = workspace
        # Validate
        if self.config.toolchain not in SUPPORTED_TOOLCHAINS:
            raise ValueError(f"unsupported toolchain {self.config.toolchain}")
        if self.config.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform {self.config.platform}")
        for arch in str_iter(self.config.architecture):
            if arch not in SUPPORTED_ARCHITECTURES:
                raise ValueError(f"unsupported architecture {arch}")

    def __call__(self):
        projects = {
            target_full_name(pkg, target): MsBuildProject(
                config=self.config,
                workspace=self.workspace,
                package=pkg,
                target=target,
                version=self._version,
            )
            for pkg in self.workspace.packages.values()
            for target in pkg.targets.values()
            if isinstance(target, BuildTarget)
        }
        for project in projects.values():
            project()
        solution = MsBuildSolution(
            config=self.config,
            workspace=self.workspace,
            projects=projects,
            version=self._version,
        )
        solution()
