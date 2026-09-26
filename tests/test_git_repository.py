"""Tests for git_repository.

The "remote" is a throwaway local repository addressed by file:// URL, so the
real clone path runs without any network access.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from builderer.details.targets.git_repository import GitRepository
from factories import make_config, make_package, make_workspace

PATCH_1 = """\
diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-hello
+hello patched
"""

# Only applies on top of PATCH_1
PATCH_2 = """\
diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-hello patched
+hello patched twice
"""


def _git(*args, cwd):
    subprocess.check_call(
        [
            "git",
            "-c",
            "user.name=builderer",
            "-c",
            "user.email=builderer@example.com",
            *args,
        ],
        cwd=cwd,
    )


class TestGitRepository(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.scratch = Path(self._scratch.name).resolve()
        self.remote = self.scratch / "remote"
        self.remote.mkdir()
        _git("init", "--quiet", cwd=self.remote)
        (self.remote / "file.txt").write_text("hello\n")
        _git("add", "file.txt", cwd=self.remote)
        _git("commit", "--quiet", "-m", "initial", cwd=self.remote)
        _git("tag", "v1", cwd=self.remote)
        self.pkg = self.scratch / "pkg"
        self.pkg.mkdir()
        (self.pkg / "1.patch").write_text(PATCH_1)
        (self.pkg / "2.patch").write_text(PATCH_2)
        self.sandbox = self.scratch / "sb" / "repo" / "0123456789abcdef"

    def tearDown(self):
        self._scratch.cleanup()

    def _repo(self, patches=[], sha="v1") -> GitRepository:
        return GitRepository(
            remote=self.remote.as_uri(),
            sha=sha,
            name="repo",
            workspace_root=self.pkg.as_posix(),
            patches=patches,
        )

    def _pre_build(self, patches=[]):
        repo = self._repo([(self.pkg / p).as_posix() for p in patches])
        repo.sandbox_root = self.sandbox.as_posix()
        repo.do_pre_build()

    def _sandbox_hash(self, patches, sha="v1") -> str:
        repo = self._repo(patches, sha)
        package = make_package("pkg", [repo])
        workspace = make_workspace([package])
        workspace._expand_variables(config=make_config(), package=package, target=repo)
        assert repo.sandbox_root
        return Path(repo.sandbox_root).name

    def test_do_pre_build_checks_out_revision(self):
        self._pre_build()
        self.assertEqual((self.sandbox / "file.txt").read_text(), "hello\n")

    def test_do_pre_build_applies_patches_in_order(self):
        self._pre_build(["1.patch", "2.patch"])
        self.assertEqual(
            (self.sandbox / "file.txt").read_text(), "hello patched twice\n"
        )
        # the pinned commit stays HEAD, so `git diff` shows exactly the patches
        diff = subprocess.check_output(
            ["git", "diff", "--name-only"], cwd=self.sandbox, text=True
        )
        self.assertEqual(diff.split(), ["file.txt"])

    def test_do_pre_build_failed_patch_leaves_nothing_behind(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self._pre_build(["2.patch"])
        self.assertFalse(self.sandbox.exists())
        self.assertEqual(list(self.sandbox.parent.iterdir()), [])

    def test_do_pre_build_leaves_existing_sandbox_untouched(self):
        self.sandbox.mkdir(parents=True)
        self._pre_build(["1.patch"])
        self.assertEqual(list(self.sandbox.iterdir()), [])

    def test_unchanged_inputs_keep_sandbox_hash(self):
        patches = ["1.patch", "2.patch"]
        self.assertEqual(self._sandbox_hash(patches), self._sandbox_hash(patches))

    def test_patch_or_revision_changes_yield_new_sandbox_hash(self):
        before = self._sandbox_hash(["1.patch", "2.patch"])
        self.assertNotEqual(before, self._sandbox_hash(["2.patch", "1.patch"]))
        self.assertNotEqual(before, self._sandbox_hash(["1.patch"]))
        self.assertNotEqual(before, self._sandbox_hash(["1.patch", "2.patch"], "v2"))
        (self.pkg / "2.patch").write_text(PATCH_2 + "+edited\n")
        self.assertNotEqual(before, self._sandbox_hash(["1.patch", "2.patch"]))
