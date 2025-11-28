import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from argparse import ArgumentParser

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.workspace import Workspace
from builderer.generators.make import MakeGenerator
from builderer.generators.msbuild import MsBuildGenerator
from builderer.generators.msbuild.version import VS_VERSIONS
from builderer.generators.xcode import XcodeGenerator


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
    generator: MsBuildGenerator,
) -> int:
    # Determine VS version from generator
    vs_major, _ = generator._version.visual_studio_version
    # Locate MSBuild
    vswhere_path = (
        Path(os.environ["ProgramFiles(x86)"])
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    vswhere_args = [
        str(vswhere_path),
        "-version",
        f"[{vs_major}.0,{vs_major + 1}.0)",
        "-prerelease",  # for 2026 Insider release support
        "-latest",
        "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "-requires",
        "Microsoft.Component.MSBuild",
        "-find",
        "**\\MSBuild.exe",
    ]
    result = subprocess.run(
        vswhere_args,
        capture_output=True,
        text=True,
        check=True,
    )
    # vswhere returns multiple paths (one per line), take the first one
    msbuild_paths = result.stdout.strip().splitlines()
    if not msbuild_paths:
        print(
            f"ERROR: Could not find MSBuild for Visual Studio {vs_major}.0. "
            f"Please ensure Visual Studio {vs_major}.0 is installed with the required components.",
            file=sys.stderr,
        )
        return 1
    msbuild = msbuild_paths[0]
    build_root = Path(config.build_root)
    # Always build the solution file - it has all the dependencies
    solution_path = build_root / "Solution.sln"
    if not solution_path.exists():
        print(f"ERROR: Solution file not found: {solution_path}")
        return 1
    # Build msbuild command - always build the full solution
    # MSBuild will use incremental builds so this is fast
    msbuild_args = [
        msbuild,
        str(solution_path),
        "/verbosity:minimal",
        "/maxcpucount",
    ]
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


def build_with_xcode(
    workspace: Workspace,
    config: Config,
    target_name: Optional[str],
    build_config: Optional[str],
    build_arch: Optional[str],
) -> int:
    build_root = Path(config.build_root)
    # Validate build_root is an .xcodeproj
    if not str(build_root).endswith(".xcodeproj"):
        print(
            f"ERROR: Xcode build_root must end with .xcodeproj, got: {build_root}",
            file=sys.stderr,
        )
        return 1
    # Build xcodebuild command
    xcode_args = [
        "xcodebuild",
        "-project",
        str(build_root),
        "-parallelizeTargets",
    ]
    # Add target if specified (use full name: package:target)
    if target_name:
        xcode_args.extend(["-target", target_name])
    else:
        xcode_args.append("-alltargets")
    # Add configuration if specified
    if build_config:
        xcode_args.extend(["-configuration", build_config])
    # Add architecture if specified
    if build_arch:
        xcode_args.extend(["-arch", build_arch])
    # Run xcodebuild
    result = subprocess.run(xcode_args)
    if result.returncode != 0:
        print(f"Build failed")
        return result.returncode
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
    elif isinstance(generator, MsBuildGenerator):
        return build_with_msbuild(
            workspace=workspace,
            config=config,
            target_name=target_name,
            build_config=build_config,
            build_arch=build_arch,
            generator=generator,
        )
    elif generator_type is XcodeGenerator:
        return build_with_xcode(
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
    command_args: list[str],
    binary_args: list[str],
) -> int:
    assert not binary_args
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
    args = parser.parse_args(command_args)
    return build_target(
        workspace=workspace,
        config=config,
        target_name=args.target,
        build_config=args.build_config,
        build_arch=args.build_arch,
    )
