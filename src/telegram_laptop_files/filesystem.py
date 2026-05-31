from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile
from typing import Literal
from urllib.parse import quote
import zipfile

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


class TrashUnavailableError(FilesystemError):
    """Raised when a file cannot be moved to the user's trash."""


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


@dataclass(frozen=True)
class DirectoryListing:
    directory: FileMetadata
    entries: tuple[FileMetadata, ...]


@dataclass(frozen=True)
class TextPreview:
    text: str
    bytes_read: int
    truncated: bool


@dataclass(frozen=True)
class ArchiveResult:
    path: Path
    size_bytes: int
    cleanup_directory: tempfile.TemporaryDirectory[str]


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

    def list_directory(
        self,
        root_id: str,
        relative_path: str | Path = "",
        *,
        show_hidden_files: bool = True,
    ) -> DirectoryListing:
        directory = self.metadata(root_id, relative_path)
        if directory.kind != "directory":
            raise FilesystemError(f"Path is not a directory: {directory.relative_path}")

        resolved = self.resolve(root_id, relative_path)
        entries: list[FileMetadata] = []
        try:
            children = list(resolved.path.iterdir())
        except FileNotFoundError as exc:
            raise FileNotFoundInRootError(
                f"Path not found in root '{root_id}': {resolved.relative_path}"
            ) from exc
        except PermissionError as exc:
            raise FilesystemError(f"Permission denied while listing: {resolved.relative_path}") from exc
        except OSError as exc:
            raise FilesystemError(f"Directory cannot be listed: {resolved.relative_path}") from exc

        for child in children:
            if not show_hidden_files and child.name.startswith("."):
                continue
            try:
                child_resolved = child.resolve(strict=True)
                if not _is_relative_to(child_resolved, resolved.root.path):
                    continue
                child_relative_path = _relative_to_root(resolved.root.path, child_resolved)
                entries.append(self.metadata(root_id, child_relative_path))
            except (FileNotFoundInRootError, UnsafePathError, ValueError):
                continue
            except PermissionError as exc:
                raise FilesystemError(f"Permission denied while inspecting: {child.name}") from exc
            except OSError:
                continue

        return DirectoryListing(
            directory=directory,
            entries=tuple(sorted(entries, key=_metadata_sort_key)),
        )

    def read_text_preview(self, root_id: str, relative_path: str | Path, max_bytes: int) -> TextPreview:
        metadata = self.metadata(root_id, relative_path)
        if metadata.kind != "file":
            raise FilesystemError(f"Path is not a file: {metadata.relative_path}")

        resolved = self.resolve(root_id, relative_path)
        try:
            with resolved.path.open("rb") as file:
                raw = file.read(max_bytes + 1)
        except FileNotFoundError as exc:
            raise FileNotFoundInRootError(
                f"Path not found in root '{root_id}': {metadata.relative_path}"
            ) from exc
        except PermissionError as exc:
            raise FilesystemError(f"Permission denied while previewing: {metadata.relative_path}") from exc
        except OSError as exc:
            raise FilesystemError(f"File cannot be previewed: {metadata.relative_path}") from exc

        truncated = len(raw) > max_bytes
        preview_bytes = raw[:max_bytes]
        if b"\x00" in preview_bytes:
            raise FilesystemError(f"File appears to be binary: {metadata.relative_path}")
        return TextPreview(
            text=preview_bytes.decode("utf-8", errors="replace"),
            bytes_read=len(preview_bytes),
            truncated=truncated,
        )

    def create_zip_archive(self, root_id: str, relative_path: str | Path) -> ArchiveResult:
        metadata = self.metadata(root_id, relative_path)
        if metadata.kind != "file":
            raise FilesystemError(f"Path is not a file: {metadata.relative_path}")

        resolved = self.resolve(root_id, relative_path)
        cleanup_directory = tempfile.TemporaryDirectory(prefix="tg-filer-")
        archive_path = Path(cleanup_directory.name) / f"{resolved.path.name}.zip"
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(resolved.path, arcname=resolved.path.name)
            size_bytes = archive_path.stat().st_size
        except Exception:
            cleanup_directory.cleanup()
            raise

        return ArchiveResult(path=archive_path, size_bytes=size_bytes, cleanup_directory=cleanup_directory)

    def move_file_to_trash(self, root_id: str, relative_path: str | Path) -> FileMetadata:
        metadata = self.metadata(root_id, relative_path)
        if metadata.kind == "directory":
            raise FilesystemError("Folder deletion is not available in this MVP.")
        if metadata.kind != "file":
            raise FilesystemError(f"Path is not a file: {metadata.relative_path}")

        resolved = self.resolve(root_id, relative_path)
        trash_files, trash_info = _trash_directories()
        try:
            trash_files.mkdir(parents=True, exist_ok=True)
            trash_info.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TrashUnavailableError(f"Trash is unavailable: {exc}") from exc

        destination, info_path = _trash_destination(trash_files, trash_info, resolved.path.name)
        deletion_date = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")
        trash_info_text = "\n".join(
            [
                "[Trash Info]",
                f"Path={quote(str(resolved.path), safe='/')}",
                f"DeletionDate={deletion_date}",
                "",
            ]
        )

        try:
            info_path.write_text(trash_info_text, encoding="utf-8")
            shutil.move(str(resolved.path), str(destination))
        except (OSError, shutil.Error) as exc:
            try:
                info_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise TrashUnavailableError(f"Could not move file to trash: {exc}") from exc

        return metadata

    def search_files(
        self,
        query: str,
        *,
        limit: int,
        show_hidden_files: bool = True,
    ) -> tuple[FileMetadata, ...]:
        tokens = tokenize_search_query(query)
        if not tokens:
            return ()

        results: list[FileMetadata] = []
        for root in self._roots_by_id.values():
            for current_dir, dir_names, file_names in os.walk(root.path, topdown=True, followlinks=False):
                current_path = Path(current_dir)
                try:
                    current_resolved = current_path.resolve(strict=True)
                except OSError:
                    dir_names[:] = []
                    continue
                if not _is_relative_to(current_resolved, root.path):
                    dir_names[:] = []
                    continue

                dir_names[:] = sorted(
                    [name for name in dir_names if show_hidden_files or not name.startswith(".")],
                    key=str.casefold,
                )

                for filename in sorted(file_names, key=str.casefold):
                    if not show_hidden_files and filename.startswith("."):
                        continue
                    normalized_name = filename.casefold()
                    if any(token not in normalized_name for token in tokens):
                        continue

                    child = current_resolved / filename
                    try:
                        child_resolved = child.resolve(strict=True)
                        if not _is_relative_to(child_resolved, root.path):
                            continue
                        relative_path = _relative_to_root(root.path, child_resolved)
                        metadata = self.metadata(root.id, relative_path)
                    except (FilesystemError, OSError, ValueError):
                        continue
                    if metadata.kind != "file":
                        continue

                    results.append(metadata)
                    if len(results) >= limit:
                        return tuple(results)

        return tuple(results)

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


def _metadata_sort_key(metadata: FileMetadata) -> tuple[int, str]:
    type_order = 0 if metadata.kind == "directory" else 1
    return type_order, metadata.name.casefold()


def tokenize_search_query(query: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in query.split() if part.strip())


def _trash_directories() -> tuple[Path, Path]:
    data_home = (
        Path(os.environ["XDG_DATA_HOME"]).expanduser()
        if os.environ.get("XDG_DATA_HOME")
        else Path.home() / ".local" / "share"
    )
    trash_root = data_home / "Trash"
    return trash_root / "files", trash_root / "info"


def _trash_destination(trash_files: Path, trash_info: Path, filename: str) -> tuple[Path, Path]:
    base_name = filename or "file"
    candidate_name = base_name
    counter = 1
    while True:
        destination = trash_files / candidate_name
        info_path = trash_info / f"{candidate_name}.trashinfo"
        if not destination.exists() and not info_path.exists():
            return destination, info_path
        candidate_name = f"{base_name}.{counter}"
        counter += 1
