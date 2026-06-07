"""Tests for https_repository.

The URL-name parsing tests are pure (urllib.parse only -- no sockets). The
download/checksum tests drive the real do_pre_build logic with the underlying
network API (urllib.request.urlopen) mocked, so no network access ever happens;
a tmp_path is used only as a scratch sink for the unavoidable archive I/O.
"""

import hashlib
import io
import tarfile
import urllib.request

import pytest

from builderer.details.targets.https_repository import (
    _archive_name_from_url,
    HttpsRepository,
)


def test_archive_name_from_url_uses_path_basename():
    assert _archive_name_from_url("https://example.com/a/file.zip?token=abc") == (
        "file.zip"
    )


def test_archive_name_from_url_falls_back_when_no_filename():
    assert _archive_name_from_url("https://example.com/") == "archive"


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


def test_do_pre_build_extracts_when_checksum_matches(tmp_path, monkeypatch):
    archive = _targz_bytes()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request: io.BytesIO(archive))
    repo = _repo(hashlib.sha256(archive).hexdigest(), tmp_path / "sb")
    repo.do_pre_build()
    # single-dir archive is unwrapped, so the file lands directly in the sandbox
    assert (tmp_path / "sb" / "file.txt").read_text() == "hello"


def test_do_pre_build_rejects_checksum_mismatch(tmp_path, monkeypatch):
    archive = _targz_bytes()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request: io.BytesIO(archive))
    repo = _repo("00" * 32, tmp_path / "sb")
    with pytest.raises(RuntimeError, match="checksum verification failed"):
        repo.do_pre_build()
    assert not (tmp_path / "sb").exists()  # nothing is left behind on failure
