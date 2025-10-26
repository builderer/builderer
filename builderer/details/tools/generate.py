from argparse import ArgumentParser

from builderer import Config
from builderer.details.workspace import Workspace


def generate_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    extra_args: list[str],
):
    parser = ArgumentParser(prog="builderer generate")
    parser.parse_args(extra_args)
    generator_type = workspace.buildtools[config.buildtool]
    generator = generator_type(config, workspace)
    generator()
