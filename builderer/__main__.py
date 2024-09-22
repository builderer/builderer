from argparse import ArgumentParser

from builderer.details.tools.generate import generate_main
from builderer.details.tools.graph import graph_main
from builderer.details.tools.sources import sources_main
from builderer.details.tools.validate import validate_main
from builderer.details.workspace import Workspace


def main():
    COMMANDS = {
        "generate": generate_main,
        "graph": graph_main,
        "sources": sources_main,
        "validate": validate_main,
    }
    parser = ArgumentParser()
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("targets", default=[], nargs="*")
    args = parser.parse_args()
    workspace = Workspace()
    config = workspace.configs[args.config]
    workspace.configure(config=config, filter_target_names=args.targets)
    COMMANDS[args.command](workspace, config)


if __name__ == "__main__":
    main()
