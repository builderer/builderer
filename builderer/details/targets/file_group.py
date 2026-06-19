import os

from pathlib import Path
from typing import Iterator, List, Tuple

from builderer.details.targets.target import (
    PreBuildTarget,
    RepositoryTarget,
    Target,
)


# A declaration-only target: globbed files whose layout is preserved relative to
# strip_prefix when a consumer (e.g. apple_application) copies them. Emits no
# build-system target of its own; consumers read its (src, dst) pairs. Conditionals,
# globbing, and deps (e.g. a generate_files source) work via the usual machinery.
class FileGroup(Target):
    def __init__(self, *, srcs: list = [], strip_prefix: str = "", **kwargs):
        super().__init__(**kwargs)
        self.srcs = srcs
        # Stripped from each source to form its destination; defaults to the package
        # root (strips nothing). Expanded but not globbed, matched via relpath.
        self.strip_prefix = strip_prefix

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    # (src, dst) per matched source, dst = src relative to strip_prefix (POSIX).
    # srcs/strip_prefix are already expanded+globbed in the same frame, so dst is
    # computed here once, build-system-agnostically. Errors if src escapes strip_prefix.
    def resource_destinations(self) -> List[Tuple[str, str]]:
        strip_root = os.path.normpath(Path(self.workspace_root) / self.strip_prefix)
        results: List[Tuple[str, str]] = []
        for src in self.srcs:
            dst = Path(os.path.relpath(src, strip_root)).as_posix()
            if dst == ".." or dst.startswith("../"):
                raise ValueError(
                    f"file_group '{self.name}': '{src}' is not under "
                    f"strip_prefix '{self.strip_prefix}'"
                )
            results.append((src, dst))
        return results


FileGroup.allowed_deps_types = (RepositoryTarget, PreBuildTarget)
