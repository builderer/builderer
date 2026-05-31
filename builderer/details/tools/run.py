import json
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from typing import Optional

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.target_artifact import get_target_artifact_path
from builderer.details.targets.target import BuildTarget
from builderer.details.targets.apple_application import AppleApplication
from builderer.details.workspace import Workspace
from builderer.details.tools.build import build_target
from builderer.details.variable_expansion import bake_config, resolve_conditionals


# CFBundleIdentifier of an AppleApplication, resolved for the build variant.
# info_plist may carry conditionals (per-key or a whole-dict Switch), so it is
# resolved against a baked config before the bundle id is read. devicectl
# launches by bundle id, so a missing CFBundleIdentifier is a fatal
# misconfiguration (the app can never launch on iOS), not a recoverable case.
def _ios_bundle_identifier(
    config: Config, target: AppleApplication, build_config: Optional[str]
) -> str:
    arch = next(iter(str_iter(config.architecture)))
    cfg = bake_config(
        config,
        architecture=arch,
        build_config=build_config or next(iter(str_iter(config.build_config))),
    )
    resolved = resolve_conditionals(cfg, target.info_plist)
    return resolved["CFBundleIdentifier"]


# Map of {name: udid} for paired iOS devices. devicectl deploys over both USB
# and Wi-Fi, so all paired devices are offered as --device choices (run is
# iOS-device-only); if the chosen device is not reachable at install time,
# devicectl reports that itself. The devicectl JSON schema is fixed, so fields
# are indexed directly — malformed output raises rather than being dropped.
def _ios_devices() -> dict:
    result = subprocess.run(
        ["xcrun", "devicectl", "list", "devices", "--json-output", "-"],
        capture_output=True,
        text=True,
    )
    # A devicectl failure is a tooling error, not "zero devices" — the
    # legitimate empty case is a successful run whose device list is empty.
    assert (
        result.returncode == 0
    ), f"`xcrun devicectl list devices` failed: {result.stderr.strip()}"
    devices = json.loads(result.stdout)["result"]["devices"]
    return {
        d["deviceProperties"]["name"]: d["hardwareProperties"]["udid"] for d in devices
    }


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
    # iOS run installs onto a paired device (the simulator is via Xcode);
    # require an explicit choice among the paired devices, never a default.
    ios_devices = _ios_devices() if config.platform == "ios" else {}
    if config.platform == "ios":
        parser.add_argument(
            "--device",
            type=str,
            required=True,
            choices=sorted(ios_devices),
            help="Paired iOS device to install and launch on",
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
    if config.platform == "emscripten":
        node = shutil.which("node")
        if node is None:
            print(
                "ERROR: `node` not found in PATH. Install Node.js, or activate "
                "emsdk (`source emsdk_env.sh` / `emsdk_env.bat`) so its bundled "
                "Node is on PATH.",
                file=sys.stderr,
            )
            return 1
        if artifact_path.suffix == ".html":
            js_path = artifact_path.with_suffix(".js")
        elif artifact_path.suffix == ".js":
            js_path = artifact_path
        else:
            print(
                f"ERROR: emscripten artifact {artifact_path} must have a .html "
                "or .js suffix to run under node.",
                file=sys.stderr,
            )
            return 1
        if not js_path.exists():
            print(
                f"ERROR: expected JavaScript entrypoint {js_path} was not "
                "produced by the build.",
                file=sys.stderr,
            )
            return 1
        print(f"\nRunning {js_path} under node...")
        run_args = [node, str(js_path.resolve()), *binary_args]
    elif config.platform == "macos" and artifact_path.suffix == ".app":
        print(f"\nRunning {artifact_path}...")
        run_args = ["open", str(artifact_path.resolve()), "--args", *binary_args]
    elif config.platform == "ios":
        # iOS install+launch on the connected device via devicectl (two commands,
        # not a single exec); for the simulator, open the project in Xcode. iOS
        # only ever runs .app bundles — unlike macOS, you cannot exec a bare
        # binary on a device — so anything else is a generation bug, not a path.
        assert artifact_path.suffix == ".app"
        assert isinstance(target, AppleApplication)
        app = artifact_path.resolve()
        bundle_id = _ios_bundle_identifier(config, target, args.build_config)
        # A device install requires a signed bundle; surface a clear message.
        if (
            subprocess.run(
                ["codesign", "--verify", "--verbose", str(app)],
                capture_output=True,
            ).returncode
            != 0
        ):
            print(
                f"ERROR: {app.name} is not code-signed; on-device install requires "
                "signing. Set `development_team` on the apple_application, sign into "
                "that team in Xcode, and register the device.",
                file=sys.stderr,
            )
            return 1
        # argparse `choices` already constrained --device to a paired device, so
        # this lookup resolves; reachability is the user's pick (devicectl
        # reports it below if the chosen device is not available).
        udid = ios_devices[args.device]
        if exit_code := subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "install",
                "app",
                "--device",
                udid,
                str(app),
            ]
        ).returncode:
            return exit_code
        print(f"\nLaunching {bundle_id} on device...")
        return subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "process",
                "launch",
                "--console",
                "--device",
                udid,
                bundle_id,
                *binary_args,
            ]
        ).returncode
    else:
        print(f"\nRunning {artifact_path}...")
        run_args = [str(artifact_path.resolve())] + binary_args
    result = subprocess.run(run_args)
    return result.returncode
