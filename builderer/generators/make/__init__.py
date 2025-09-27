from copy import deepcopy
from pathlib import Path

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace
from builderer.generators.make.root_makefile import RootMakefile
from builderer.generators.make.target_mk import TargetMk
from builderer.generators.make.utils import build_config_root, is_header_only_library

SUPPORTED_TOOLCHAINS = ["clang", "gcc", "emscripten"]
SUPPORTED_PLATFORMS = ["linux", "macos", "emscripten"]
SUPPORTED_ARCHITECTURES = {
    "linux": [
        "x86-64",
        "i386",
        "i686",
        # Arm list from: https://gcc.gnu.org/onlinedocs/gcc/AArch64-Options.html
        "armv8-a",
        "armv8.1-a",
        "armv8.2-a",
        "armv8.3-a",
        "armv8.4-a",
        "armv8.5-a",
        "armv8.6-a",
        "armv8.7-a",
        "armv8.8-a",
        "armv8.9-a",
        "armv8-r",
        "armv9-a",
        "armv9.1-a",
        "armv9.2-a",
        "armv9.3-a",
        "armv9.4-a",
    ],
    "macos": [
        "x86_64",
        "arm64",
    ],
    "emscripten": [
        "wasm32",
    ],
}


def bake_config(config: Config, architecture: str, build_config: str):
    config = deepcopy(config)
    config.architecture = architecture
    config.build_config = build_config
    return config


class MakeGenerator:
    def __init__(self, config: Config, workspace: Workspace):
        self.base_config = config
        self.workspace = workspace
        # Validate
        if self.base_config.toolchain not in SUPPORTED_TOOLCHAINS:
            raise ValueError(f"unsupported toolchain {self.base_config.toolchain}")
        if self.base_config.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform {self.base_config.platform}")
        platform_archs = SUPPORTED_ARCHITECTURES[self.base_config.platform]
        for arch in str_iter(self.base_config.architecture):
            if arch not in platform_archs:
                raise ValueError(f"unsupported architecture {arch}")

    def __call__(self):
        makefile = RootMakefile(config=self.base_config, workspace=self.workspace)
        makefile()
        configs = [
            bake_config(self.base_config, architecture=a, build_config=c)
            for a in str_iter(self.base_config.architecture)
            for c in str_iter(self.base_config.build_config)
        ]
        for config in configs:
            mk_root = Path(
                build_config_root(
                    config.build_root, config.architecture, config.build_config
                )
            )
            target_mks = [
                TargetMk(
                    config=config,
                    workspace=self.workspace,
                    build_root=mk_root,
                    package=package,
                    target=target,
                )
                for package, target in self.workspace.targets
                if isinstance(target, BuildTarget)
                and not is_header_only_library(target)
            ]
            for mk in target_mks:
                mk()
