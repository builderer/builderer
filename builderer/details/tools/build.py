import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from argparse import ArgumentParser

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.workspace import Workspace, target_full_name
from builderer.generators.make import MakeGenerator
from builderer.generators.msbuild import MsBuildGenerator


def build_with_make(
    workspace: Workspace,
    config: Config,
    target_name: Optional[str],
    build_config: Optional[str],
    build_arch: Optional[str],
) -> int:
    build_root = Path(config.build_root)
    # Build make command
    make_args = [
        "make",
        "-C",
        str(build_root),
        f"-j{os.cpu_count() or 1}",
    ]
    # Only specify ARCH/CONFIG if explicitly requested
    if build_arch:
        make_args.append(f"ARCH={build_arch}")
    if build_config:
        make_args.append(f"CONFIG={build_config}")
    # Build makefile target name
    if target_name:
        pkg_name, tgt_name = target_name.split(":")
        make_args.append(f"{pkg_name}@{tgt_name}")
    else:
        make_args.append("build")
    # Run make
    result = subprocess.run(make_args)
    if result.returncode != 0:
        print(f"Build failed")
        return result.returncode
    return 0


def build_with_msbuild(
    workspace: Workspace,
    config: Config,
    target_name: Optional[str],
    build_config: Optional[str],
    build_arch: Optional[str],
) -> int:
    # Locate MSBuild
    vswhere_path = (
        Path(os.environ["ProgramFiles(x86)"])
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    result = subprocess.run(
        [
            str(vswhere_path),
            "-latest",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-requires",
            "Microsoft.Component.MSBuild",
            "-find",
            "**\\MSBuild.exe",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # vswhere returns multiple paths (one per line), take the first one
    msbuild = result.stdout.strip().splitlines()[0]
    build_root = Path(config.build_root)
    # Always build the solution file - it has all the dependencies
    solution_path = build_root / "Solution.sln"
    if not solution_path.exists():
        print(f"ERROR: Solution file not found: {solution_path}")
        return 1
    # Build msbuild command - always build the full solution
    # MSBuild will use incremental builds so this is fast
    msbuild_args = [msbuild, str(solution_path), "/m"]  # Multi-core build
    # Only specify Configuration/Platform if explicitly requested
    if build_config:
        msbuild_args.append(f"/p:Configuration={build_config}")
    if build_arch:
        msbuild_args.append(f"/p:Platform={build_arch}")
    build_result = subprocess.run(msbuild_args)
    if build_result.returncode != 0:
        print(f"Build failed")
        return build_result.returncode
    return 0


def build_target(
    workspace: Workspace,
    config: Config,
    target_name: Optional[str] = None,
    build_config: Optional[str] = None,
    build_arch: Optional[str] = None,
) -> int:
    # First, generate build files
    generator_type = workspace.buildtools[config.buildtool]
    generator = generator_type(config, workspace)
    generator()
    # Build based on the generator type
    if generator_type is MakeGenerator:
        return build_with_make(
            workspace=workspace,
            config=config,
            target_name=target_name,
            build_config=build_config,
            build_arch=build_arch,
        )
    elif generator_type is MsBuildGenerator:
        return build_with_msbuild(
            workspace=workspace,
            config=config,
            target_name=target_name,
            build_config=build_config,
            build_arch=build_arch,
        )
    else:
        print(
            f"ERROR: Unsupported build tool: {generator_type.__name__}",
            file=sys.stderr,
        )
        return 1


def build_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    extra_args: list[str],
) -> int:
    parser = ArgumentParser(prog="builderer build")
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
    parser.add_argument(
        "target",
        nargs="?",
        help="Optional specific target to build",
    )
    args = parser.parse_args(extra_args)
    return build_target(
        workspace=workspace,
        config=config,
        target_name=args.target,
        build_config=args.build_config,
        build_arch=args.build_arch,
    )
