from argparse import ArgumentParser
import sys

from builderer.details.tools.build import build_main
from builderer.details.tools.generate import generate_main
from builderer.details.tools.graph import graph_main
from builderer.details.tools.run import run_main
from builderer.details.tools.sources import sources_main
from builderer.details.tools.licenses import licenses_main
from builderer.details.tools.validate import validate_main
from builderer.details.workspace import Workspace


def main():
    COMMANDS = {
        "build": build_main,
        "generate": generate_main,
        "graph": graph_main,
        "run": run_main,
        "sources": sources_main,
        "validate": validate_main,
        "licenses": licenses_main,
    }
    # Filter out run args separator...
    if "--" in sys.argv:
        separator_idx = sys.argv.index("--")
        builderer_args = sys.argv[1:separator_idx]
        binary_args = sys.argv[separator_idx + 1 :]
    else:
        builderer_args = sys.argv[1:]
        binary_args = []
    # parse common arguments...
    parser = ArgumentParser()
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("targets", default=[], nargs="*")
    args, unknown_args = parser.parse_known_args(builderer_args)
    # build workspace for target(s)...
    workspace = Workspace()
    config = workspace.configs[args.config]
    workspace.configure(config=config, filter_target_names=args.targets)
    # Pass workspace, config, and unknown args to the command
    exit_code = COMMANDS[args.command](
        workspace=workspace,
        config=config,
        top_level_targets=args.targets,
        command_args=unknown_args,
        binary_args=binary_args,
    )
    if exit_code is not None:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
