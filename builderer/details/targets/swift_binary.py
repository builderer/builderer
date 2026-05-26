from typing import Iterator, Tuple

from builderer.details.targets.target import BuildTarget


class SwiftBinary(BuildTarget):
    def __init__(
        self,
        *,
        srcs: list = [],
        swift_flags: list = [],
        link_flags: list = [],
        cxx_interop: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.srcs = srcs
        self.swift_flags = swift_flags
        self.link_flags = link_flags
        self.cxx_interop = cxx_interop

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield
