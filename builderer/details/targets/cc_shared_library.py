from typing import Iterator, Tuple

from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import (
    BuildTarget,
    PreBuildTarget,
    RepositoryTarget,
)


# A shared library (.dylib, .so or .dll) linked from its srcs and dependencies.
# Like a cc_library it offers public headers, includes and defines to the
# targets that depend on it.
class CCSharedLibrary(BuildTarget):
    def __init__(
        self,
        *,
        hdrs: list = [],
        srcs: list = [],
        c_flags: list = [],
        cxx_flags: list = [],
        link_flags: list = [],
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
        self.link_flags = link_flags
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


# Links cc_libraries and other shared libraries; may source inputs from
# repositories or generated files.
CCSharedLibrary.allowed_deps_types = (
    CCLibrary,
    CCSharedLibrary,
    RepositoryTarget,
    PreBuildTarget,
)
