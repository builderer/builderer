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
