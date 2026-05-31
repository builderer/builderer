from typing import Iterator, Tuple

from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import (
    BuildTarget,
    PreBuildTarget,
    RepositoryTarget,
)


class CCBinary(BuildTarget):
    def __init__(
        self,
        *,
        srcs: list = [],
        c_flags: list = [],
        cxx_flags: list = [],
        link_flags: list = [],
        private_defines: list = [],
        private_includes: list = [],
        **kwargs
    ):
        super().__init__(**kwargs)
        self.srcs = srcs
        self.c_flags = c_flags
        self.cxx_flags = cxx_flags
        self.link_flags = link_flags
        self.private_defines = private_defines
        self.private_includes = private_includes

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.private_includes:
            yield "private", self.private_includes


# A cc_binary links cc_libraries and may source inputs from repositories or
# generated-file (prebuild) targets.
CCBinary.allowed_deps_types = (CCLibrary, RepositoryTarget, PreBuildTarget)
