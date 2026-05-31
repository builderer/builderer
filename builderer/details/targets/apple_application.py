from typing import Iterator, List, Optional, Tuple, Union

from builderer.conditional import ConditionalValue
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.target import BuildTarget

# iOS device families exposed to users by name, mapped to Apple's
# TARGETED_DEVICE_FAMILY codes. (3=tv, 4=watch reserved for future platforms.)
DEVICE_FAMILY_CODES = {
    "iphone": 1,
    "ipad": 2,
    "tv": 3,
    "watch": 4,
}


def _is_plist_value(value) -> bool:
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_plist_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_plist_value(v) for k, v in value.items())
    return False


# Validate an info_plist dict AFTER conditionals have been resolved. info_plist
# may legally contain ConditionalValue entries before resolution (e.g.
# Optional(Condition(platform="ios"), {...})), so validation is deferred until
# the generators have called resolve_conditionals. Keys must be plain strings;
# values must be plist-representable scalars/lists/dicts.
def validate_resolved_info_plist(target_name: str, info_plist: dict):
    if not isinstance(info_plist, dict):
        raise ValueError(
            f"AppleApplication '{target_name}' expected info_plist to resolve to a "
            f"dict, got {type(info_plist).__name__}"
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
        info_plist: dict,
        resources: list = [],
        development_team: Optional[str] = None,
        device_families: Optional[List[str]] = None,
        **kwargs,
    ):
        super().__init__(deps=[binary], **kwargs)
        self.binary = binary
        # An app bundle is invalid without an Info.plist (it must carry at least
        # CFBundleIdentifier/CFBundleExecutable), so info_plist is required. It
        # may be a dict (possibly containing ConditionalValue entries) or a
        # top-level ConditionalValue (e.g. a Switch returning a dict). Validation
        # of the resolved dict happens in the generators via
        # validate_resolved_info_plist(), after resolve_conditionals.
        self.info_plist: Union[dict, ConditionalValue]
        if isinstance(info_plist, ConditionalValue):
            self.info_plist = info_plist
        elif isinstance(info_plist, dict):
            self.info_plist = dict(info_plist)
        else:
            raise ValueError(
                f"AppleApplication '{self.name}' expected info_plist to be a dict or "
                f"a conditional, got {type(info_plist).__name__}"
            )
        self.resources = list(resources)
        self.development_team = development_team
        # A list of family names, or None. Conditionals on scalar config fields
        # (e.g. Optional(Condition(platform="ios"), ...)) are resolved by the
        # workspace before the generator reads this.
        self.device_families = device_families

    # Map the device_families names to a TARGETED_DEVICE_FAMILY string, e.g.
    # ["iphone", "ipad"] -> "1,2". Returns None when unset (the generator
    # applies the platform default).
    def targeted_device_family(self) -> Optional[str]:
        # None or empty (e.g. a platform-gated Optional that resolved away) means
        # "unset" — the generator applies the platform default.
        if not self.device_families:
            return None
        for name in self.device_families:
            if name not in DEVICE_FAMILY_CODES:
                raise ValueError(
                    f"AppleApplication '{self.name}' unknown device family "
                    f"'{name}'; expected one of {sorted(DEVICE_FAMILY_CODES)}"
                )
        return ",".join(str(DEVICE_FAMILY_CODES[name]) for name in self.device_families)

    def get_file_path_fields(self) -> Iterator[Tuple[str, list]]:
        if self.resources:
            yield "resource", self.resources

    def get_dir_path_fields(self) -> Iterator[Tuple[str, list]]:
        return
        yield

    def resolve_binary_target(self, workspace, package):
        dep_package, dep_target = workspace.find_target(self.binary, package)
        if not isinstance(dep_target, (CCBinary, SwiftBinary)):
            raise ValueError(
                f"AppleApplication '{self.name}' expects binary='{self.binary}' "
                f"to reference a cc_binary or swift_binary target"
            )
        return dep_package, dep_target
