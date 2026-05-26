import fnmatch
from pathlib import Path
from typing import Sequence


def split_patterns(patterns: Sequence[str]) -> tuple[list[str], list[str]]:
    includes = [p for p in patterns if not p.startswith("!")]
    excludes = [p[1:] for p in patterns if p.startswith("!")]
    return includes, excludes


def glob_with_exclusions(root: Path, patterns: Sequence[str], predicate) -> list[str]:
    includes, excludes = split_patterns(patterns)
    if not includes:
        return []
    # Collect all paths matching include patterns. Dedupe + sort so the result
    # is filesystem-traversal-order independent (callers feed this into hashes).
    matched = sorted(
        {
            (src.as_posix(), src.relative_to(root).as_posix())
            for pattern in includes
            for src in root.glob(pattern)
            if predicate(src)
        }
    )
    if not excludes:
        return [src for src, _ in matched]
    return [
        src
        for src, rel_path in matched
        if not any(fnmatch.fnmatch(rel_path, exclude) for exclude in excludes)
    ]
