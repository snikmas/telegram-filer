# Telegram Laptop Files

A private Telegram bot for browsing allowlisted laptop folders from a phone.

The MVP runs locally on the laptop and uses Telegram long polling, so no public
web server is needed.

## MVP Status

Milestones 1 through 8 are in place, and milestone 9 packaging is in place except reboot validation:

- Project name: `telegram-laptop-files`.
- Python package: `telegram_laptop_files`.
- Telegram framework choice: `python-telegram-bot`.
- Config format: YAML.
- Local secrets: `.env`, ignored by git.
- Telegram long polling startup.
- Owner Telegram user ID allowlist.
- `/start`, `/roots`, `/help`, and `/cancel`.
- Canonical allowlisted filesystem roots.
- Shared safe path resolver for future file actions.
- Path traversal and symlink-escape protection.
- File and folder metadata helper.
- Compact typed root and folder browsing.
- Hidden-file display inside allowlisted roots.
- Folder-first sorting, parent navigation, pagination, and empty-folder handling.
- File detail screens with metadata and compact action buttons.
- Text preview for common text formats, including Markdown notes.
- Direct file download under the configured upload limit.
- Oversized-file metadata plus compressed archive creation and upload when the archive fits.
- Expiring delete confirmation that moves files to the user's trash.
- Folder deletion remains disabled for the MVP.
- `/search <query>` filename search across all configured roots.
- Case-insensitive multi-token search results with path, size, modified date, and selectable buttons.
- Append-only JSONL audit log for auth, browse, preview, download, archive, delete, search, startup, and shutdown events.
- Startup validation for config, token, root paths, and audit log writability.
- Local run script plus user-level systemd service template.

## Quickstart

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Create local config and env files:

```bash
cp config.example.yaml config.local.yaml
cp .env.example .env
```

Edit `.env` and set:

```bash
TELEGRAM_FILE_BOT_TOKEN=your-token-from-botfather
```

Edit `config.local.yaml` and replace the placeholder Telegram owner ID with
your numeric Telegram user ID.

Check that config loads:

```bash
telegram-laptop-files --config config.local.yaml --check-config --require-token
```

For a token-free skeleton check, use the committed example config:

```bash
telegram-laptop-files --config config.example.yaml --check-config
```

Start the bot locally:

```bash
telegram-laptop-files --config config.local.yaml
```

Or use the local run script:

```bash
scripts/run-local.sh
```

Only Telegram users listed in `telegram.owner_user_ids` can use the bot. Other
users receive an access-denied response and no folder details.

Use `/start` or `/roots` in Telegram, then send a listed number or `/root-name`
to choose a root. Inside a folder, send a listed number to open that item or
`/folder-name` to enter a folder by exact name or unique 3+ character prefix. File detail
screens show compact buttons for preview, download, compression, delete confirmation, and back navigation.
Use `/search invoice pdf` to search filenames across configured roots and tap a result
number to open its file detail screen. Full controls are available from `/help`.

## Config

The example config allowlists these folders:

- `/home/snikmas/work`
- `/home/snikmas/Documents`
- `/home/snikmas/Documents/Obsidian Vault`

The bot token is never stored in YAML. The config names the environment variable
that should contain the token:

```yaml
telegram:
  bot_token_env: TELEGRAM_FILE_BOT_TOKEN
```

Audit events are written as JSONL to `logging.audit_log_path`. The default is
`./data/audit.jsonl`; the parent directory is created at startup.

## Systemd

Install the service for the current user:

```bash
mkdir -p ~/.config/telegram-laptop-files ~/.config/systemd/user
cp packaging/env.example ~/.config/telegram-laptop-files/env
cp packaging/telegram-laptop-files.service ~/.config/systemd/user/
```

Edit `~/.config/telegram-laptop-files/env` and set the real bot token. If the
repo path or config path is different, edit `WorkingDirectory` and `ExecStart`
inside `~/.config/systemd/user/telegram-laptop-files.service`.

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now telegram-laptop-files.service
loginctl enable-linger "$USER"
```

Check status and logs:

```bash
systemctl --user status telegram-laptop-files.service
journalctl --user -u telegram-laptop-files.service -f
```

## Troubleshooting

- Token: run `telegram-laptop-files --config config.local.yaml --check-config --require-token`; if it fails, check `.env` or the systemd environment file.
- Auth: make sure `telegram.owner_user_ids` contains your numeric Telegram user ID.
- Config: root paths must be absolute existing directories.
- Filesystem: path traversal and symlink escapes are rejected; permission errors are reported without permanently deleting files.
- Audit: if startup reports audit log writability problems, check `logging.audit_log_path` and parent directory permissions.

## Development

Run the module directly during development:

```bash
PYTHONPATH=src python -m telegram_laptop_files --config config.example.yaml --check-config
```

Run the tests:

```bash
.venv/bin/python -m pip install pytest
.venv/bin/pytest -q
```
