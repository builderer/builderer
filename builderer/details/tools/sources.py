from pathlib import Path

from builderer import Config
from builderer.details.workspace import Workspace


def _count_lines(file_path: Path) -> int:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def sources_main(
    workspace: Workspace,
    config: Config,
    top_level_targets: list[str],
    command_args: list[str],
    binary_args: list[str],
):
    assert not command_args
    assert not binary_args

    # Count all files once
    file_locs = {
        Path(f).resolve(): _count_lines(Path(f).resolve())
        for pkg in workspace.packages.values()
        for t in pkg.targets.values()
        for _, a in t.get_file_path_fields()
        for f in a
    }

    # Print source tree
    for pkg in workspace.packages.values():
        pkg_loc = sum(
            file_locs[Path(f).resolve()]
            for t in pkg.targets.values()
            for _, a in t.get_file_path_fields()
            for f in a
        )
        print(f"{pkg.name} : {pkg_loc:,} lines")
        for target in pkg.targets.values():
            target_loc = sum(
                file_locs[Path(f).resolve()]
                for _, a in target.get_file_path_fields()
                for f in a
            )
            print(f"  {target.name} : {target_loc:,} lines")
            for attr_name, attr in target.get_file_path_fields():
                attr_loc = sum(file_locs[Path(f).resolve()] for f in attr)
                print(f"    {attr_name} : {attr_loc:,} lines")
                for file in attr:
                    file_path = Path(file).resolve()
                    print(
                        f"      {file_path.relative_to(workspace.root)} : {file_locs[file_path]:,} lines"
                    )

    # Print total
    total_loc = sum(file_locs.values())
    print(f"\nTotal : {total_loc:,} lines")
