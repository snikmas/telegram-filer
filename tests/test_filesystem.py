from pathlib import Path
from datetime import datetime, timezone
import os
import tempfile
import unittest
from unittest.mock import patch

from telegram_laptop_files.config import AppConfig, ConfigError, RootConfig, _parse_config
from telegram_laptop_files.filesystem import (
    FileNotFoundInRootError,
    FilesystemResolver,
    FilesystemError,
    TrashUnavailableError,
    UnknownRootError,
    UnsafePathError,
    tokenize_search_query,
)


class FilesystemResolverTests(unittest.TestCase):
    def test_resolves_path_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            nested = root_path / "notes" / "today.md"
            nested.parent.mkdir()
            nested.write_text("hello", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            resolved = resolver.resolve("work", "notes/today.md")

            self.assertEqual(nested, resolved.path)
            self.assertEqual("notes/today.md", resolved.relative_path)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with self.assertRaises(UnsafePathError):
                resolver.resolve("work", "../outside.txt")

    def test_rejects_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with self.assertRaises(UnsafePathError):
                resolver.resolve("work", "/etc/passwd")

    def test_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as outside_dir:
            root_path = Path(root_dir).resolve()
            outside_file = Path(outside_dir).resolve() / "secret.txt"
            outside_file.write_text("secret", encoding="utf-8")
            (root_path / "escape.txt").symlink_to(outside_file)
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with self.assertRaises(UnsafePathError):
                resolver.resolve("work", "escape.txt")

    def test_reports_unknown_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=Path(temp_dir).resolve()),))

            with self.assertRaises(UnknownRootError):
                resolver.resolve("documents", "")

    def test_reports_missing_path_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=Path(temp_dir).resolve()),))

            with self.assertRaises(FileNotFoundInRootError):
                resolver.resolve("work", "missing.txt")

    def test_returns_file_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            file_path = root_path / "report.txt"
            file_path.write_text("hello", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            metadata = resolver.metadata("work", "report.txt")

            self.assertEqual("work", metadata.root_id)
            self.assertEqual("report.txt", metadata.relative_path)
            self.assertEqual("report.txt", metadata.name)
            self.assertEqual("file", metadata.kind)
            self.assertEqual(5, metadata.size_bytes)

    def test_lists_directory_with_hidden_files_and_folders_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "z-file.txt").write_text("z", encoding="utf-8")
            (root_path / ".hidden").write_text("hidden", encoding="utf-8")
            (root_path / "Folder").mkdir()
            (root_path / "a-file.txt").write_text("a", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            listing = resolver.list_directory("work")

            self.assertEqual(["Folder", ".hidden", "a-file.txt", "z-file.txt"], [entry.name for entry in listing.entries])

    def test_list_directory_can_hide_hidden_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / ".hidden").write_text("hidden", encoding="utf-8")
            (root_path / "visible.txt").write_text("visible", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            listing = resolver.list_directory("work", show_hidden_files=False)

            self.assertEqual(["visible.txt"], [entry.name for entry in listing.entries])

    def test_list_directory_reports_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with patch.object(Path, "iterdir", side_effect=PermissionError):
                with self.assertRaisesRegex(FilesystemError, "Permission denied while listing"):
                    resolver.list_directory("work")

    def test_reads_text_preview_with_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "note.md").write_text("hello world", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            preview = resolver.read_text_preview("work", "note.md", max_bytes=5)

            self.assertEqual("hello", preview.text)
            self.assertEqual(5, preview.bytes_read)
            self.assertTrue(preview.truncated)

    def test_rejects_binary_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "binary.txt").write_bytes(b"hello\x00world")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with self.assertRaises(FilesystemError):
                resolver.read_text_preview("work", "binary.txt", max_bytes=100)

    def test_creates_zip_archive_for_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "report.txt").write_text("hello", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            archive = resolver.create_zip_archive("work", "report.txt")
            try:
                self.assertTrue(archive.path.exists())
                self.assertGreater(archive.size_bytes, 0)
                self.assertEqual("report.txt.zip", archive.path.name)
            finally:
                archive.cleanup_directory.cleanup()

    def test_moves_file_to_trash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as data_home:
            root_path = Path(temp_dir).resolve()
            file_path = root_path / "report.txt"
            file_path.write_text("hello", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with patch.dict(os.environ, {"XDG_DATA_HOME": data_home}):
                metadata = resolver.move_file_to_trash("work", "report.txt")

            trash_file = Path(data_home) / "Trash" / "files" / "report.txt"
            trash_info = Path(data_home) / "Trash" / "info" / "report.txt.trashinfo"
            self.assertEqual("report.txt", metadata.relative_path)
            self.assertFalse(file_path.exists())
            self.assertEqual("hello", trash_file.read_text(encoding="utf-8"))
            self.assertIn("Path=", trash_info.read_text(encoding="utf-8"))

    def test_move_file_to_trash_rejects_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as data_home:
            root_path = Path(temp_dir).resolve()
            (root_path / "folder").mkdir()
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with patch.dict(os.environ, {"XDG_DATA_HOME": data_home}):
                with self.assertRaises(FilesystemError):
                    resolver.move_file_to_trash("work", "folder")

            self.assertTrue((root_path / "folder").exists())

    def test_move_file_to_trash_fails_clearly_when_trash_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            file_path = root_path / "report.txt"
            file_path.write_text("hello", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            with patch.dict(os.environ, {"XDG_DATA_HOME": str(file_path)}):
                with self.assertRaises(TrashUnavailableError):
                    resolver.move_file_to_trash("work", "report.txt")

            self.assertTrue(file_path.exists())

    def test_search_files_matches_case_insensitive_tokens_across_roots(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_root = Path(first_dir).resolve()
            second_root = Path(second_dir).resolve()
            (first_root / "Invoice March.pdf").write_text("a", encoding="utf-8")
            (first_root / "invoice-notes.txt").write_text("b", encoding="utf-8")
            (second_root / "client-INVOICE-final.PDF").write_text("c", encoding="utf-8")
            resolver = FilesystemResolver(
                (
                    RootConfig(id="work", display_name="Work", path=first_root),
                    RootConfig(id="documents", display_name="Documents", path=second_root),
                )
            )

            results = resolver.search_files("invoice pdf", limit=10)

            self.assertEqual(
                [("work", "Invoice March.pdf"), ("documents", "client-INVOICE-final.PDF")],
                [(result.root_id, result.relative_path) for result in results],
            )

    def test_search_files_respects_limit_and_hidden_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / ".invoice.pdf").write_text("hidden", encoding="utf-8")
            (root_path / "invoice-1.pdf").write_text("1", encoding="utf-8")
            (root_path / "invoice-2.pdf").write_text("2", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_files("invoice pdf", limit=1, show_hidden_files=False)

            self.assertEqual(["invoice-1.pdf"], [result.relative_path for result in results])

    def test_search_files_skips_excluded_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / ".git").mkdir()
            (root_path / ".git" / "invoice.pdf").write_text("git", encoding="utf-8")
            (root_path / "venv").mkdir()
            (root_path / "venv" / "invoice.pdf").write_text("venv", encoding="utf-8")
            (root_path / "node_modules").mkdir()
            (root_path / "node_modules" / "invoice.pdf").write_text("node", encoding="utf-8")
            (root_path / ".env").write_text("invoice", encoding="utf-8")
            (root_path / ".env.local").write_text("invoice", encoding="utf-8")
            (root_path / ".useful-invoice.pdf").write_text("hidden useful", encoding="utf-8")
            (root_path / "invoice.pdf").write_text("visible", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_files(
                "invoice",
                limit=10,
                show_hidden_files=True,
                exclude_names=(".git", "venv", "node_modules", ".env", ".env.*"),
            )

            self.assertEqual([".useful-invoice.pdf", "invoice.pdf"], [result.relative_path for result in results])

    def test_search_files_matches_relative_path_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            invoices = root_path / "Invoices"
            invoices.mkdir()
            (invoices / "March.pdf").write_text("1", encoding="utf-8")
            (root_path / "March.pdf").write_text("2", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_files("invoices march", limit=10)

            self.assertEqual(["Invoices/March.pdf"], [result.relative_path for result in results])

    def test_tokenizes_search_query(self) -> None:
        self.assertEqual(("invoice", "pdf"), tokenize_search_query("  Invoice   PDF "))

    def test_search_content_matches_text_and_returns_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "notes.md").write_text(
                "Today we discussed Telegram config and search behavior.",
                encoding="utf-8",
            )
            (root_path / "other.md").write_text("Nothing relevant here.", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_content(
                "telegram config",
                limit=10,
                searchable_extensions=(".md", ".txt"),
                max_file_bytes=1000,
                snippet_chars=80,
            )

            self.assertEqual(["notes.md"], [result.metadata.relative_path for result in results])
            self.assertIn("Telegram config", results[0].snippet)

    def test_search_content_skips_binary_oversized_and_unconfigured_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "binary.txt").write_bytes(b"telegram\x00config")
            (root_path / "large.md").write_text("telegram config", encoding="utf-8")
            (root_path / "image.jpg").write_text("telegram config", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_content(
                "telegram config",
                limit=10,
                searchable_extensions=(".md", ".txt"),
                max_file_bytes=10,
                snippet_chars=80,
            )

            self.assertEqual((), results)

    def test_search_content_handles_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / "notes.md").write_text("no match", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_content(
                "telegram config",
                limit=10,
                searchable_extensions=(".md",),
                max_file_bytes=1000,
                snippet_chars=80,
            )

            self.assertEqual((), results)

    def test_search_content_skips_permission_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            unreadable = root_path / "secret.md"
            unreadable.write_text("telegram config", encoding="utf-8")
            unreadable.chmod(0)
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))
            try:
                results = resolver.search_content(
                    "telegram config",
                    limit=10,
                    searchable_extensions=(".md",),
                    max_file_bytes=1000,
                    snippet_chars=80,
                )
            finally:
                unreadable.chmod(0o600)

            self.assertEqual((), results)

    def test_search_content_skips_excluded_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            (root_path / ".venv").mkdir()
            (root_path / ".venv" / "secret.md").write_text("telegram config", encoding="utf-8")
            (root_path / "venv").mkdir()
            (root_path / "venv" / "secret.md").write_text("telegram config", encoding="utf-8")
            (root_path / ".env").write_text("telegram config", encoding="utf-8")
            (root_path / ".env.local").write_text("telegram config", encoding="utf-8")
            (root_path / ".notes.md").write_text("telegram config hidden note", encoding="utf-8")
            (root_path / "notes.md").write_text("telegram config visible note", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.search_content(
                "telegram config",
                limit=10,
                searchable_extensions=(".env", ".md"),
                max_file_bytes=1000,
                snippet_chars=80,
                show_hidden_files=True,
                exclude_names=(".venv", "venv", ".env", ".env.*"),
            )

            self.assertEqual([".notes.md", "notes.md"], [result.metadata.relative_path for result in results])

    def test_recent_files_returns_newest_files_and_skips_excluded_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            old_file = root_path / "old.txt"
            new_file = root_path / "new.txt"
            env_file = root_path / ".env"
            folder = root_path / "folder"
            folder.mkdir()
            old_file.write_text("old", encoding="utf-8")
            new_file.write_text("new", encoding="utf-8")
            env_file.write_text("secret", encoding="utf-8")
            old_time = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
            new_time = datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()
            os.utime(old_file, (old_time, old_time))
            os.utime(new_file, (new_time, new_time))
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.recent_files(limit=10, show_hidden_files=True, exclude_names=(".env",))

            self.assertEqual(["new.txt", "old.txt"], [result.relative_path for result in results])

    def test_recent_files_skips_explicit_excluded_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir).resolve()
            audit_file = root_path / "data" / "audit.jsonl"
            note_file = root_path / "note.md"
            audit_file.parent.mkdir()
            audit_file.write_text("audit", encoding="utf-8")
            note_file.write_text("note", encoding="utf-8")
            resolver = FilesystemResolver((RootConfig(id="work", display_name="Work", path=root_path),))

            results = resolver.recent_files(limit=10, exclude_paths=(("work", "data/audit.jsonl"),))

            self.assertEqual(["note.md"], [result.relative_path for result in results])


class RootConfigTests(unittest.TestCase):
    def test_config_canonicalizes_root_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            real_root = base_path / "real"
            real_root.mkdir()
            symlink_root = base_path / "link"
            symlink_root.symlink_to(real_root, target_is_directory=True)

            config = _parse_config(_raw_config(symlink_root), base_dir=base_path)

            self.assertIsInstance(config, AppConfig)
            self.assertEqual(real_root.resolve(), config.filesystem.roots[0].path)

    def test_config_rejects_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            with self.assertRaises(ConfigError):
                _parse_config(_raw_config(base_path / "missing"), base_dir=base_path)

    def test_config_rejects_file_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            file_root = base_path / "file.txt"
            file_root.write_text("not a directory", encoding="utf-8")

            with self.assertRaises(ConfigError):
                _parse_config(_raw_config(file_root), base_dir=base_path)

    def test_config_loads_search_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            raw = _raw_config(base_path)
            filesystem = raw["filesystem"]
            assert isinstance(filesystem, dict)
            filesystem["search_result_limit"] = 7
            filesystem["content_search_max_bytes"] = 12345
            filesystem["search_snippet_chars"] = 120
            filesystem["searchable_extensions"] = [".md", ".TXT", ".md"]
            filesystem["search_exclude_names"] = [".git", ".ENV", ".git"]

            config = _parse_config(raw, base_dir=base_path)

            self.assertEqual(7, config.filesystem.search_result_limit)
            self.assertEqual(12345, config.filesystem.content_search_max_bytes)
            self.assertEqual(120, config.filesystem.search_snippet_chars)
            self.assertEqual((".md", ".txt"), config.filesystem.searchable_extensions)
            self.assertEqual((".git", ".ENV"), config.filesystem.search_exclude_names)

    def test_config_defaults_exclude_machine_files_and_do_not_search_env_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)

            config = _parse_config(_raw_config(base_path), base_dir=base_path)

            self.assertNotIn(".env", config.filesystem.searchable_extensions)
            self.assertIn(".git", config.filesystem.search_exclude_names)
            self.assertIn("venv", config.filesystem.search_exclude_names)
            self.assertIn(".env", config.filesystem.search_exclude_names)
            self.assertIn(".env.*", config.filesystem.search_exclude_names)

    def test_config_rejects_invalid_search_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            raw = _raw_config(base_path)
            filesystem = raw["filesystem"]
            assert isinstance(filesystem, dict)
            filesystem["searchable_extensions"] = ["md"]

            with self.assertRaises(ConfigError):
                _parse_config(raw, base_dir=base_path)

    def test_config_rejects_invalid_search_exclude_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            raw = _raw_config(base_path)
            filesystem = raw["filesystem"]
            assert isinstance(filesystem, dict)
            filesystem["search_exclude_names"] = ["cache/files"]

            with self.assertRaises(ConfigError):
                _parse_config(raw, base_dir=base_path)


def _raw_config(root_path: Path) -> dict[str, object]:
    return {
        "telegram": {
            "owner_user_ids": [123],
        },
        "filesystem": {
            "roots": {
                "work": {
                    "display_name": "Work",
                    "path": str(root_path),
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
