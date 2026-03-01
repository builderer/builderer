from pathlib import Path

from builderer.details.target_artifact import (
    get_target_artifact_path,
    get_target_artifact_subpath,
)
from builderer.details.targets.apple_application import AppleApplication
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary


def build_config_root(build_root: str, arch: str, config: str) -> str:
    return f"{build_root}/{arch}/{config}"


def mk_target_build_path(package, target):
    return Path(package.name).joinpath(f"{target.name}.mk")


def phony_target_name(package, target):
    return f"{package.name}@{target.name}"


def is_header_only_library(target):
    if isinstance(target, CCLibrary):
        return not bool(target.srcs)
    else:
        return False


def is_apple_platform(platform_name: str):
    APPLE_PLATFORMS = {
        "macos",
        "ios",
    }
    return platform_name in APPLE_PLATFORMS


def cc_library_output_path(config, package, target):
    assert not is_header_only_library(target)
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


def cc_binary_output_path(config, package, target):
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


def apple_application_output_path(config, package, target):
    assert isinstance(target, AppleApplication)
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


def cc_binary_output_path_workspace(config, workspace, package, target):
    assert isinstance(target, CCBinary)
    return get_target_artifact_path(workspace, config, package, target)
