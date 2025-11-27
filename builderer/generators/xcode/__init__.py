from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace
from builderer.details.variable_expansion import bake_config
from builderer.details.as_iterator import str_iter
from builderer.generators.xcode.formatter import format_xcode_project
from builderer.generators.xcode.model_builder import generate_xcode_project, ProjectInfo
from builderer.generators.xcode.validator import (
    validate_references,
    validate_paths,
    validate_output_paths,
)

# Platform validation constants
SUPPORTED_TOOLCHAINS = ["clang"]
SUPPORTED_PLATFORMS = ["macos"]
SUPPORTED_ARCHITECTURES = ["arm64", "x86_64"]


def _generate(config: Config, workspace: Workspace) -> None:

    # Validate build_root ends with .xcodeproj
    if not config.build_root.endswith(".xcodeproj"):
        raise ValueError(
            f"Xcode generator requires build_root to end with '.xcodeproj'. "
            f"Got '{config.build_root}' instead. Please specify a path ending with '.xcodeproj'."
        )

    # Generate project model
    project = generate_xcode_project(config, workspace)

    # Get output path
    output_root = Path(config.build_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # Validate references, paths, and output paths
    if errors := validate_references(project):
        raise ValueError(f"Invalid project: {errors}")

    if errors := validate_paths(project, str(workspace.root)):
        raise ValueError(f"Invalid project paths: {errors}")

    validate_output_paths(project)

    # Format and write to disk
    project_str = format_xcode_project(project)
    project_file = output_root / "project.pbxproj"
    with open(project_file, "w") as f:
        f.write(project_str)


class XcodeGenerator:
    def __init__(self, config: Config, workspace: Workspace):
        self.config = config
        self.workspace = workspace

        # Validate platform, toolchain, and architecture
        if self.config.toolchain not in SUPPORTED_TOOLCHAINS:
            raise ValueError(f"unsupported toolchain {self.config.toolchain}")
        if self.config.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform {self.config.platform}")
        for arch in str_iter(self.config.architecture):
            if arch not in SUPPORTED_ARCHITECTURES:
                raise ValueError(f"unsupported architecture {arch}")

    def __call__(self) -> None:
        """Generate the Xcode project."""
        _generate(self.config, self.workspace)
