from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def validate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8"):
            pass

    def record(self, action: str, **fields: Any) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **{key: value for key, value in fields.items() if value is not None},
        }
        try:
            self.validate()
            with self.path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            logger.exception("Failed to write audit log event action=%s path=%s", action, self.path)
