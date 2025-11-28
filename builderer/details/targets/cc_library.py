import os
import shutil

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, Tuple, Optional

from builderer.details.targets.target import BuildTarget


class CCLibrary(BuildTarget):
    def __init__(
        self,
        *,
        hdrs: list = [],
        srcs: list = [],
        c_flags: list = [],
        cxx_flags: list = [],
        public_defines: list = [],
        private_defines: list = [],
        public_includes: list = [],
        private_includes: list = [],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.hdrs = hdrs
        self.srcs = srcs
        self.c_flags = c_flags
        self.cxx_flags = cxx_flags
        self.public_defines = public_defines
        self.private_defines = private_defines
        self.public_includes = public_includes
        self.private_includes = private_includes

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.hdrs:
            yield "public", self.hdrs
        if self.srcs:
            yield "source", self.srcs

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.public_includes:
            yield "public", self.public_includes
        if self.private_includes:
            yield "private", self.private_includes

    def do_pre_build(self):
        assert self.sandbox_root

        def get_relative_paths(files, root):
            return [os.path.relpath(f, root) for f in files]

        # Compute common paths for each path group...
        group_paths = defaultdict(list)
        for group, paths in self.get_file_path_fields():
            group_paths[group].extend([Path(p).parent for p in paths])
        for group, paths in self.get_dir_path_fields():
            group_paths[group].extend([Path(p) for p in paths])
        group_roots = {
            group: Path(os.path.commonpath(paths)).resolve()
            for group, paths in group_paths.items()
        }
        # Install sandbox if it doesn't already exist...
        # TODO: we should also check to see if any dependencies have changed (e.g. if repo changed we need to update sandbox)
        sandbox_root = Path(self.sandbox_root)
        if not sandbox_root.is_dir():
            print(f"Sandboxing {self.name}")
            sandbox_root.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=str(sandbox_root.parent)) as tmp:
                sandbox_temp = Path(tmp)
                for group, files in self.get_file_path_fields():
                    group_root = group_roots[group]
                    files = get_relative_paths(files, group_root)
                    for file in files:
                        src = group_root.joinpath(file)
                        dst = sandbox_temp.joinpath(group, file)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(str(src), str(dst))
                sandbox_temp.rename(sandbox_root)
        # Change file paths to sandbox...
        for group, paths in self.get_all_path_fields():
            paths[:] = [
                sandbox_root.joinpath(group, path).as_posix()
                for path in get_relative_paths(paths, group_roots[group])
            ]
