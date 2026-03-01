from copy import deepcopy
from pathlib import Path
from typing import Optional

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.package import Package
from builderer.details.targets.apple_application import AppleApplication
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import BuildTarget
from builderer.details.variable_expansion import resolve_conditionals
from builderer.details.workspace import Workspace


LIBRARY_NAMING_BY_PLATFORM = {
    "windows": ("", ".lib"),
    "linux": ("lib", ".a"),
    "macos": ("lib", ".a"),
    "emscripten": ("lib", ".a"),
}

BINARY_EXTENSION_BY_PLATFORM = {
    "windows": ".exe",
    "linux": "",
    "macos": "",
    "emscripten": "",
}


def _default_artifact_filename(config: Config, target: BuildTarget) -> str:
    if isinstance(target, CCLibrary):
        prefix, extension = LIBRARY_NAMING_BY_PLATFORM[config.platform]
        return f"{prefix}{target.name}{extension}"
    if isinstance(target, CCBinary):
        extension = BINARY_EXTENSION_BY_PLATFORM[config.platform]
        return f"{target.name}{extension}"
    if isinstance(target, AppleApplication):
        return f"{target.name}.app"
    raise TypeError(f"unsupported build target type '{type(target).__name__}'")


def _default_artifact_subpath(config, package_name: str, target: BuildTarget) -> Path:
    if isinstance(target, CCLibrary):
        kind = "libs"
    elif isinstance(target, CCBinary):
        kind = "binaries"
    elif isinstance(target, AppleApplication):
        kind = "applications"
    else:
        raise TypeError(f"unsupported build target type '{type(target).__name__}'")
    return Path(config.build_root).joinpath(
        ".artifacts",
        str(config.architecture),
        str(config.build_config),
        str(config.buildtool),
        kind,
        package_name,
        _default_artifact_filename(config, target),
    )


def get_target_artifact_subpath(config, package_name: str, target: BuildTarget) -> Path:
    output_path = resolve_conditionals(config=config, value=target.output_path)
    if output_path:
        return Path(output_path)
    return _default_artifact_subpath(config, package_name, target)


def _resolve_config_variant(
    config: Config, build_config: Optional[str], build_arch: Optional[str]
) -> Config:
    resolve_config = deepcopy(config)
    resolve_config.build_config = build_config or list(str_iter(config.build_config))[0]
    resolve_config.architecture = build_arch or list(str_iter(config.architecture))[0]
    return resolve_config


def get_target_artifact_path(
    workspace: Workspace,
    config: Config,
    package: Package,
    target: BuildTarget,
    build_config: Optional[str] = None,
    build_arch: Optional[str] = None,
) -> Path:
    if not isinstance(target, BuildTarget):
        raise TypeError(
            f"unsupported run target type '{type(target).__name__}' for package '{package.name}'"
        )
    resolve_config = _resolve_config_variant(config, build_config, build_arch)
    return workspace.root / get_target_artifact_subpath(
        resolve_config, package.name, target
    )
