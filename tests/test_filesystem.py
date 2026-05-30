from pathlib import Path
import tempfile
import unittest

from telegram_laptop_files.config import AppConfig, ConfigError, RootConfig, _parse_config
from telegram_laptop_files.filesystem import (
    FileNotFoundInRootError,
    FilesystemResolver,
    UnknownRootError,
    UnsafePathError,
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
