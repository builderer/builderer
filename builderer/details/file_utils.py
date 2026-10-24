import time

from pathlib import Path


# NOTE: On windows filesystem is sometimes not ready for rename immediately
#       after writing a tree, this function attempts to allow us to gracefully
#       handle this case by waiting a short time and trying again...
def rename_with_retry(src: Path, dst: Path, attempts: int = 3):
    for attempts_remaining in range(attempts, -1, -1):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempts_remaining:
                time.sleep(1)
                continue
            else:
                raise


# Leaves the file untouched when it already holds exactly this text, so tools
# watching generated files (e.g. Xcode) don't see a spurious modification.
def write_text_if_changed(path: Path, text: str):
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
