from pathlib import Path

from app.core.config import settings


class LocalFileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        normalized = str(key or "").replace("\\", "/").lstrip("/")
        if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("Invalid storage key")
        path = (self.root / normalized).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def open(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def metadata(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return {"size": path.stat().st_size, "name": path.name}


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(settings.document_storage_dir)
