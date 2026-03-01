from typing import Iterator, Optional, Tuple

from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.target import BuildTarget


def _is_plist_value(value) -> bool:
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_plist_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_plist_value(v) for k, v in value.items())
    return False


def _validate_info_plist_dict(target_name: str, info_plist: Optional[dict]):
    if info_plist is None:
        return
    if not isinstance(info_plist, dict):
        raise ValueError(
            f"AppleApplication '{target_name}' expected info_plist to be a dict, "
            f"got {type(info_plist).__name__}"
        )
    if not all(isinstance(k, str) for k in info_plist.keys()):
        raise ValueError(
            f"AppleApplication '{target_name}' info_plist keys must all be strings"
        )
    if not _is_plist_value(info_plist):
        raise ValueError(
            f"AppleApplication '{target_name}' info_plist contains unsupported value types"
        )


class AppleApplication(BuildTarget):
    def __init__(
        self,
        *,
        binary: str,
        info_plist: Optional[dict] = None,
        resources: list = [],
        **kwargs,
    ):
        super().__init__(deps=[binary], **kwargs)
        self.binary = binary
        self.info_plist = dict(info_plist) if info_plist is not None else None
        _validate_info_plist_dict(target_name=self.name, info_plist=self.info_plist)
        self.resources = list(resources)

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.resources:
            yield "resource", self.resources

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield

    def resolve_binary_target(self, workspace, package):
        dep_package, dep_target = workspace.find_target(self.binary, package)
        if not isinstance(dep_target, CCBinary):
            raise ValueError(
                f"AppleApplication '{self.name}' expects binary='{self.binary}' "
                f"to reference a cc_binary target"
            )
        return dep_package, dep_target
