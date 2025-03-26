"""
Xcode Generator for Builderer.

This module provides functionality to generate Xcode project files from builderer targets.
It generates a single .xcodeproj file that includes all targets and their dependencies.

PROGRESS & NOTES:
- TASK: Simplify the Xcode generator to produce a single .pbxproj file instead of one per target
  This will improve usability since Xcode has poor support for multi-project dependencies.

- TASK: Add validation to ensure the build_root ends with .xcodeproj
  This makes it explicit to the user that the output is an Xcode project directory.

- IMPLEMENTATION PLAN:
  1. Validate build_root ends with .xcodeproj during initialization
  2. Collect all targets into a single project model
  3. Generate a single project file that includes all targets
  4. Make each target aware of its dependencies within the single project

- FUTURE IMPROVEMENTS:
  1. Add support for multiple build configurations (debug/release)
  2. Improve organization of files in the project navigator
  3. Add support for more target types (e.g., frameworks, unit tests)
"""

from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace
from builderer.generators.xcode.formatter import format_xcode_project
from builderer.generators.xcode.model_builder import generate_xcode_project
from builderer.generators.xcode.validator import validate_references, validate_paths


def _generate(config: Config, workspace: Workspace) -> None:
    """Generate an Xcode project from the workspace.

    Args:
        config: The configuration to use for generation.
        workspace: The workspace containing all targets.
    """
    # Generate project model
    project = generate_xcode_project(config, workspace)

    # Get output path
    output_root = Path(config.build_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # Validate references and paths
    if errors := validate_references(project):
        raise ValueError(f"Invalid project: {errors}")

    if errors := validate_paths(project, str(output_root.parent)):
        raise ValueError(f"Invalid project paths: {errors}")

    # Format and write to disk
    project_str = format_xcode_project(project)
    project_file = output_root / "project.pbxproj"
    with open(project_file, "w") as f:
        f.write(project_str)

    print(f"Generated Xcode project at {output_root}")


class XcodeGenerator:
    """Generator for Xcode projects.

    This is a thin wrapper around the pure functional implementation to maintain
    compatibility with the buildtool system.
    """

    def __init__(self, config: Config, workspace: Workspace):
        self.config = config
        self.workspace = workspace

    def __call__(self) -> None:
        """Generate the Xcode project."""
        _generate(self.config, self.workspace)
