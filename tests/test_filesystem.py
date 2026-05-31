from pathlib import Path
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

    def test_tokenizes_search_query(self) -> None:
        self.assertEqual(("invoice", "pdf"), tokenize_search_query("  Invoice   PDF "))


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
