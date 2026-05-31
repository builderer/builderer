from pathlib import Path
from subprocess import check_call
from typing import Iterator, Tuple

from builderer.details.targets.target import PreBuildTarget, RepositoryTarget


class GenerateFiles(PreBuildTarget):
    def __init__(self, args: list, srcs: list = [], **kwargs):
        super().__init__(**kwargs)
        self.args = args
        self.srcs = srcs

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    def do_pre_build(self):
        assert self.sandbox_root
        sandbox_root = Path(self.sandbox_root)
        if not sandbox_root.is_dir():
            print(f"generating {self.name}")
            sandbox_root.mkdir(parents=True, exist_ok=True)
            check_call(self.args, cwd=self.workspace_root)


# A generate_files step may reference repositories or other generated-file
# (prebuild) targets as inputs.
GenerateFiles.allowed_deps_types = (RepositoryTarget, PreBuildTarget)
