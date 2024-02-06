from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace

def sources_main(workspace: Workspace, config: Config):
    # Print source tree
    for pkg in workspace.packages.values():
        print(pkg.name)
        for target in pkg.targets.values():
            print(f"  {target.name}")
            for attr_name,attr in target.get_file_path_fields():
                print(f"    {attr_name}")
                for file in attr:
                  print(f"      {Path(file).resolve().relative_to(workspace.root)}")
