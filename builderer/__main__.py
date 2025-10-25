from argparse import ArgumentParser
import sys

from builderer.details.tools.build import build_main
from builderer.details.tools.generate import generate_main
from builderer.details.tools.graph import graph_main
from builderer.details.tools.sources import sources_main
from builderer.details.tools.licenses import licenses_main
from builderer.details.tools.validate import validate_main
from builderer.details.workspace import Workspace


def main():
    COMMANDS = {
        "build": build_main,
        "generate": generate_main,
        "graph": graph_main,
        "sources": sources_main,
        "validate": validate_main,
        "licenses": licenses_main,
    }
    parser = ArgumentParser()
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("targets", default=[], nargs="*")
    args, unknown_args = parser.parse_known_args()

    workspace = Workspace()
    config = workspace.configs[args.config]
    workspace.configure(config=config, filter_target_names=args.targets)

    # Pass workspace, config, and unknown args to the command
    exit_code = COMMANDS[args.command](workspace, config, unknown_args)
    if exit_code is not None:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
