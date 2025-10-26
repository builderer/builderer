import fnmatch
from pathlib import Path
from typing import Sequence


def split_patterns(patterns: Sequence[str]) -> tuple[list[str], list[str]]:
    includes = [p for p in patterns if not p.startswith("!")]
    excludes = [p[1:] for p in patterns if p.startswith("!")]
    return includes, excludes


def glob_with_exclusions(root: Path, patterns: Sequence[str]) -> list[str]:
    includes, excludes = split_patterns(patterns)
    if not includes:
        return []
    # Collect all files matching include patterns
    matched = [
        (src, src.relative_to(root).as_posix())
        for pattern in includes
        for src in root.glob(pattern)
    ]
    if not excludes:
        return [src.as_posix() for src, _ in matched]
    # Filter out files matching any exclude pattern (using relative paths for matching)
    return [
        src.as_posix()
        for src, rel_path in matched
        if not any(fnmatch.fnmatch(rel_path, exclude) for exclude in excludes)
    ]
