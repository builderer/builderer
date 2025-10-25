from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, List

from builderer import Config
from builderer.details.targets.target import RepositoryTarget
from builderer.details.workspace import Workspace, target_full_name


LICENSE_PRIORITY: tuple[str, ...] = (
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "LICENSE.rst",
    "COPYING",
    "COPYING.txt",
    "COPYING.md",
    "COPYING.rst",
)


LICENSE_PRIORITY_MAP: Dict[str, int] = {
    name.lower(): index for index, name in enumerate(LICENSE_PRIORITY)
}


def _license_sort_key(path: Path) -> tuple[int, str]:
    name_lower = path.name.lower()
    rank = LICENSE_PRIORITY_MAP.get(name_lower, len(LICENSE_PRIORITY))
    return rank, name_lower


def _collect_license_files(root: Path) -> List[Path]:
    resolved_root = root.resolve()
    seen: Dict[Path, Path] = {}
    for child in resolved_root.iterdir():
        try:
            candidate = child.resolve()
        except OSError:
            continue
        if not candidate.is_file():
            continue
        name_lower = candidate.name.lower()
        if name_lower.startswith("license") or name_lower.startswith("copying"):
            seen.setdefault(candidate, candidate)
    candidates = list(seen.values())
    candidates.sort(key=_license_sort_key)
    return candidates


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def licenses_main(workspace: Workspace, config: Config, extra_args: list[str]) -> None:
    parser = ArgumentParser(prog="builderer licenses")
    parser.parse_args(extra_args)
    repository_targets = [
        (pkg, target)
        for pkg in workspace.packages.values()
        for target in pkg.targets.values()
        if isinstance(target, RepositoryTarget)
    ]
    if not repository_targets:
        print("No repository targets found.")
        return

    for package, target in repository_targets:
        target_label = target_full_name(package, target)
        target_root = Path(target.root).resolve()
        if not target_root.exists():
            print(f"{target_label}: repository path {target_root} does not exist")
            continue

        license_paths = _collect_license_files(target_root)
        if not license_paths:
            print("#" * 80)
            print(f"## {target_label} (no license file found)")
            print("#" * 80)
            print(
                "Unable to locate a license file. Looked for filenames starting with 'LICENSE' or 'COPYING'."
            )
            print(f"Repository root: {target_root}")
            print()
            continue

        for license_path in license_paths:
            try:
                relative_path = license_path.relative_to(target_root)
            except ValueError:
                relative_path = license_path

            print("#" * 80)
            print(f"## {target_label} ({relative_path})")
            print("#" * 80)
            license_text = _read_text_file(license_path)
            if not license_text.strip():
                print("<empty license file>")
            else:
                print(license_text.rstrip())
            print()
