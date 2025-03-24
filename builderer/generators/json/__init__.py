import json
import os
from pathlib import Path

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace
from builderer.details.variable_expansion import bake_config, resolve_conditionals
from builderer.generators.json.utils import categorize_files


# This is an example generator that dumps the workspace in a JSON format for easy inspection.
# It is not consumed by any build tools, but can be used as a reference for building your own generators.
class JsonGenerator:
    def __init__(self, config: Config, workspace: Workspace):
        self.base_config = config
        self.workspace = workspace
        self.output_root = Path(config.build_root)

    def __call__(self):
        # Create output directory
        self.output_root.mkdir(parents=True, exist_ok=True)
        # Generate build configurations
        build_configs = [
            bake_config(self.base_config, architecture=arch, build_config=build_cfg)
            for arch in str_iter(self.base_config.architecture)
            for build_cfg in str_iter(self.base_config.build_config)
        ]
        # Process each target and generate one file per target with all configurations
        for package, target in self.workspace.targets:
            if not isinstance(target, BuildTarget):
                continue  # Skip non-build targets
            self._generate_target_file(package, target, build_configs)
        # Generate workspace info after target files to get correct paths
        self._generate_workspace_json()

    def _generate_workspace_json(self):
        # Create a summary of the workspace
        summary = {
            "platform": self.base_config.platform,
            "toolchain": self.base_config.toolchain,
            "packages": list(self.workspace.packages.keys()),
            "targets": [],
        }
        # Add target information including path to the target's JSON file
        for package, target in self.workspace.targets:
            if not isinstance(target, BuildTarget):
                continue  # Skip non-build targets
            # Determine the path to the target's JSON file
            target_path = self._get_target_json_path(package, target)
            summary["targets"].append(
                {
                    "name": f"{package.name}:{target.name}",
                    "type": target.__class__.__name__,
                    "path": os.path.relpath(target_path, self.output_root),
                }
            )
        # Write summary to JSON file
        workspace_path = self.output_root.joinpath("workspace.json")
        with open(workspace_path, "w") as f:
            json.dump(summary, f, indent=2)

    def _get_target_json_path(self, package, target):
        package_dir = self.output_root
        if package.name != "":  # Handle root package
            package_dir = self.output_root.joinpath(package.name)
        return package_dir.joinpath(f"{target.name}.json")

    def _generate_target_file(self, package, target, build_configs):
        # Create package directory structure
        package_dir = self.output_root
        if package.name != "":  # Handle root package
            package_path = Path(package.name)
            package_dir = self.output_root.joinpath(package_path)
            package_dir.mkdir(parents=True, exist_ok=True)
        # Create target data with common attributes
        target_data = {
            "name": target.name,
            "type": target.__class__.__name__,
            "root": os.path.relpath(target.root, package_dir),
            "workspace_root": os.path.relpath(target.workspace_root, package_dir),
            "sandbox": target.sandbox,
            "configurations": {},
        }
        # Add sandbox_root only if the target is sandboxed
        if target.sandbox:
            assert (
                target.sandbox_root is not None
            ), f"Sandbox enabled for {package.name}:{target.name} but sandbox_root is None"
            target_data["sandbox_root"] = os.path.relpath(
                target.sandbox_root, package_dir
            )
        # Process dependencies (these don't change with config)
        all_deps = list(self.workspace.all_dependencies(package, target))
        target_data["dependencies"] = [
            f"{dep_pkg.name}:{dep_target.name}" for dep_pkg, dep_target in all_deps
        ]
        # Add configuration-specific data
        for config in build_configs:
            config_key = f"{config.architecture}_{config.build_config}"
            target_data["configurations"][config_key] = self._process_config_data(
                config, package, target, all_deps, package_dir
            )
        # Write target data to JSON file in the package directory
        target_path = package_dir.joinpath(f"{target.name}.json")
        with open(target_path, "w") as f:
            json.dump(target_data, f, indent=2)

    def _process_config_data(self, config, package, target, all_deps, package_dir):
        # Process source files
        source_files = resolve_conditionals(config=config, value=target.srcs)
        # Make source files relative to the package directory
        relative_source_files = [
            os.path.relpath(src, package_dir) for src in source_files
        ]
        file_categories = categorize_files(relative_source_files)
        # Process include paths
        includes = []
        if hasattr(target, "private_includes"):
            includes.extend(
                resolve_conditionals(config=config, value=target.private_includes)
            )
        if hasattr(target, "public_includes"):
            includes.extend(
                resolve_conditionals(config=config, value=target.public_includes)
            )
        # Add dependency includes
        for dep_pkg, dep_target in all_deps:
            if hasattr(dep_target, "public_includes"):
                includes.extend(
                    resolve_conditionals(
                        config=config, value=dep_target.public_includes
                    )
                )
        # Process compiler flags
        compiler_flags = {}
        if hasattr(target, "c_flags"):
            compiler_flags["c_flags"] = resolve_conditionals(
                config=config, value=target.c_flags
            )
        if hasattr(target, "cxx_flags"):
            compiler_flags["cxx_flags"] = resolve_conditionals(
                config=config, value=target.cxx_flags
            )
        # Process linker flags
        linker_flags = {}
        if hasattr(target, "link_flags"):
            linker_flags["link_flags"] = resolve_conditionals(
                config=config, value=target.link_flags
            )
        # Process defines
        defines = []
        if hasattr(target, "private_defines"):
            defines.extend(
                resolve_conditionals(config=config, value=target.private_defines)
            )
        if hasattr(target, "public_defines"):
            defines.extend(
                resolve_conditionals(config=config, value=target.public_defines)
            )
        # Add dependency defines
        for dep_pkg, dep_target in all_deps:
            if hasattr(dep_target, "public_defines"):
                defines.extend(
                    resolve_conditionals(config=config, value=dep_target.public_defines)
                )
        # Return config-specific data
        return {
            "header_files": file_categories["header_files"],
            "source_files": file_categories["source_files"],
            "include_paths": [os.path.relpath(inc, package_dir) for inc in includes],
            "defines": defines,
            "compiler_flags": compiler_flags,
            "linker_flags": linker_flags,
            "platform": config.platform,
            "architecture": config.architecture,
            "build_config": config.build_config,
        }
