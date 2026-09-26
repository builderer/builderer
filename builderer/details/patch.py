import os
import re

from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

# Applies unified diffs (as produced by `git diff` and `git format-patch`) to a
# directory tree using only the standard library.
#
# - Edits to, creation of, and deletion of text files are supported.
# - Context and removed lines must match exactly. Line endings are matched
#   loosely so patches still apply after autocrlf conversion, and added lines
#   take the line-ending style of the file they are added to.
# - Hunks may have moved from their recorded line numbers.
# - Renames, copies, mode changes, and binary patches raise a ValueError.

HUNK_HEADER = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Git extended header lines describing changes other than text edits
UNSUPPORTED_GIT_HEADERS = (
    b"old mode ",
    b"new mode ",
    b"rename from ",
    b"rename to ",
    b"copy from ",
    b"copy to ",
    b"similarity index ",
    b"dissimilarity index ",
)

# C-style escapes used by git when quoting paths
QUOTED_ESCAPES = dict(zip(b'abtnvfr"\\', b'\a\b\t\n\v\f\r"\\'))


class Hunk:
    def __init__(self, *, label: str, position: int):
        # "<path> @@ -l,s +l,s @@", identifying the hunk in errors
        self.label = label
        # Index in the original file at which the hunk's old lines begin
        self.position = position
        # (op, text, eol) where op is b" ", b"-" or b"+"
        self.lines: List[Tuple[bytes, bytes, bytes]] = []
        self.old_missing_eol = False
        self.new_missing_eol = False

    @property
    def old_lines(self) -> List[bytes]:
        return [text for op, text, _ in self.lines if op != b"+"]


class FilePatch:
    def __init__(
        self,
        *,
        old_path: Optional[str],
        new_path: Optional[str],
        new_mode: Optional[int],
    ):
        # None when the file is created (old) or deleted (new)
        self.old_path = old_path
        self.new_path = new_path
        self.new_mode = new_mode
        self.hunks: List[Hunk] = []

    @property
    def path(self) -> str:
        path = self.new_path or self.old_path
        assert path
        return path


# Split after every b"\n", keeping line endings. A lone b"\r" is content.
def _split_lines(data: bytes) -> List[bytes]:
    lines = data.split(b"\n")
    result = [line + b"\n" for line in lines[:-1]]
    if lines[-1]:
        result.append(lines[-1])
    return result


def _split_eol(line: bytes) -> Tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    elif line.endswith(b"\n"):
        return line[:-1], b"\n"
    else:
        return line, b""


def _dominant_eol(lines: List[bytes]) -> Optional[bytes]:
    crlf = sum(1 for line in lines if line.endswith(b"\r\n"))
    lf = sum(1 for line in lines if line.endswith(b"\n")) - crlf
    if not crlf and not lf:
        return None
    return b"\r\n" if crlf > lf else b"\n"


def _unquote(path: bytes) -> bytes:
    if len(path) < 2 or not (path.startswith(b'"') and path.endswith(b'"')):
        return path
    out = bytearray()
    i, end = 1, len(path) - 1
    while i < end:
        if path[i] != ord("\\"):
            out.append(path[i])
            i += 1
        elif i + 1 < end and path[i + 1] in b"01234567":
            out.append(int(path[i + 1 : i + 4], 8))
            i += 4
        elif i + 1 < end and path[i + 1] in QUOTED_ESCAPES:
            out.append(QUOTED_ESCAPES[path[i + 1]])
            i += 2
        else:
            raise ValueError(f"invalid quoted path {path!r}")
    return bytes(out)


# Parse a ---/+++ header line into a path with its a/ or b/ prefix stripped,
# or None for /dev/null.
def _parse_header_path(line: bytes) -> Optional[str]:
    raw, _ = _split_eol(line[4:])
    # `diff -u` appends a tab-separated timestamp
    raw = _unquote(raw.split(b"\t", 1)[0])
    if raw == b"/dev/null":
        return None
    parts = raw.decode("utf-8", "surrogateescape").split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError(f"path {raw!r} has no a/ or b/ prefix")
    return parts[1]


# Parse the hunk for path starting at lines[i], returning it and the index
# after it.
def _parse_hunk(lines: List[bytes], i: int, path: str) -> Tuple[Hunk, int]:
    match = HUNK_HEADER.match(lines[i])
    if not match:
        raise ValueError(f"{path}: malformed hunk header {lines[i]!r}")
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_count = int(match.group(4)) if match.group(4) is not None else 1
    # A hunk without old lines inserts after line old_start
    hunk = Hunk(
        label=f"{path} " + _split_eol(lines[i])[0].decode("utf-8", "replace"),
        position=max(old_start - 1 if old_count else old_start, 0),
    )
    i += 1
    while old_count or new_count or (i < len(lines) and lines[i].startswith(b"\\")):
        if i >= len(lines):
            raise ValueError(f"{hunk.label}: hunk is truncated")
        line = lines[i]
        i += 1
        # "\ No newline at end of file" applies to the preceding line
        if line.startswith(b"\\"):
            if not hunk.lines:
                raise ValueError(f"{hunk.label}: unexpected {line!r}")
            last_op = hunk.lines[-1][0]
            hunk.old_missing_eol |= last_op != b"+"
            hunk.new_missing_eol |= last_op != b"-"
            continue
        # A blank context line may have had its leading space stripped
        if line in (b"\n", b"\r\n"):
            line = b" " + line
        op = line[:1]
        if op == b" ":
            old_count -= 1
            new_count -= 1
        elif op == b"-":
            old_count -= 1
        elif op == b"+":
            new_count -= 1
        else:
            raise ValueError(f"{hunk.label}: unexpected line {line!r}")
        if old_count < 0 or new_count < 0:
            raise ValueError(f"{hunk.label}: hunk has more lines than its header")
        hunk.lines.append((op, *_split_eol(line[1:])))
    return hunk, i


def parse_patch(data: bytes) -> List[FilePatch]:
    lines = _split_lines(data)
    file_patches: List[FilePatch] = []
    # The `diff --git` line whose ---/+++ lines have not been reached yet
    git_header: Optional[bytes] = None
    new_mode: Optional[int] = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(b"diff --git "):
            if git_header is not None:
                raise ValueError(f"unsupported change without edits: {git_header!r}")
            git_header, new_mode = line, None
            i += 1
        elif line.startswith((b"GIT binary patch", b"Binary files ")):
            raise ValueError(f"unsupported binary patch: {line!r}")
        elif git_header is not None and line.startswith(UNSUPPORTED_GIT_HEADERS):
            raise ValueError(f"unsupported change {line!r} in {git_header!r}")
        elif git_header is not None and line.startswith(b"new file mode "):
            new_mode = int(line.split()[-1], 8)
            i += 1
        elif (
            line.startswith(b"--- ")
            and i + 1 < len(lines)
            and lines[i + 1].startswith(b"+++ ")
        ):
            file_patch = FilePatch(
                old_path=_parse_header_path(line),
                new_path=_parse_header_path(lines[i + 1]),
                new_mode=new_mode,
            )
            if file_patch.old_path is None and file_patch.new_path is None:
                raise ValueError(f"both sides of {line!r} are /dev/null")
            if file_patch.old_path and file_patch.new_path:
                if file_patch.old_path != file_patch.new_path:
                    raise ValueError(
                        f"unsupported rename {file_patch.old_path} -> {file_patch.new_path}"
                    )
            i += 2
            while i < len(lines) and lines[i].startswith(b"@@ "):
                hunk, i = _parse_hunk(lines, i, file_patch.path)
                file_patch.hunks.append(hunk)
            if not file_patch.hunks:
                raise ValueError(f"no hunks for {file_patch.path}")
            file_patches.append(file_patch)
            git_header = None
        else:
            # Commit message, index lines, signature, etc.
            i += 1
    if git_header is not None:
        raise ValueError(f"unsupported change without edits: {git_header!r}")
    if not file_patches:
        raise ValueError("no file changes found")
    return file_patches


def _matches(lines: List[bytes], position: int, hunk: Hunk) -> bool:
    old = hunk.old_lines
    if position < 0 or position + len(old) > len(lines):
        return False
    for k, text in enumerate(old):
        if _split_eol(lines[position + k])[0] != text:
            return False
    # Only the last line of a file can lack a line ending
    if hunk.old_missing_eol:
        return position + len(old) == len(lines) and not _split_eol(lines[-1])[1]
    return True


# Locate the hunk's old lines, searching outward from the expected position
# but never before the end of the previous hunk, so hunks apply in order.
def _find(lines: List[bytes], expected: int, earliest: int, hunk: Hunk) -> int:
    if not hunk.old_lines:
        if earliest <= expected <= len(lines):
            return expected
        raise ValueError(f"{hunk.label}: insertion point is outside the file")
    for distance in range(max(expected, len(lines) - expected) + 1):
        for position in (expected - distance, expected + distance):
            if position >= earliest and _matches(lines, position, hunk):
                return position
    raise ValueError(f"{hunk.label}: does not match the file contents")


def _apply_hunks(original: List[bytes], file_patch: FilePatch) -> List[bytes]:
    eol = _dominant_eol(original)
    result: List[bytes] = []
    # Lines of original before this index have been copied into result
    consumed = 0
    # Displacement of the previous hunk from its recorded position
    offset = 0
    for hunk in file_patch.hunks:
        position = _find(original, hunk.position + offset, consumed, hunk)
        offset = position - hunk.position
        result.extend(original[consumed:position])
        consumed = position
        for op, text, line_eol in hunk.lines:
            if op == b" ":
                result.append(original[consumed])
                consumed += 1
            elif op == b"-":
                consumed += 1
            else:
                result.append(text + (eol or line_eol))
        at_end = consumed == len(original)
        if hunk.new_missing_eol:
            if not at_end:
                raise ValueError(f"{hunk.label}: missing newline is not at end of file")
            if result:
                result[-1] = _split_eol(result[-1])[0]
        elif at_end and result and not _split_eol(result[-1])[1]:
            result[-1] += eol or b"\n"
    result.extend(original[consumed:])
    return result


def _resolve(root: Path, path: str) -> Path:
    parts = PurePosixPath(path).parts
    if not parts or PurePosixPath(path).is_absolute() or ".." in parts:
        raise ValueError(f"path {path!r} is outside the patched tree")
    target = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved = target.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path {path!r} is outside the patched tree")
    return target


# Apply every file change in patch_file to the tree at root. All new contents
# are computed before anything is written, so a patch that fails leaves the
# tree untouched.
def apply_patch(root: Path, patch_file: Path):
    contents: Dict[Path, Optional[bytes]] = {}
    modes: Dict[Path, int] = {}
    for file_patch in parse_patch(patch_file.read_bytes()):
        target = _resolve(root, file_patch.path)
        if target in contents:
            current = contents[target]
        elif target.is_file():
            current = target.read_bytes()
        else:
            current = None
        if file_patch.old_path is None:
            if current is not None:
                raise ValueError(f"{file_patch.path}: new file already exists")
            current = b""
        elif current is None:
            raise ValueError(f"{file_patch.path}: file does not exist")
        patched = b"".join(_apply_hunks(_split_lines(current), file_patch))
        if file_patch.new_path is None:
            if patched:
                raise ValueError(f"{file_patch.path}: deleted file is not empty")
            contents[target] = None
        else:
            contents[target] = patched
            if file_patch.new_mode is not None:
                modes[target] = file_patch.new_mode
    for target, data in contents.items():
        if data is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    for target, mode in modes.items():
        if mode & 0o111:
            os.chmod(target, target.stat().st_mode | 0o111)
