from builderer import Config
from builderer.details.workspace import Workspace


def generate_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    command_args: list[str],
    binary_args: list[str],
):
    assert not command_args
    assert not binary_args
    generator_type = workspace.buildtools[config.buildtool]
    generator = generator_type(config, workspace)
    generator()
