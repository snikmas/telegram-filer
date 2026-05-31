from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when local configuration cannot be loaded safely."""


@dataclass(frozen=True)
class TelegramConfig:
    framework: str
    bot_token_env: str
    owner_user_ids: tuple[int, ...]
    bot_token: str | None


@dataclass(frozen=True)
class RootConfig:
    id: str
    display_name: str
    path: Path


@dataclass(frozen=True)
class FilesystemConfig:
    roots: tuple[RootConfig, ...]
    max_preview_bytes: int
    max_upload_bytes: int
    show_hidden_files: bool
    oversized_file_action: str
    delete_mode: str


@dataclass(frozen=True)
class LoggingConfig:
    audit_log_path: Path


@dataclass(frozen=True)
class AppConfig:
    name: str
    telegram: TelegramConfig
    filesystem: FilesystemConfig
    logging: LoggingConfig


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE lines without overriding existing environment."""
    if not path.exists():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid .env line {line_number}: expected KEY=VALUE")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise ConfigError(f"Invalid .env line {line_number}: empty key")
        os.environ.setdefault(key, value)


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file) or {}

    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")

    return _parse_config(raw, base_dir=config_path.parent)


def _parse_config(raw: dict[str, Any], base_dir: Path) -> AppConfig:
    app_raw = _mapping(raw.get("app", {}), "app")
    telegram_raw = _mapping(raw.get("telegram"), "telegram")
    filesystem_raw = _mapping(raw.get("filesystem"), "filesystem")
    logging_raw = _mapping(raw.get("logging", {}), "logging")

    bot_token_env = _string(telegram_raw.get("bot_token_env", "TG_FILER_BOT_TOKEN"), "telegram.bot_token_env")
    owner_user_ids = _owner_ids(telegram_raw.get("owner_user_ids", []))
    framework = _string(telegram_raw.get("framework", "python-telegram-bot"), "telegram.framework")

    roots = _roots(filesystem_raw.get("roots"))
    max_preview_bytes = _positive_int(filesystem_raw.get("max_preview_bytes", 12000), "filesystem.max_preview_bytes")
    max_upload_bytes = _positive_int(filesystem_raw.get("max_upload_bytes", 45000000), "filesystem.max_upload_bytes")

    audit_log_path = _path(logging_raw.get("audit_log_path", "./data/audit.jsonl"), "logging.audit_log_path")
    if not audit_log_path.is_absolute():
        audit_log_path = (base_dir / audit_log_path).resolve()

    return AppConfig(
        name=_string(app_raw.get("name", "tg-filer"), "app.name"),
        telegram=TelegramConfig(
            framework=framework,
            bot_token_env=bot_token_env,
            owner_user_ids=owner_user_ids,
            bot_token=os.environ.get(bot_token_env) or None,
        ),
        filesystem=FilesystemConfig(
            roots=roots,
            max_preview_bytes=max_preview_bytes,
            max_upload_bytes=max_upload_bytes,
            show_hidden_files=bool(filesystem_raw.get("show_hidden_files", True)),
            oversized_file_action=_string(
                filesystem_raw.get("oversized_file_action", "metadata_and_compress"),
                "filesystem.oversized_file_action",
            ),
            delete_mode=_string(filesystem_raw.get("delete_mode", "trash"), "filesystem.delete_mode"),
        ),
        logging=LoggingConfig(audit_log_path=audit_log_path),
    )


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _path(value: Any, name: str) -> Path:
    return Path(_string(value, name)).expanduser()


def _owner_ids(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("telegram.owner_user_ids must be a non-empty list")

    owner_ids: list[int] = []
    for index, user_id in enumerate(value):
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ConfigError(f"telegram.owner_user_ids[{index}] must be a positive integer")
        owner_ids.append(user_id)
    return tuple(owner_ids)


def _roots(value: Any) -> tuple[RootConfig, ...]:
    roots_raw = _mapping(value, "filesystem.roots")
    if not roots_raw:
        raise ConfigError("filesystem.roots must define at least one root")

    roots: list[RootConfig] = []
    seen_ids: set[str] = set()
    for root_id, root_value in roots_raw.items():
        root_id = _string(root_id, "filesystem.roots key")
        if root_id in seen_ids:
            raise ConfigError(f"Duplicate filesystem root id: {root_id}")
        seen_ids.add(root_id)

        if isinstance(root_value, str):
            display_name = root_id.replace("_", " ").title()
            path = Path(root_value).expanduser()
        else:
            root_raw = _mapping(root_value, f"filesystem.roots.{root_id}")
            display_name = _string(root_raw.get("display_name", root_id), f"filesystem.roots.{root_id}.display_name")
            path = _path(root_raw.get("path"), f"filesystem.roots.{root_id}.path")

        if not path.is_absolute():
            raise ConfigError(f"filesystem.roots.{root_id}.path must be absolute")
        path = _canonical_root_path(path, f"filesystem.roots.{root_id}.path")
        roots.append(RootConfig(id=root_id, display_name=display_name, path=path))

    return tuple(roots)


def _canonical_root_path(path: Path, name: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ConfigError(f"{name} does not exist: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"{name} cannot be resolved: {path}") from exc

    if not resolved.is_dir():
        raise ConfigError(f"{name} must be a directory: {path}")
    return resolved
