from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path

from .config import AppConfig, RootConfig
from .filesystem import ContentSearchResult, FileMetadata, TextPreview

MAX_PREVIEW_MESSAGE_CHARS = 3000
PREVIEWABLE_EXTENSIONS = frozenset(
    {
        ".cfg",
        ".conf",
        ".csv",
        ".env",
        ".ini",
        ".json",
        ".log",
        ".md",
        ".py",
        ".rst",
        ".toml",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


def format_roots_message(roots: tuple[RootConfig, ...]) -> str:
    lines = ["<b>roots</b>"]
    for index, root in enumerate(roots, start=1):
        display_name = html.escape(root.display_name)
        lines.append(f"<code>{index})</code> {display_name}")
    return "\n".join(lines)


def format_help_message() -> str:
    return "\n".join(
        [
            "<b>Commands</b>",
            "<code>/start</code> - Show bot status and configured root folders.",
            "<code>/roots</code> - Show configured root folders.",
            "<code>/recent</code> - Show recently modified files.",
            "<code>/search &lt;query&gt;</code> - Find files by name or path.",
            "<code>/content &lt;query&gt;</code> - Find text inside configured files.",
            "<code>/status</code> - Show bot health and current limits.",
            "<code>/help</code> - Show available commands.",
            "<code>/cancel</code> - Cancel the current pending action.",
            "",
            "<b>Navigation</b>",
            "<code>1</code> - Select a root or item from the current list.",
            "<code>/folder-name</code> - Enter a folder by exact name or unique 3+ character prefix.",
            "<code>/..</code> - Go to the parent folder.",
            "<code>/</code> - Go to the selected root.",
            "Use the buttons on file details to preview, download, compress, delete, or go back.",
        ]
    )


def format_directory_message(
    directory: FileMetadata,
    all_entries: tuple[FileMetadata, ...],
    visible_entries: tuple[FileMetadata, ...],
    page: int,
    total_pages: int,
) -> str:
    path = _format_shell_path(directory.root_id, directory.relative_path)
    dir_count = sum(1 for entry in all_entries if entry.kind == "directory")
    file_count = sum(1 for entry in all_entries if entry.kind == "file")
    other_count = len(all_entries) - dir_count - file_count
    lines = [
        f"<b><code>{html.escape(path)}</code></b>",
        _format_counts(dir_count, file_count, other_count),
        "",
    ]

    if not visible_entries:
        lines.append("(empty)")
    else:
        for index, entry in enumerate(visible_entries, start=1):
            suffix = "/" if entry.kind == "directory" else ""
            detail = "" if entry.kind == "directory" else f"  {format_size(entry.size_bytes)}"
            lines.append(f"<code>{index})</code> <code>{html.escape(entry.name + suffix)}</code>{detail}")

    if total_pages > 1:
        lines.extend(["", f"page {page + 1}/{total_pages}"])
    return "\n".join(lines)


def format_file_detail_message(metadata: FileMetadata, max_upload_bytes: int) -> str:
    lines = [
        f"<b>{html.escape(metadata.name)}</b>",
        f"Path: <code>{html.escape(metadata.relative_path)}</code>",
        f"Size: {format_size(metadata.size_bytes)}",
        f"Modified: {metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
    ]
    if metadata.kind != "file":
        lines.append("")
        lines.append("This item is not a regular downloadable file.")
    elif metadata.size_bytes > max_upload_bytes:
        lines.append("")
        lines.append(
            f"This file is larger than the upload limit ({format_size(max_upload_bytes)}). "
            "You can create a compressed archive."
        )
    elif not is_previewable_file(metadata.name):
        lines.append("")
        lines.append("Preview is unavailable for this file type. Metadata and download are available.")
    return "\n".join(lines)


def format_preview_message(metadata: FileMetadata, preview: TextPreview) -> str:
    preview_text = html.escape(preview.text)
    if len(preview_text) > MAX_PREVIEW_MESSAGE_CHARS:
        preview_text = f"{preview_text[:MAX_PREVIEW_MESSAGE_CHARS]}\n..."
    lines = [
        "<b>Preview</b>",
        f"<code>{html.escape(metadata.relative_path)}</code>",
        f"{format_size(preview.bytes_read)} shown"
        + ("; file continues beyond preview limit." if preview.truncated else "."),
        "",
        f"<pre>{preview_text}</pre>",
    ]
    return "\n".join(lines)


def format_unsupported_preview_message(metadata: FileMetadata) -> str:
    return "\n".join(
        [
            "<b>Preview unavailable</b>",
            f"<code>{html.escape(metadata.relative_path)}</code>",
            "",
            "This file type is not configured for text preview.",
            f"Size: {format_size(metadata.size_bytes)}",
            f"Modified: {metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        ]
    )


def format_delete_confirmation_message(metadata: FileMetadata, expires_at: datetime) -> str:
    return "\n".join(
        [
            "<b>Confirm delete</b>",
            f"<code>{html.escape(metadata.root_id)}:/{html.escape(metadata.relative_path)}</code>",
            f"Size: {format_size(metadata.size_bytes)}",
            f"Modified: {metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "",
            "This will move the file to trash.",
            f"Expires: {expires_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        ]
    )


def format_search_results_message(query: str, results: tuple[FileMetadata, ...], limit: int) -> str:
    lines = [
        "<b>Search results</b>",
        f"Query: <code>{html.escape(query)}</code>",
        "",
    ]

    if not results:
        lines.append("No matching files.")
        return "\n".join(lines)

    for index, metadata in enumerate(results, start=1):
        lines.extend(
            [
                f"<code>{index})</code> <b>{html.escape(metadata.name)}</b>",
                f"     <code>{html.escape(metadata.root_id)}:/{html.escape(metadata.relative_path)}</code>",
                (
                    f"     {format_size(metadata.size_bytes)} · "
                    f"{metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
                ),
            ]
        )

    if len(results) >= limit:
        lines.extend(["", f"Showing first {limit} matches."])
    return "\n".join(lines)


def format_content_search_results_message(query: str, results: tuple[ContentSearchResult, ...], limit: int) -> str:
    lines = [
        "<b>Content search results</b>",
        f"Query: <code>{html.escape(query)}</code>",
        "",
    ]

    if not results:
        lines.append("No matching text files.")
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        metadata = result.metadata
        lines.extend(
            [
                f"<code>{index})</code> <b>{html.escape(metadata.name)}</b>",
                f"     <code>{html.escape(metadata.root_id)}:/{html.escape(metadata.relative_path)}</code>",
                (
                    f"     {format_size(metadata.size_bytes)} · "
                    f"{metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
                ),
                f"     <i>{html.escape(result.snippet)}</i>",
            ]
        )

    if len(results) >= limit:
        lines.extend(["", f"Showing first {limit} matches."])
    return "\n".join(lines)


def format_recent_files_message(results: tuple[FileMetadata, ...], limit: int) -> str:
    lines = ["<b>Recent files</b>", ""]

    if not results:
        lines.append("No recent files found.")
        return "\n".join(lines)

    for index, metadata in enumerate(results, start=1):
        lines.extend(
            [
                f"<code>{index})</code> <b>{html.escape(metadata.name)}</b>",
                f"     <code>{html.escape(metadata.root_id)}:/{html.escape(metadata.relative_path)}</code>",
                (
                    f"     {format_size(metadata.size_bytes)} · "
                    f"{metadata.modified_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
                ),
            ]
        )

    if len(results) >= limit:
        lines.extend(["", f"Showing first {limit} files."])
    return "\n".join(lines)


def format_status_message(
    config: AppConfig,
    *,
    audit_writable: bool,
    proxy_configured: bool,
    session_path: str | None,
) -> str:
    lines = [
        f"<b>{html.escape(config.name)} status</b>",
        f"Token: {'set' if config.telegram.bot_token else 'missing'}",
        f"Proxy: {'configured' if proxy_configured else 'not configured'}",
        f"Audit log: {'writable' if audit_writable else 'not writable'}",
        f"Roots: {len(config.filesystem.roots)}",
        f"Search results: {config.filesystem.search_result_limit}",
        f"Content max: {format_size(config.filesystem.content_search_max_bytes)}",
        f"Upload max: {format_size(config.filesystem.max_upload_bytes)}",
    ]
    if session_path:
        lines.append(f"Session: <code>{html.escape(session_path)}</code>")
    else:
        lines.append("Session: none")
    return "\n".join(lines)


def is_previewable_file(filename: str) -> bool:
    name = Path(filename).name.casefold()
    return name in PREVIEWABLE_EXTENSIONS or Path(name).suffix.casefold() in PREVIEWABLE_EXTENSIONS


def format_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _format_shell_path(root_id: str, relative_path: str) -> str:
    if not relative_path:
        return f"{root_id}:/"
    return f"{root_id}:/{relative_path}"


def _format_counts(dir_count: int, file_count: int, other_count: int) -> str:
    parts = [f"{dir_count} dirs", f"{file_count} files"]
    if other_count:
        parts.append(f"{other_count} other")
    return " · ".join(parts)
