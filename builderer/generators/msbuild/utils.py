import uuid

from pathlib import Path, PureWindowsPath
from typing import Union


def as_msft_path(path: Union[str, Path]) -> str:
    return str(PureWindowsPath(path))


def make_guid(key: str) -> str:
    return f"{{{uuid.uuid5(uuid.NAMESPACE_X500, key)}}}".upper()


def msvc_file_rule(path: Path) -> str:
    if path.suffix.lower() in [".cpp", ".cc", ".c"]:
        return "ClCompile"
    elif path.suffix.lower() in [".h", ".hpp", ".inl"]:
        return "ClInclude"
    else:
        raise ValueError(f"Unsupported file extension for {path}")
