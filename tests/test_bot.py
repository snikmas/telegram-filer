from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
import unittest.mock

from telegram_laptop_files.bot import (
    CALLBACK_PREFIX,
    CallbackAction,
    CallbackActionStore,
    _content_search_results_keyboard,
    PendingDeleteStore,
    _audit_log_exclude_paths,
    _clear_browser_session,
    _delete_confirmation_keyboard,
    _file_detail_keyboard,
    _search_results_keyboard,
    _named_entry_matches,
    _format_session_path,
    _polling_retry_delay,
    _root_match,
    _selector_index,
    _visible_directory_entries,
    _telegram_proxy_from_environment,
    format_delete_confirmation_message,
    format_content_search_results_message,
    format_directory_message,
    format_file_detail_message,
    format_help_message,
    format_preview_message,
    format_recent_files_message,
    format_roots_message,
    format_search_results_message,
    format_status_message,
    format_size,
    is_authorized_user_id,
    is_previewable_file,
)
from telegram_laptop_files.config import AppConfig, FilesystemConfig, LoggingConfig, RootConfig, TelegramConfig
from telegram_laptop_files.filesystem import ContentSearchResult, FileMetadata, TextPreview


class BotCommandHelperTests(unittest.TestCase):
    def test_owner_allowlist_accepts_configured_user(self) -> None:
        self.assertTrue(is_authorized_user_id(123, (123, 456)))
        self.assertFalse(is_authorized_user_id(789, (123, 456)))
        self.assertFalse(is_authorized_user_id(None, (123, 456)))

    def test_roots_message_escapes_html(self) -> None:
        roots = (
            RootConfig(id="notes", display_name="Notes <private>", path=Path("/tmp/Notes & Docs")),
        )

        message = format_roots_message(roots)

        self.assertIn("roots", message)
        self.assertIn("<code>1)</code>", message)
        self.assertIn("Notes &lt;private&gt;", message)
        self.assertNotIn("notes", message)
        self.assertNotIn("/tmp/Notes", message)

    def test_help_message_lists_milestone_two_commands(self) -> None:
        message = format_help_message()

        for command in (
            "/start",
            "/roots",
            "/recent",
            "/search &lt;query&gt;",
            "/content &lt;query&gt;",
            "/status",
            "/help",
            "/cancel",
        ):
            self.assertIn(command, message)
        self.assertNotIn("<query>", message)
        self.assertIn("unique 3+ character prefix", message)

    def test_root_match_accepts_display_name_prefix(self) -> None:
        roots = (
            RootConfig(id="work", display_name="Work", path=Path("/tmp/work")),
            RootConfig(id="obsidian", display_name="Obsidian Vault", path=Path("/tmp/obsidian")),
        )

        self.assertEqual("work", _root_match(roots, "1").id)
        self.assertEqual("work", _root_match(roots, "1)").id)
        self.assertEqual("work", _root_match(roots, "/Wor").id)
        self.assertEqual("obsidian", _root_match(roots, "/Obsidian").id)
        self.assertIsNone(_root_match(roots, "/Wo"))
        self.assertIsNone(_root_match(roots, "/missing"))

    def test_polling_retry_delay_backs_off_with_cap(self) -> None:
        self.assertEqual(5, _polling_retry_delay(1))
        self.assertEqual(10, _polling_retry_delay(2))
        self.assertEqual(60, _polling_retry_delay(99))

    def test_telegram_proxy_prefers_app_specific_environment(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ",
            {
                "TG_FILER_PROXY": " socks5://127.0.0.1:7897 ",
                "https_proxy": "http://127.0.0.1:7897",
            },
            clear=True,
        ):
            self.assertEqual("socks5://127.0.0.1:7897", _telegram_proxy_from_environment())

    def test_telegram_proxy_falls_back_to_shell_proxy_environment(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ",
            {"https_proxy": "http://127.0.0.1:7897"},
            clear=True,
        ):
            self.assertEqual("http://127.0.0.1:7897", _telegram_proxy_from_environment())

    def test_selector_index_accepts_menu_number_format(self) -> None:
        self.assertEqual(0, _selector_index("1"))
        self.assertEqual(0, _selector_index("1)"))
        self.assertEqual(1, _selector_index(" 2) "))
        self.assertIsNone(_selector_index("two"))

    def test_clear_browser_session_preserves_pending_delete_tokens(self) -> None:
        context = _FakeContext(
            user_data={
                "browser_session": object(),
                "pending_delete_tokens": ["token"],
                "pending_delete_token": "token",
            }
        )

        _clear_browser_session(context)

        self.assertNotIn("browser_session", context.user_data)
        self.assertEqual(["token"], context.user_data["pending_delete_tokens"])

    def test_callback_action_store_uses_short_lookup_tokens(self) -> None:
        store = CallbackActionStore()
        action = CallbackAction(kind="preview", root_id="work", relative_path="notes/today.md", page=2)

        callback_data = store.put(action)

        self.assertTrue(callback_data.startswith(CALLBACK_PREFIX))
        self.assertLessEqual(len(callback_data), 64)
        self.assertEqual(action, store.get(callback_data))
        self.assertIsNone(store.get("unknown"))

    def test_pending_delete_store_expires_and_consumes_actions(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        store = PendingDeleteStore(ttl=timedelta(minutes=5))

        token, action = store.put("work", "notes/today.md", now=now)

        self.assertEqual("notes/today.md", action.relative_path)
        self.assertIsNotNone(store.get(token, now=now + timedelta(minutes=4)))
        self.assertIsNone(store.pop(token, now=now + timedelta(minutes=6)))
        self.assertIsNone(store.get(token, now=now + timedelta(minutes=6)))

    def test_pending_delete_store_pop_consumes_valid_action(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        store = PendingDeleteStore(ttl=timedelta(minutes=5))
        token, _ = store.put("work", "notes/today.md", now=now)

        self.assertIsNotNone(store.pop(token, now=now + timedelta(minutes=1)))
        self.assertIsNone(store.pop(token, now=now + timedelta(minutes=1)))

    def test_previewable_file_extensions_include_markdown(self) -> None:
        self.assertTrue(is_previewable_file("note.MD"))
        self.assertTrue(is_previewable_file(".env"))
        self.assertFalse(is_previewable_file("photo.jpg"))

    def test_file_detail_shows_oversized_archive_guidance(self) -> None:
        metadata = FileMetadata(
            root_id="work",
            relative_path="large.bin",
            name="large.bin",
            kind="file",
            size_bytes=50_000_000,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        message = format_file_detail_message(metadata, max_upload_bytes=45_000_000)

        self.assertIn("larger than the upload limit", message)
        self.assertIn("compressed archive", message)
        self.assertNotIn("Type:", message)

    def test_delete_confirmation_message_includes_trash_and_expiration(self) -> None:
        metadata = FileMetadata(
            root_id="work",
            relative_path="notes/today.md",
            name="today.md",
            kind="file",
            size_bytes=8,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        message = format_delete_confirmation_message(metadata, datetime(2026, 1, 2, 1, tzinfo=timezone.utc))

        self.assertIn("Confirm delete", message)
        self.assertIn("move the file to trash", message)
        self.assertIn("Expires:", message)

    def test_file_detail_keyboard_includes_delete_for_files(self) -> None:
        store = CallbackActionStore()
        metadata = FileMetadata(
            root_id="work",
            relative_path="notes/today.md",
            name="today.md",
            kind="file",
            size_bytes=8,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        keyboard = _file_detail_keyboard(metadata, store, max_upload_bytes=45_000_000)

        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("Delete", button_texts)

    def test_delete_confirmation_keyboard_has_confirm_and_cancel(self) -> None:
        store = CallbackActionStore()
        metadata = FileMetadata(
            root_id="work",
            relative_path="notes/today.md",
            name="today.md",
            kind="file",
            size_bytes=8,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        keyboard = _delete_confirmation_keyboard(metadata, "pending-token", store)

        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("Confirm delete", button_texts)
        self.assertIn("Cancel", button_texts)

    def test_preview_message_escapes_html(self) -> None:
        metadata = FileMetadata(
            root_id="work",
            relative_path="notes/today.md",
            name="today.md",
            kind="file",
            size_bytes=8,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        preview = TextPreview(text="<secret>&done", bytes_read=13, truncated=True)

        message = format_preview_message(metadata, preview)

        self.assertIn("&lt;secret&gt;&amp;done", message)
        self.assertIn("file continues beyond preview limit", message)

    def test_search_results_message_includes_path_size_and_modified_date(self) -> None:
        metadata = FileMetadata(
            root_id="work",
            relative_path="invoices/Invoice March.pdf",
            name="Invoice March.pdf",
            kind="file",
            size_bytes=2048,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        message = format_search_results_message("invoice pdf", (metadata,), limit=20)

        self.assertIn("Invoice March.pdf", message)
        self.assertIn("<code>1)</code>", message)
        self.assertIn("work:/invoices/Invoice March.pdf", message)
        self.assertIn("2.0 KB", message)
        self.assertIn("2026-01-02", message)

    def test_search_results_message_handles_empty_results(self) -> None:
        message = format_search_results_message("missing", (), limit=20)

        self.assertIn("No matching files", message)

    def test_search_results_keyboard_makes_each_result_selectable(self) -> None:
        store = CallbackActionStore()
        results = tuple(
            FileMetadata(
                root_id="work",
                relative_path=f"file-{index}.txt",
                name=f"file-{index}.txt",
                kind="file",
                size_bytes=1,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
            for index in range(3)
        )

        keyboard = _search_results_keyboard(results, store)

        self.assertIsNotNone(keyboard)
        assert keyboard is not None
        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(["1", "2", "3"], button_texts)

    def test_content_search_results_message_includes_snippet(self) -> None:
        result = ContentSearchResult(
            metadata=FileMetadata(
                root_id="work",
                relative_path="notes/today.md",
                name="today.md",
                kind="file",
                size_bytes=1024,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            snippet="Discussed Telegram config and content search.",
        )

        message = format_content_search_results_message("telegram config", (result,), limit=10)

        self.assertIn("Content search results", message)
        self.assertIn("work:/notes/today.md", message)
        self.assertIn("Discussed Telegram config", message)

    def test_content_search_results_keyboard_makes_each_result_selectable(self) -> None:
        store = CallbackActionStore()
        results = tuple(
            ContentSearchResult(
                metadata=FileMetadata(
                    root_id="work",
                    relative_path=f"file-{index}.md",
                    name=f"file-{index}.md",
                    kind="file",
                    size_bytes=1,
                    modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
                snippet="telegram config",
            )
            for index in range(3)
        )

        keyboard = _content_search_results_keyboard(results, store)

        self.assertIsNotNone(keyboard)
        assert keyboard is not None
        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(["1", "2", "3"], button_texts)

    def test_recent_files_message_uses_search_result_shape(self) -> None:
        metadata = FileMetadata(
            root_id="work",
            relative_path="notes/today.md",
            name="today.md",
            kind="file",
            size_bytes=1024,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        message = format_recent_files_message((metadata,), limit=10)

        self.assertIn("Recent files", message)
        self.assertIn("<code>1)</code>", message)
        self.assertIn("work:/notes/today.md", message)
        self.assertIn("2026-01-02", message)

    def test_status_message_summarizes_runtime_health_without_secrets(self) -> None:
        config = AppConfig(
            name="tg-filer",
            telegram=TelegramConfig(
                framework="python-telegram-bot",
                bot_token_env="TG_FILER_BOT_TOKEN",
                owner_user_ids=(123,),
                bot_token="secret-token",
            ),
            filesystem=FilesystemConfig(
                roots=(RootConfig(id="work", display_name="Work", path=Path("/tmp/work")),),
                max_preview_bytes=12000,
                max_upload_bytes=45_000_000,
                show_hidden_files=True,
                oversized_file_action="metadata_and_compress",
                delete_mode="trash",
                search_result_limit=10,
                content_search_max_bytes=250_000,
                search_snippet_chars=160,
                searchable_extensions=(".md",),
                search_exclude_names=(".git",),
            ),
            logging=LoggingConfig(audit_log_path=Path("/tmp/audit.jsonl")),
        )

        message = format_status_message(
            config,
            audit_writable=True,
            proxy_configured=False,
            session_path="work:/notes",
        )

        self.assertIn("tg-filer status", message)
        self.assertIn("Token: set", message)
        self.assertIn("Proxy: not configured", message)
        self.assertIn("Audit log: writable", message)
        self.assertIn("Session: <code>work:/notes</code>", message)
        self.assertNotIn("secret-token", message)

    def test_format_session_path_handles_root_and_nested_paths(self) -> None:
        self.assertEqual("work:/", _format_session_path("work", ""))
        self.assertEqual("work:/notes/today.md", _format_session_path("work", "notes/today.md"))

    def test_audit_log_exclude_paths_maps_audit_path_under_roots(self) -> None:
        config = AppConfig(
            name="tg-filer",
            telegram=TelegramConfig(
                framework="python-telegram-bot",
                bot_token_env="TG_FILER_BOT_TOKEN",
                owner_user_ids=(123,),
                bot_token="secret-token",
            ),
            filesystem=FilesystemConfig(
                roots=(RootConfig(id="work", display_name="Work", path=Path("/tmp/work")),),
                max_preview_bytes=12000,
                max_upload_bytes=45_000_000,
                show_hidden_files=True,
                oversized_file_action="metadata_and_compress",
                delete_mode="trash",
                search_result_limit=10,
                content_search_max_bytes=250_000,
                search_snippet_chars=160,
                searchable_extensions=(".md",),
                search_exclude_names=(".git",),
            ),
            logging=LoggingConfig(audit_log_path=Path("/tmp/work/data/audit.jsonl")),
        )

        self.assertEqual((("work", "data/audit.jsonl"),), _audit_log_exclude_paths(config))

    def test_format_size_uses_human_units(self) -> None:
        self.assertEqual("42 B", format_size(42))
        self.assertEqual("2.0 KB", format_size(2048))

    def test_directory_message_is_quiet_without_inline_hints(self) -> None:
        directory = FileMetadata(
            root_id="work",
            relative_path="projects",
            name="projects",
            kind="directory",
            size_bytes=0,
            modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        entries = (
            FileMetadata(
                root_id="work",
                relative_path="projects/app",
                name="app",
                kind="directory",
                size_bytes=0,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            FileMetadata(
                root_id="work",
                relative_path="projects/README.md",
                name="README.md",
                kind="file",
                size_bytes=2048,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        )

        message = format_directory_message(directory, entries, entries, page=0, total_pages=1)

        self.assertIn("work:/projects", message)
        self.assertIn("1 dirs", message)
        self.assertIn("1 files", message)
        self.assertIn("<code>1)</code> <code>app/</code>", message)
        self.assertIn("<code>2)</code> <code>README.md</code>  2.0 KB", message)
        self.assertIn("app/", message)
        self.assertIn("README.md", message)
        self.assertNotIn("cd 1", message)
        self.assertNotIn("filter", message)
        self.assertNotIn("next", message)

    def test_directory_pages_are_smaller_for_mobile(self) -> None:
        entries = tuple(
            FileMetadata(
                root_id="work",
                relative_path=f"file-{index}.txt",
                name=f"file-{index}.txt",
                kind="file",
                size_bytes=1,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
            for index in range(10)
        )

        visible_entries, page, total_pages = _visible_directory_entries(entries, page=0)

        self.assertEqual(8, len(visible_entries))
        self.assertEqual(0, page)
        self.assertEqual(2, total_pages)

    def test_named_entry_matches_three_character_prefix_and_reports_ambiguity(self) -> None:
        entries = (
            FileMetadata(
                root_id="work",
                relative_path="Screenshots 2026",
                name="Screenshots 2026",
                kind="directory",
                size_bytes=0,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            FileMetadata(
                root_id="work",
                relative_path="Scripts",
                name="Scripts",
                kind="directory",
                size_bytes=0,
                modified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        )

        self.assertEqual(
            ("Screenshots 2026",),
            tuple(entry.name for entry in _named_entry_matches(entries, "Screen", dirs_only=True, files_only=False)),
        )
        self.assertEqual(
            (),
            tuple(entry.name for entry in _named_entry_matches(entries, "Sc", dirs_only=True, files_only=False)),
        )
        self.assertEqual(
            ("Screenshots 2026", "Scripts"),
            tuple(entry.name for entry in _named_entry_matches(entries, "Scr", dirs_only=True, files_only=False)),
        )

class _FakeContext:
    def __init__(self, user_data: dict[str, object]) -> None:
        self.user_data = user_data


if __name__ == "__main__":
    unittest.main()
