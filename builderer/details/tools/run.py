import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Optional
from argparse import ArgumentParser

from builderer import Config
from builderer.details.as_iterator import str_iter, as_scalar
from builderer.details.workspace import Workspace
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.tools.build import build_target
from builderer.details.variable_expansion import resolve_conditionals


def get_binary_output_path(
    workspace: Workspace,
    config: Config,
    target: CCBinary,
    build_config: Optional[str],
    build_arch: Optional[str],
) -> Path:
    assert target.output_path
    # Create a config with specific build_config/arch for resolution
    # resolve_conditionals requires scalar values, so default to first if not specified
    resolve_config = deepcopy(config)
    resolve_config.build_config = build_config or list(str_iter(config.build_config))[0]
    resolve_config.architecture = build_arch or list(str_iter(config.architecture))[0]
    # Resolve conditionals (e.g., Switch expressions)
    resolved_path = resolve_conditionals(
        config=resolve_config, value=target.output_path
    )
    return workspace.root / resolved_path


def run_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    extra_args: list[str],
) -> int:
    # Ensure there is a single binary target requested
    if len(top_level_targets) != 1:
        print("ERROR: run command requires exactly one target", file=sys.stderr)
        return 1
    target_name = top_level_targets[0]
    _, target = workspace.find_target(target_name, None)
    # Validate that the target is a binary
    assert isinstance(target, CCBinary)
    # Split args on "--" to separate builderer args from binary args
    if "--" in extra_args:
        separator_idx = extra_args.index("--")
        builderer_args = extra_args[:separator_idx]
        binary_args = extra_args[separator_idx + 1 :]
    else:
        builderer_args = extra_args
        binary_args = []
    # Parse run-specific arguments
    parser = ArgumentParser(prog="builderer run")
    parser.add_argument(
        "--build_config",
        type=str,
        choices=list(str_iter(config.build_config)),
        help="Specific build configuration to build",
    )
    parser.add_argument(
        "--build_arch",
        type=str,
        choices=list(str_iter(config.architecture)),
        help="Specific architecture to build for",
    )
    args = parser.parse_args(builderer_args)
    # Build the target
    if exit_code := build_target(
        workspace=workspace,
        config=config,
        target_name=target_name,
        build_config=args.build_config,
        build_arch=args.build_arch,
    ):
        return exit_code
    # Get the binary output path
    binary_path = get_binary_output_path(
        workspace=workspace,
        config=config,
        target=target,
        build_config=args.build_config,
        build_arch=args.build_arch,
    )
    assert binary_path.exists()
    # Execute the binary
    print(f"\nRunning {binary_path}...")
    run_args = [str(binary_path.resolve())] + binary_args
    result = subprocess.run(run_args)
    return result.returncode
