from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace

def generate_main(workspace: Workspace, config: Config):
    generator_type = workspace.buildtools[config.buildtool]
    generator = generator_type(config, workspace)
    generator()