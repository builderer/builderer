import subprocess
import time

from pathlib import Path
from tempfile import TemporaryDirectory

from builderer.details.targets.target import RepositoryTarget


# NOTE: On windows filesystem is sometimes not ready for rename immediately
#       after cloning, this function attempts to allow us to gracefully
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


class GitRepository(RepositoryTarget):
    def __init__(self, *, remote: str, sha: str, **kwargs):
        super().__init__(**kwargs)
        self.remote = remote
        self.sha = sha

    def do_pre_build(self):
        assert self.sandbox_root
        target_sandbox = Path(self.sandbox_root)
        if target_sandbox.is_dir():
            return
        assert not target_sandbox.exists()
        target_sandbox.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=str(target_sandbox.parent)) as tmp:
            print(f"cloning {self.remote}")
            subprocess.check_call(["git", "init", "--quiet"], cwd=tmp)
            subprocess.check_call(
                ["git", "remote", "add", "origin", self.remote], cwd=tmp
            )
            subprocess.check_call(
                ["git", "fetch", "--quiet", "--depth", "1", "origin", self.sha], cwd=tmp
            )
            subprocess.check_call(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=tmp)
            rename_with_retry(Path(tmp), target_sandbox)
