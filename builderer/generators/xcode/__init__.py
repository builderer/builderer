from pathlib import Path

from builderer import Config
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace
from builderer.generators.xcode.formatter import format_xcode_project
from builderer.generators.xcode.model_builder import create_xcode_project
from builderer.generators.xcode.utils import xcode_project_path
from builderer.generators.xcode.validator import validate_references


class XcodeGenerator:
    """Generator for Xcode projects."""

    def __init__(self, config: Config, workspace: Workspace):
        self.config = config
        self.workspace = workspace

    def __call__(self) -> None:
        """Generate the Xcode project files."""
        for package, target in self.workspace.targets:
            if isinstance(target, BuildTarget):
                # Create the Xcode project model using the new model_builder
                xcode_project = create_xcode_project(
                    config=self.config,
                    workspace=self.workspace,
                    package=package,
                    target=target,
                )

                # Validate the Xcode project model
                errors = validate_references(xcode_project)
                if errors:
                    raise ValueError(f"Validation errors in Xcode project: {errors}")

                # Format the project model to a string using the new formatter
                project_str = format_xcode_project(xcode_project)

                # Write the project file
                project_dir = Path(self.config.build_root) / xcode_project_path(
                    package, target
                )
                project_dir.mkdir(parents=True, exist_ok=True)

                project_file = project_dir / "project.pbxproj"
                with open(project_file, "w") as f:
                    f.write(project_str)
