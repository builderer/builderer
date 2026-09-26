import subprocess

from pathlib import Path

from builderer.details.targets.target import RepositoryTarget


class GitRepository(RepositoryTarget):
    def __init__(self, *, remote: str, sha: str, **kwargs):
        super().__init__(**kwargs)
        self.remote = remote
        self.sha = sha

    def fetch(self, scratch: Path) -> Path:
        print(f"cloning {self.remote}")
        subprocess.check_call(["git", "init", "--quiet"], cwd=scratch)
        subprocess.check_call(
            ["git", "remote", "add", "origin", self.remote], cwd=scratch
        )
        subprocess.check_call(
            ["git", "fetch", "--quiet", "--depth", "1", "origin", self.sha],
            cwd=scratch,
        )
        subprocess.check_call(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=scratch)
        return scratch
