from typing import Iterator, Optional, Tuple

from builderer.details.targets.target import BuildTarget


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
