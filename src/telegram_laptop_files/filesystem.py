from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .config import RootConfig

FileKind = Literal["directory", "file", "other"]


class FilesystemError(ValueError):
    """Raised when a requested file path is not allowed or cannot be read."""


class UnknownRootError(FilesystemError):
    """Raised when a request references a root id that is not configured."""


class UnsafePathError(FilesystemError):
    """Raised when a request would escape its configured root."""


class FileNotFoundInRootError(FilesystemError):
    """Raised when a requested path inside a root no longer exists."""


@dataclass(frozen=True)
class ResolvedPath:
    root: RootConfig
    path: Path
    relative_path: str


@dataclass(frozen=True)
class FileMetadata:
    root_id: str
    relative_path: str
    name: str
    kind: FileKind
    size_bytes: int
    modified_at: datetime


class FilesystemResolver:
    def __init__(self, roots: tuple[RootConfig, ...]) -> None:
        self._roots_by_id = {root.id: root for root in roots}

    def resolve(self, root_id: str, relative_path: str | Path = "") -> ResolvedPath:
        root = self._root(root_id)
        requested = _clean_relative_path(relative_path)
        candidate = root.path / requested

        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFoundInRootError(f"Path not found in root '{root_id}': {requested}") from exc
        except OSError as exc:
            raise FilesystemError(f"Path cannot be resolved in root '{root_id}': {requested}") from exc

        if not _is_relative_to(resolved, root.path):
            raise UnsafePathError(f"Path escapes configured root '{root_id}': {requested}")

        return ResolvedPath(root=root, path=resolved, relative_path=_relative_to_root(root.path, resolved))

    def metadata(self, root_id: str, relative_path: str | Path = "") -> FileMetadata:
        resolved = self.resolve(root_id, relative_path)

        try:
            stat_result = resolved.path.stat()
        except FileNotFoundError as exc:
            raise FileNotFoundInRootError(
                f"Path not found in root '{root_id}': {resolved.relative_path}"
            ) from exc
        except OSError as exc:
            raise FilesystemError(f"Path cannot be inspected in root '{root_id}': {resolved.relative_path}") from exc

        if resolved.path.is_dir():
            kind: FileKind = "directory"
        elif resolved.path.is_file():
            kind = "file"
        else:
            kind = "other"

        return FileMetadata(
            root_id=resolved.root.id,
            relative_path=resolved.relative_path,
            name=resolved.path.name,
            kind=kind,
            size_bytes=stat_result.st_size,
            modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
        )

    def _root(self, root_id: str) -> RootConfig:
        try:
            return self._roots_by_id[root_id]
        except KeyError as exc:
            raise UnknownRootError(f"Unknown filesystem root: {root_id}") from exc


def _clean_relative_path(relative_path: str | Path) -> Path:
    raw = str(relative_path)
    if "\x00" in raw:
        raise UnsafePathError("Path contains a null byte")

    path = Path(raw)
    if path.is_absolute():
        raise UnsafePathError(f"Absolute paths are not allowed: {raw}")

    parts = path.parts
    if any(part == ".." for part in parts):
        raise UnsafePathError(f"Path traversal is not allowed: {raw}")

    return Path(*[part for part in parts if part != "."])


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _relative_to_root(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if str(relative) == ".":
        return ""
    return relative.as_posix()
