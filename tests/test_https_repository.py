"""Tests for https_repository.

The URL-name parsing tests are pure (urllib.parse only -- no sockets). The
download/checksum tests drive the real do_pre_build logic with the underlying
network API (urllib.request.urlopen) mocked, so no network access ever happens;
a temporary directory is used only as a scratch sink for the unavoidable
archive I/O.
"""

import hashlib
import io
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from builderer.details.targets.https_repository import (
    _archive_name_from_url,
    HttpsRepository,
)


def _targz_bytes():
    """A .tar.gz holding a single top-level directory with one file."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"hello"
        info = tarfile.TarInfo(name="pkgroot/file.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _repo(sha256, sandbox_root):
    repo = HttpsRepository(
        url="https://example.com/pkg.tar.gz",
        sha256=sha256,
        name="dep",
        workspace_root="pkg",
    )
    repo.sandbox_root = str(sandbox_root)
    return repo


class TestArchiveNameFromUrl(unittest.TestCase):
    def test_archive_name_from_url_uses_path_basename(self):
        self.assertEqual(
            _archive_name_from_url("https://example.com/a/file.zip?token=abc"),
            "file.zip",
        )

    def test_archive_name_from_url_falls_back_when_no_filename(self):
        self.assertEqual(_archive_name_from_url("https://example.com/"), "archive")


class TestHttpsRepositoryPreBuild(unittest.TestCase):
    def test_do_pre_build_extracts_when_checksum_matches(self):
        archive = _targz_bytes()
        with tempfile.TemporaryDirectory() as scratch:
            sandbox = Path(scratch) / "sb"
            with mock.patch.object(
                urllib.request, "urlopen", lambda request: io.BytesIO(archive)
            ):
                repo = _repo(hashlib.sha256(archive).hexdigest(), sandbox)
                repo.do_pre_build()
            # single-dir archive is unwrapped, so the file lands directly in
            # the sandbox
            self.assertEqual((sandbox / "file.txt").read_text(), "hello")

    def test_do_pre_build_rejects_checksum_mismatch(self):
        archive = _targz_bytes()
        with tempfile.TemporaryDirectory() as scratch:
            sandbox = Path(scratch) / "sb"
            with mock.patch.object(
                urllib.request, "urlopen", lambda request: io.BytesIO(archive)
            ):
                repo = _repo("00" * 32, sandbox)
                with self.assertRaisesRegex(
                    RuntimeError, "checksum verification failed"
                ):
                    repo.do_pre_build()
            # nothing is left behind on failure
            self.assertFalse(sandbox.exists())
