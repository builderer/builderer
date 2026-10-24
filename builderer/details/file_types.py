import os

from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Union


# What a file listed in a target's srcs or hdrs is, decided by its extension
# (case-insensitively). Every generator classifies files through this table, so
# they agree on what gets compiled and what is only included.
class FileKind(Enum):
    C = "c"
    CXX = "c++"
    OBJC = "objective-c"
    OBJCXX = "objective-c++"
    ASM = "assembly"
    SWIFT = "swift"
    METAL = "metal"
    HEADER = "header"


FILE_KINDS: Dict[str, FileKind] = {
    ".c": FileKind.C,
    ".cc": FileKind.CXX,
    ".cpp": FileKind.CXX,
    ".cxx": FileKind.CXX,
    ".m": FileKind.OBJC,
    ".mm": FileKind.OBJCXX,
    # ".S" (preprocessed assembly) matches too
    ".s": FileKind.ASM,
    ".swift": FileKind.SWIFT,
    ".metal": FileKind.METAL,
    ".h": FileKind.HEADER,
    ".hh": FileKind.HEADER,
    ".hpp": FileKind.HEADER,
    ".hxx": FileKind.HEADER,
    ".inl": FileKind.HEADER,
    ".inc": FileKind.HEADER,
    ".def": FileKind.HEADER,
    ".tc": FileKind.HEADER,
    ".th": FileKind.HEADER,
    # std-style headers without an extension, e.g. Eigen's "Dense"
    "": FileKind.HEADER,
}

# Kinds compiled by the C-family compiler drivers (clang, gcc, msvc, ...)
C_FAMILY_KINDS: FrozenSet[FileKind] = frozenset(
    {FileKind.C, FileKind.CXX, FileKind.OBJC, FileKind.OBJCXX, FileKind.ASM}
)


def file_extension(path: Union[str, "os.PathLike[str]"]) -> str:
    return os.path.splitext(os.fspath(path))[1].lower()


def file_kind(path: Union[str, "os.PathLike[str]"]) -> Optional[FileKind]:
    return FILE_KINDS.get(file_extension(path))


# The extensions of the given kinds, for tools that match on extensions
def kind_extensions(kinds: Iterable[FileKind]) -> List[str]:
    kinds = set(kinds)
    return sorted(ext for ext, kind in FILE_KINDS.items() if kind in kinds)
