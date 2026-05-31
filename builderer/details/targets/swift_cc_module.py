from typing import Iterator, Tuple

from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.target import (
    Target,
    PreBuildTarget,
    RepositoryTarget,
)


class SwiftCcModule(Target):
    def __init__(
        self,
        *,
        module_maps: list = [],
        **kwargs,
    ):
        super().__init__(**kwargs)
        if not module_maps:
            raise ValueError(
                f"swift_cc_module '{kwargs.get('name')}' requires at least one entry in module_maps"
            )
        self.module_maps = list(module_maps)

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        yield "module_maps", self.module_maps

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield


# The bridge directly depends on the cc_library its modulemap describes; the
# modulemap itself may be sourced from a repository.
SwiftCcModule.allowed_deps_types = (CCLibrary, RepositoryTarget, PreBuildTarget)
