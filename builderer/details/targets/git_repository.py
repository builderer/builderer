import subprocess

from pathlib import Path
from tempfile import TemporaryDirectory

from builderer.details.targets.target import RepositoryTarget


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
            Path(tmp).rename(target_sandbox)
