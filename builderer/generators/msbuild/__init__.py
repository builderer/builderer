from typing import List

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace, target_full_name
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.solution import MsBuildSolution

SUPPORTED_TOOLCHAINS = ["msvc"]
SUPPORTED_PLATFORMS = ["windows"]
SUPPORTED_ARCHITECTURES = ["x64", "Win32", "ARM64"]

class MsBuildGenerator:
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
            projects=projects
        )
        solution()