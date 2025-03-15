from pathlib import Path

from builderer.details.package import Package
from builderer.details.targets.target import Target


def xcode_project_path(pkg: Package, target: Target) -> Path:
    return Path(pkg.name) / f"{target.name}.xcodeproj"
