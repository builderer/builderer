import subprocess
import sys
from argparse import ArgumentParser

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.target_artifact import get_target_artifact_path
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace
from builderer.details.tools.build import build_target


def run_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    command_args: list[str],
    binary_args: list[str],
) -> int:
    # Ensure there is a single binary target requested
    if len(top_level_targets) != 1:
        print("ERROR: run command requires exactly one target", file=sys.stderr)
        return 1
    target_name = top_level_targets[0]
    target_package, target = workspace.find_target(target_name, None)
    assert isinstance(target, BuildTarget)
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
    args = parser.parse_args(command_args)
    # Build the target
    if exit_code := build_target(
        workspace=workspace,
        config=config,
        target_name=target_name,
        build_config=args.build_config,
        build_arch=args.build_arch,
    ):
        return exit_code
    artifact_path = get_target_artifact_path(
        workspace=workspace,
        config=config,
        package=target_package,
        target=target,
        build_config=args.build_config,
        build_arch=args.build_arch,
    )
    assert artifact_path.exists()
    # Execute the built artifact directly, or launch macOS bundles via open.
    if config.platform == "macos" and artifact_path.suffix == ".app":
        print(f"\nRunning {artifact_path}...")
        run_args = ["open", str(artifact_path.resolve()), "--args", *binary_args]
    else:
        print(f"\nRunning {artifact_path}...")
        run_args = [str(artifact_path.resolve())] + binary_args
    result = subprocess.run(run_args)
    return result.returncode
