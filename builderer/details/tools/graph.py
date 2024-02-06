import sys

from pathlib import Path
from typing import List, Dict, TextIO 

from builderer import Config
from builderer.details.targets.target import PreBuildTarget
from builderer.details.workspace import Workspace, target_full_name

def write_clustered_graph(workspace: Workspace, file: TextIO):
    print("digraph DependencyGraph {", file=file)
    for pkg_i, pkg in enumerate(workspace.packages.values()):
        print(f'  subgraph cluster{pkg_i} {{', file=file)
        print(f'    label = "{pkg.name}";', file=file)
        for tgt in pkg.targets.values():
            shape = "box" if isinstance(tgt, PreBuildTarget) else "oval"
            print(f'    "{target_full_name(pkg,tgt)}" [label="{tgt.name}", shape={shape}];', file=file)
        print("  }", file=file)
    for pkg_i, pkg in enumerate(workspace.packages.values()):
        for tgt in pkg.targets.values():
            deps = ', '.join(f'"{target_full_name(*workspace.find_target(d, pkg))}"' for d in tgt.deps)
            print(f'  "{target_full_name(pkg,tgt)}" -> {{{deps}}};', file=file)
    print("}", file=file)


def graph_main(workspace: Workspace, config: Config):
    write_clustered_graph(workspace, sys.stdout)