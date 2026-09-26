import fnmatch
from pathlib import Path
from typing import Sequence


def split_patterns(patterns: Sequence[str]) -> tuple[list[str], list[str]]:
    includes = [p for p in patterns if not p.startswith("!")]
    excludes = [p[1:] for p in patterns if p.startswith("!")]
    return includes, excludes


def glob_with_exclusions(root: Path, patterns: Sequence[str], predicate) -> list[str]:
    includes, excludes = split_patterns(patterns)
    # Results follow the declared pattern order (e.g. patches apply in sequence,
    # include dirs keep their search order). Matches within a single pattern
    # are sorted and duplicates keep their first position, so the result is
    # filesystem-traversal-order independent (callers feed this into hashes).
    matched: dict[str, str] = {}
    for pattern in includes:
        for src in sorted(root.glob(pattern), key=Path.as_posix):
            if predicate(src):
                matched.setdefault(src.as_posix(), src.relative_to(root).as_posix())
    return [
        src
        for src, rel_path in matched.items()
        if not any(fnmatch.fnmatch(rel_path, exclude) for exclude in excludes)
    ]
