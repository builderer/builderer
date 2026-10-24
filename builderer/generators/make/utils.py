import os

from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Optional, Tuple

from builderer.details.naming import flat_target_name
from builderer.details.target_artifact import (
    get_target_artifact_path,
    get_target_artifact_subpath,
)
from builderer.details.targets.apple_application import AppleApplication
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_library import SwiftLibrary


def build_config_root(build_root: str, arch: str, config: str) -> str:
    return f"{build_root}/{arch}/{config}"


def mk_target_build_path(package, target):
    return Path(package.name).joinpath(f"{target.name}.mk")


# Compile-settings stamp, written next to the target's .mk file. Objects depend on
# it so changed flags, defines, includes or source locations rebuild them.
def compile_stamp_build_path(package, target):
    return Path(package.name).joinpath(f"{target.name}.compile")


# A target's intermediates: $(OBJS_ROOT)/<package>/<target>. Packages map to
# directories; the workspace-root package "." adds no directory.
def target_obj_dir(package, target) -> str:
    return f"$(OBJS_ROOT)/{PurePosixPath(package.name, target.name).as_posix()}"


# Object paths for a target's compiled sources: each source's path relative to the
# lowest common ancestor directory of all of them. Sources may come from the
# package, the target's own sandbox or other targets' sandboxes, and arrive with
# "pkg/../" segments, so paths are normalized first (commonpath is purely lexical).
# Distinct sources always get distinct paths, and none contain "..". Returns the
# absolute ancestor and {source: object path without extension suffix}.
def object_subpaths(
    srcs: Iterable[str], workspace_root
) -> Tuple[Optional[str], Dict[str, str]]:
    normalized = {
        src: os.path.normpath(os.path.join(workspace_root, src)) for src in srcs
    }
    if not normalized:
        return None, {}
    ancestor = os.path.commonpath([os.path.dirname(p) for p in normalized.values()])
    return ancestor, {
        src: Path(os.path.relpath(path, ancestor)).as_posix()
        for src, path in normalized.items()
    }


def phony_target_name(package, target):
    return flat_target_name(package.name, target.name)


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


def metal_library_output_path(config, package, target):
    assert isinstance(target, MetalLibrary)
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


# The in-bundle directory an app's resources (incl. embedded metal_library
# .bundles) are copied into, per platform. macOS apps nest resources under
# Contents/Resources; flat-bundle platforms (iOS et al.) place them at the
# bundle root. Returns "" for the bundle root. NOTE: make currently only builds
# Apple apps for macOS (PLATFORM_ARCH_FLAGS has no ios entry), so the flat-bundle
# branch is presently unreachable via make and exists for when make grows iOS.
def apple_bundle_resource_dir(platform: str) -> str:
    if platform == "macos":
        return "Contents/Resources"
    return ""


def cc_binary_output_path_workspace(config, workspace, package, target):
    assert isinstance(target, (CCBinary, SwiftBinary))
    return get_target_artifact_path(workspace, config, package, target)


def swift_library_output_path(config, package, target):
    assert isinstance(target, SwiftLibrary)
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


def swift_binary_output_path(config, package, target):
    assert isinstance(target, SwiftBinary)
    subpath = get_target_artifact_subpath(config, package.name, target).as_posix()
    return f"$(WORKSPACE_ROOT)/{subpath}"


# Internal Swift artifact paths (consumed only by other targets in the same workspace).
# These live in the target's intermediates directory and are not user-controllable.
def swift_module_path(package, target):
    """Path to the .swiftmodule produced by a SwiftLibrary."""
    assert isinstance(target, SwiftLibrary)
    return f"{swift_module_dir(package, target)}/{target.name}.swiftmodule"


def swift_module_dir(package, target):
    """Directory containing the .swiftmodule, for use as -I to downstream Swift consumers."""
    assert isinstance(target, SwiftLibrary)
    return target_obj_dir(package, target)


def swift_header_dir(package, target):
    """Directory containing the emitted C-callable header, for use as -I to downstream
    C/C++ consumers. The header filename inside this dir is target.swift_header."""
    assert isinstance(target, SwiftLibrary)
    return f"{target_obj_dir(package, target)}/include"
