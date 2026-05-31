# tg-filer

A private Telegram bot for browsing allowlisted laptop folders from a phone.

The MVP runs locally on the laptop and uses Telegram long polling, so no public
web server is needed.

## MVP Status

Milestones 1 through 8 are in place, and milestone 9 packaging is in place except reboot validation:

- Project name: `tg-filer`.
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
- `/recent` recently modified files across configured roots.
- `/search <query>` filename/path search across all configured roots.
- `/content <query>` content search inside configured text-like files.
- `/status` runtime health summary for token, proxy, audit log, roots, and limits.
- Case-insensitive multi-token search results with path, size, modified date, snippets for content matches, and selectable buttons.
- Append-only JSONL audit log for auth, browse, preview, download, archive, delete, search, recent, status, startup, and shutdown events.
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
TG_FILER_BOT_TOKEN=your-token-from-botfather
```

If Telegram Bot API access on this laptop needs a local proxy, also set:

```bash
TG_FILER_PROXY=http://127.0.0.1:7897
```

Edit `config.local.yaml` and replace the placeholder Telegram owner ID with
your numeric Telegram user ID.

Check that config loads:

```bash
tg-filer --config config.local.yaml --check-config --require-token
```

For a token-free skeleton check, use the committed example config:

```bash
tg-filer --config config.example.yaml --check-config
```

Start the bot locally:

```bash
tg-filer --config config.local.yaml
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
Use `/search invoice pdf` to search filenames and relative paths across configured roots.
Use `/content meeting notes` to search inside text-like files. Tap a result
number to open its file detail screen. Use `/recent` when you remember roughly
when a file changed, not its name or folder. Use `/status` to check local health
from Telegram. Full controls are available from `/help`.
Search and content results skip configured machine or sensitive names such as
`.git`, `.venv`, `venv`, `node_modules`, `.env`, and `.env.*` by default.

## Config

The example config allowlists these folders:

- `/home/snikmas/work`
- `/home/snikmas/Documents`
- `/home/snikmas/Documents/Obsidian Vault`

The bot token is never stored in YAML. The config names the environment variable
that should contain the token:

```yaml
telegram:
  bot_token_env: TG_FILER_BOT_TOKEN
```

Audit events are written as JSONL to `logging.audit_log_path`. The default is
`./data/audit.jsonl`; the parent directory is created at startup.

Search limits are configured under `filesystem`:

- `search_result_limit`: maximum returned results.
- `content_search_max_bytes`: maximum file size read during content search.
- `search_snippet_chars`: maximum snippet length for content matches.
- `searchable_extensions`: text-like extensions eligible for content search.
- `search_exclude_names`: file or directory names, with optional glob patterns,
  skipped by filename and content search.

`show_hidden_files` still controls whether hidden files are visible while
browsing. Search has the additional `search_exclude_names` filter so noisy
machine folders and secret files do not dominate results. `.env` is excluded
from content search by default because snippets can expose tokens or credentials.

## Systemd

Install the service for the current user:

```bash
mkdir -p ~/.config/tg-filer ~/.config/systemd/user
cp packaging/env.example ~/.config/tg-filer/env
cp packaging/tg-filer.service ~/.config/systemd/user/
```

Edit `~/.config/tg-filer/env` and set the real bot token. If the
repo path or config path is different, edit `WorkingDirectory` and `ExecStart`
inside `~/.config/systemd/user/tg-filer.service`.

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now tg-filer.service
loginctl enable-linger "$USER"
```

Check status and logs:

```bash
systemctl --user status tg-filer.service
journalctl --user -u tg-filer.service -f
```

## Troubleshooting

- Token: run `tg-filer --config config.local.yaml --check-config --require-token`; if it fails, check `.env` or the systemd environment file.
- Network/proxy: if the audit log repeats `polling_network_error` with `TimedOut`, set `TG_FILER_PROXY` in `.env` or `~/.config/tg-filer/env` and restart the bot.
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
.venv/bin/python -m pytest -q
```
