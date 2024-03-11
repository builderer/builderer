from typing import Iterator, Tuple, Optional

from builderer.details.targets.target import BuildTarget

class CCBinary(BuildTarget):
    def __init__(self,
                 *,
                 srcs: list = [],
                 c_flags: list = [],
                 cxx_flags: list = [],
                 link_flags: list = [],
                 private_defines: list = [],
                 private_includes: list = [],
                 output_path: Optional[str] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.srcs = srcs
        self.c_flags = c_flags
        self.cxx_flags = cxx_flags
        self.link_flags = link_flags
        self.private_defines = private_defines
        self.private_includes = private_includes
        self.output_path = output_path
    
    def get_file_path_fields(self) -> Iterator[Tuple[str,list]]:
        if self.srcs:
            yield "source",self.srcs
        if self.private_includes:
            yield "private",self.private_includes
