import hashlib
import shutil
import urllib.parse
import urllib.request

from pathlib import Path
from tempfile import TemporaryDirectory

from builderer.details.targets.target import RepositoryTarget


def _download_archive(url: str, destination: Path) -> None:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request) as response:
        with destination.open("wb") as out:
            shutil.copyfileobj(response, out)


def _checksum_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _archive_name_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name
    if name:
        return name
    return "archive"


def _select_extracted_root(path: Path) -> Path:
    entries = list(path.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return path


class HttpsRepository(RepositoryTarget):
    def __init__(self, *, url: str, sha256: str, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.sha256 = sha256

    def do_pre_build(self):
        assert self.sandbox_root
        target_sandbox = Path(self.sandbox_root)
        if target_sandbox.is_dir():
            return
        assert not target_sandbox.exists()
        target_sandbox.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=str(target_sandbox.parent)) as tmp:
            tmp_root = Path(tmp)
            archive_path = tmp_root.joinpath(_archive_name_from_url(self.url))
            extracted_root = tmp_root.joinpath("extracted")
            extracted_root.mkdir(parents=True, exist_ok=False)
            print(f"downloading {self.url}")
            _download_archive(self.url, archive_path)
            actual_digest = _checksum_file(archive_path)
            if actual_digest.lower() != self.sha256.lower():
                raise RuntimeError(
                    f"checksum verification failed for {self.url}: "
                    f"expected {self.sha256}, got {actual_digest}"
                )
            shutil.unpack_archive(str(archive_path), str(extracted_root))
            _select_extracted_root(extracted_root).rename(target_sandbox)
