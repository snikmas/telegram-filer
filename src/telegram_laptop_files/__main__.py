from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from .bot import run_bot
from .config import AppConfig, ConfigError, load_config, load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram Laptop Files local bot")
    parser.add_argument(
        "--config",
        default="config.example.yaml",
        type=Path,
        help="Path to YAML config file. Defaults to config.example.yaml.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        type=Path,
        help="Path to local env file. Defaults to .env when present.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Load config, print a summary, and exit without starting Telegram polling.",
    )
    parser.add_argument(
        "--require-token",
        action="store_true",
        help="Fail if the configured bot token environment variable is not set.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)

    try:
        load_dotenv(args.env_file)
        config = load_config(args.config)
        if (args.require_token or not args.check_config) and not config.telegram.bot_token:
            raise ConfigError(f"Missing bot token environment variable: {config.telegram.bot_token_env}")
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    print(_format_summary(config))
    if args.check_config:
        return 0

    print("")
    print("Starting Telegram polling. Press Ctrl+C to stop.")
    try:
        run_bot(config)
    except (RuntimeError, ValueError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("")
        print("Stopped.")
    return 0


def _format_summary(config: AppConfig) -> str:
    lines = [
        f"{config.name}",
        f"Framework: {config.telegram.framework}",
        f"Owner IDs configured: {len(config.telegram.owner_user_ids)}",
        f"Bot token env: {config.telegram.bot_token_env} ({'set' if config.telegram.bot_token else 'not set'})",
        f"Max preview bytes: {config.filesystem.max_preview_bytes}",
        f"Max upload bytes: {config.filesystem.max_upload_bytes}",
        f"Audit log path: {config.logging.audit_log_path}",
        "Roots:",
    ]
    for root in config.filesystem.roots:
        lines.append(f"  - {root.id}: {root.display_name} -> {root.path}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
