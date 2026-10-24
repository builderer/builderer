import uuid

from pathlib import Path, PureWindowsPath
from typing import Union

from builderer.details.file_types import FileKind, file_kind


def as_msft_path(path: Union[str, Path]) -> str:
    return str(PureWindowsPath(path))


# MSBuild reads these characters as syntax (property, item and metadata
# references, list separators, wildcards, condition quotes). %XX makes them
# literal; MSBuild unescapes values before passing them to tools.
MSBUILD_SPECIAL_CHARACTERS = "%$@';?*"


def msbuild_escape(value: str) -> str:
    return "".join(
        f"%{ord(c):02X}" if c in MSBUILD_SPECIAL_CHARACTERS else c for c in value
    )


def make_guid(key: str) -> str:
    return f"{{{uuid.uuid5(uuid.NAMESPACE_X500, key)}}}".upper()


def msvc_file_rule(path: Path) -> str:
    kind = file_kind(path)
    if kind in (FileKind.C, FileKind.CXX):
        return "ClCompile"
    elif kind is FileKind.HEADER:
        return "ClInclude"
    else:
        raise ValueError(f"Unsupported file extension for {path}")


def is_compile_rule(rule: str) -> bool:
    return rule == "ClCompile"
