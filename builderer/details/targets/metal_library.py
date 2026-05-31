from typing import Iterator, Tuple

from builderer.details.targets.target import (
    BuildTarget,
    PreBuildTarget,
    RepositoryTarget,
)


class MetalLibrary(BuildTarget):
    def __init__(
        self,
        *,
        srcs: list = [],
        metal_flags: list = [],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.srcs = srcs
        self.metal_flags = metal_flags
        # The library's artifact is <target.name>.metallib (named like every other
        # target's product). An app embeds each metal_library dep's
        # <target.name>.metallib at its resources root, with no per-app config and
        # no renaming. Load it at runtime by name:
        #   device.makeLibrary(URL: Bundle.main.url(
        #       forResource: "<target.name>", withExtension: "metallib")!).
        # A target named "default" produces default.metallib, which Metal also
        # loads via device.makeDefaultLibrary() -- a natural side effect of the
        # filename, not a special case.

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.srcs:
            yield "source", self.srcs

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield


# A metal_library compiles only its own .metal srcs; it may source them from a
# repository or a generated-file (prebuild) target. Its <target.name>.metallib is
# embedded by an apple_application (which declares MetalLibrary in its allowed deps).
MetalLibrary.allowed_deps_types = (RepositoryTarget, PreBuildTarget)
