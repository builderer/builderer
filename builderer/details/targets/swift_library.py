from typing import Iterator, Optional, Tuple

from builderer.details.targets.swift_cc_module import SwiftCcModule
from builderer.details.targets.target import (
    BuildTarget,
    PreBuildTarget,
    RepositoryTarget,
)


class SwiftLibrary(BuildTarget):
    def __init__(
        self,
        *,
        srcs: list = [],
        swift_flags: list = [],
        cxx_interop: bool = False,
        swift_header: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.srcs = srcs
        self.swift_flags = swift_flags
        self.cxx_interop = cxx_interop
        self.swift_header = swift_header

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield


# Swift links other swift_libraries and imports C/C++ through a swift_cc_module
# bridge (never a cc_library directly); inputs may come from a repository.
SwiftLibrary.allowed_deps_types = (
    SwiftLibrary,
    SwiftCcModule,
    RepositoryTarget,
    PreBuildTarget,
)
