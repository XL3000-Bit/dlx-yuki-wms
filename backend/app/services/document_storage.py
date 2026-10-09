from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import HTTPException

from app.core.config import settings


@dataclass(frozen=True)
class StoredObjectMetadata:
    key: str
    size: int


class LocalDocumentStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.document_storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        posix = PurePosixPath(key)
        if not key or posix.is_absolute() or ".." in posix.parts or "\\" in key:
            raise HTTPException(400, "Invalid document storage key")
        path = (self.root / Path(*posix.parts)).resolve()
        if self.root != path and self.root not in path.parents:
            raise HTTPException(400, "Invalid document storage key")
        return path

    def save(self, key: str, source: BinaryIO, max_bytes: int) -> tuple[int, str]:
        import hashlib
        path = self._path(key); path.parent.mkdir(parents=True, exist_ok=True)
        size = 0; digest = hashlib.sha256()
        try:
            with path.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, f"Document exceeds {max_bytes} byte limit")
                    digest.update(chunk); target.write(chunk)
            if size == 0:
                raise HTTPException(422, "Empty document is not valid evidence")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return size, digest.hexdigest()

    def open(self, key: str) -> BinaryIO: return self._path(key).open("rb")
    def delete(self, key: str) -> None: self._path(key).unlink(missing_ok=True)
    def exists(self, key: str) -> bool: return self._path(key).is_file()
    def metadata(self, key: str) -> StoredObjectMetadata:
        path = self._path(key)
        if not path.is_file(): raise FileNotFoundError(key)
        return StoredObjectMetadata(key, path.stat().st_size)
