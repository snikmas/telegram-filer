from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from telegram_laptop_files.audit import AuditLog


class AuditLogTests(unittest.TestCase):
    def test_records_append_only_jsonl_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "logs" / "audit.jsonl"
            audit_log = AuditLog(audit_path)

            audit_log.record("browse", status="ok", user_id=123, root_id="work")
            audit_log.record("preview", status="error", error_type="FilesystemError")

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(lines))
            first_event = json.loads(lines[0])
            second_event = json.loads(lines[1])
            self.assertEqual("browse", first_event["action"])
            self.assertEqual("ok", first_event["status"])
            self.assertEqual(123, first_event["user_id"])
            self.assertIn("timestamp", first_event)
            self.assertEqual("preview", second_event["action"])
            self.assertEqual("FilesystemError", second_event["error_type"])

    def test_validate_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "data" / "audit.jsonl"

            AuditLog(audit_path).validate()

            self.assertTrue(audit_path.exists())


if __name__ == "__main__":
    unittest.main()
