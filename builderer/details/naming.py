from pathlib import PurePosixPath
from typing import Dict, Iterable

# Flat names stand in for canonical "pkg/path:target" names wherever "/" and ":"
# are not allowed (Xcode scheme file names, make targets and variables). "/" maps
# to "." and ":" maps to "@". Reserving "@" in package and target names keeps the
# package/target split unambiguous; "." stays legal (versioned directories,
# "foo.app" targets), so packages that differ only by "/" vs "." are rejected
# instead (see check_package_name_conflicts).
RESERVED_PACKAGE_CHARS = "@:"
RESERVED_TARGET_CHARS = "@:/"


def flat_package_name(package_name: str) -> str:
    return ".".join(PurePosixPath(package_name).parts)


def flat_target_name(package_name: str, target_name: str) -> str:
    return f"{flat_package_name(package_name)}@{target_name}"


def validate_package_name(name: str):
    for part in PurePosixPath(name).parts:
        if any(c in part for c in RESERVED_PACKAGE_CHARS):
            raise ValueError(
                f"package name='{name}' must not contain any of "
                f"'{RESERVED_PACKAGE_CHARS}' in its directory names"
            )


def validate_target_name(name: str):
    if any(c in name for c in RESERVED_TARGET_CHARS):
        raise ValueError(
            f"target name='{name}' must not contain any of '{RESERVED_TARGET_CHARS}'"
        )


# Packages whose flat names match (e.g. "python/3.9" and "python.3.9") would
# produce identical flat target names, so they cannot coexist in a workspace.
def check_package_name_conflicts(names: Iterable[str]):
    seen: Dict[str, str] = {}
    for name in sorted(names):
        flat = flat_package_name(name)
        if flat in seen:
            raise ValueError(
                f"package '{name}' conflicts with '{seen[flat]}': package names "
                f"must stay distinct when '/' is read as '.'"
            )
        seen[flat] = name
