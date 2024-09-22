from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace


def validate_main(workspace: Workspace, config: Config):
    for pkg_name, pkg in workspace.packages.items():
        assert pkg_name == pkg.name
        for target_name, target in pkg.targets.items():
            assert target_name == target.name
            print(f"{pkg.name}:{target.name}")
            for dep in target.deps:
                dep_package, dep_target = workspace.find_target(dep, pkg)
                print(f"  {dep_package.name}:{dep_target.name}")
