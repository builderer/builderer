"""Shared in-memory factories for builderer's unit tests.

Everything here builds objects directly in memory -- no files are read or
written, no user modules are loaded off disk. Tests construct inputs with these
helpers, call a function/method, and assert on the return value or emitted
string.
"""

from pathlib import Path

from builderer import Config
from builderer.details.package import Package
from builderer.details.targets.apple_application import AppleApplication
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import Target
from builderer.details.workspace import Workspace


def make_config(**overrides) -> Config:
    """A complete Config with windows-ish defaults; override per test.

    Note that ``build_config`` and ``architecture`` default to single-element
    lists, mirroring how real configs are declared (they get baked down to
    scalars during generation).
    """
    params = dict(
        buildtool="vs2022",
        toolchain="msvc",
        platform="windows",
        sandbox_root=".sandbox",
        build_root="Out/build/windows",
        build_config=["debug"],
        architecture=["x64"],
    )
    params.update(overrides)
    return Config(**params)


def make_cc_library(name: str, *, workspace_root: str = "pkg", **kwargs) -> CCLibrary:
    return CCLibrary(name=name, workspace_root=workspace_root, **kwargs)


def make_cc_binary(name: str, *, workspace_root: str = "pkg", **kwargs) -> CCBinary:
    return CCBinary(name=name, workspace_root=workspace_root, **kwargs)


def make_apple_application(
    name: str, *, binary: str, info_plist: dict, workspace_root: str = "pkg", **kwargs
) -> AppleApplication:
    return AppleApplication(
        name=name,
        binary=binary,
        info_plist=info_plist,
        workspace_root=workspace_root,
        **kwargs,
    )


def make_package(name: str, targets=()) -> Package:
    """A Package with pre-built targets installed directly (no add_target rule)."""
    pkg = Package(name=name, root=Path(name))
    for target in targets:
        pkg.targets[target.name] = target
    return pkg


def make_workspace(packages) -> Workspace:
    """Build a Workspace WITHOUT running its disk-loading __init__.

    Sets ``.packages`` and ``._graph`` directly so the pure graph algorithms
    (find_target / direct_dependencies / all_dependencies / topological sort)
    can be exercised in memory. Dependency edges are derived from each target's
    ``deps`` exactly as Workspace._update_graph would.
    """
    ws = object.__new__(Workspace)
    ws.root = Path(".").resolve()
    ws.packages = {pkg.name: pkg for pkg in packages}
    ws._graph = {
        (package, target): [ws.find_target(dep, package) for dep in target.deps]
        for package in ws.packages.values()
        for target in package.targets.values()
    }
    return ws
