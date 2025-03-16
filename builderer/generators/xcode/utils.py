from pathlib import Path

from builderer.config import Config
from builderer.details.package import Package
from builderer.details.targets.target import Target


def xcode_project_parent(config: Config, pkg: Package) -> Path:
    return Path(config.build_root) / pkg.name


def xcode_project_path(config: Config, pkg: Package, target: Target) -> Path:
    return xcode_project_parent(config, pkg) / f"{target.name}.xcodeproj"
