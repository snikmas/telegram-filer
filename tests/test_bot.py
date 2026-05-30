from pathlib import Path
import unittest

from telegram_laptop_files.bot import format_help_message, format_roots_message, is_authorized_user_id
from telegram_laptop_files.config import RootConfig


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

        self.assertIn("Configured root folders", message)
        self.assertIn("Notes &lt;private&gt;", message)
        self.assertIn("/tmp/Notes &amp; Docs", message)

    def test_help_message_lists_milestone_two_commands(self) -> None:
        message = format_help_message()

        for command in ("/start", "/roots", "/help", "/cancel"):
            self.assertIn(command, message)


if __name__ == "__main__":
    unittest.main()
