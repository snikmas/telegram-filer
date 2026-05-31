# tg-filer

Private Telegram file browser for your laptop.

`tg-filer` lets you open selected laptop folders from your phone, find files,
preview text, download files, compress oversized files, and move files to trash
without exposing your whole machine.

It runs as a local process on the laptop and talks to Telegram with long
polling. There is no public web server and no inbound port to open.

```text
Phone -> Telegram Bot API -> tg-filer on your laptop -> allowlisted folders
```

## What You Can Do

- Browse configured folders from Telegram.
- Use a compact shell-style chat UI that works comfortably on a phone.
- Open file detail screens with size, path, and modified time.
- Preview common text files, including Markdown, JSON, YAML, logs, and Python.
- Download files directly when they fit Telegram's upload limit.
- Create and download a compressed archive for oversized files.
- Search by filename or path with `/search <query>`.
- Search inside text-like files with `/content <query>`.
- Show recently modified files with `/recent`.
- Check bot health and limits with `/status`.
- Move files to trash only after an explicit confirmation.
- Keep an append-only JSONL audit log of bot actions.

## Safety Model

`tg-filer` is designed for personal, owner-only use.

- Only Telegram user IDs listed in the config can use the bot.
- Every file operation is limited to configured root folders.
- Path traversal and symlink escapes are rejected.
- Folder deletion is disabled.
- File deletion moves files to trash and requires confirmation.
- Bot tokens are read from environment variables, not YAML config.
- Search skips noisy or sensitive names such as `.git`, `.venv`,
  `node_modules`, `.env`, and `.env.*` by default.
- Audit logs record actions and paths, not file contents.

## Telegram Commands

| Command | Purpose |
| --- | --- |
| `/start` | Show bot status and configured roots. |
| `/roots` | Show configured root folders. |
| `/recent` | Show recently modified files. |
| `/search invoice pdf` | Find files by filename or relative path. |
| `/content meeting notes` | Search inside configured text-like files. |
| `/status` | Show token, proxy, audit log, root, and limit health. |
| `/help` | Show controls inside Telegram. |
| `/cancel` | Cancel pending actions and clear the current session. |

Navigation is intentionally simple:

- Send `1`, `2`, `3`, etc. to open a listed root or item.
- Send `/folder-name` to enter a folder by exact name or unique 3+ character
  prefix.
- Send `/..` to go to the parent folder.
- Send `/` to return to the selected root.
- Use file detail buttons for preview, download, zip, delete, and back.

## Showcase Flow

A typical phone workflow looks like this:

1. Send `/start` and choose a configured root.
2. Browse folders with numbers or `/folder-prefix`.
3. Open a file detail screen.
4. Preview a text file or download the file to the phone.
5. Use `/search tax receipt` when you remember the filename.
6. Use `/content project deadline` when you remember text inside a note.
7. Use `/recent` when you only remember that the file changed recently.

The bot is most useful for personal notes, documents, project folders, logs, and
other laptop files that you occasionally need while away from the keyboard.

## Quickstart

Requirements:

- Python 3.11 or newer.
- A Telegram bot token from BotFather.
- Your numeric Telegram user ID.

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

Edit `.env` and set your bot token:

```bash
TG_FILER_BOT_TOKEN=your-token-from-botfather
```

If this laptop needs a local proxy to reach Telegram, also set:

```bash
TG_FILER_PROXY=http://127.0.0.1:7897
```

Edit `config.local.yaml`:

- Replace the placeholder `telegram.owner_user_ids` value with your numeric
  Telegram user ID.
- Replace `filesystem.roots` with the folders you want to expose.
- Keep root paths absolute.

Check the config before starting the bot:

```bash
tg-filer --config config.local.yaml --check-config --require-token
```

Start locally:

```bash
tg-filer --config config.local.yaml
```

Or use the local helper script:

```bash
scripts/run-local.sh
```

Open Telegram and send `/start` to your bot.

## Config Guide

The example config allowlists three folders:

```yaml
filesystem:
  roots:
    work:
      display_name: Work
      path: /home/snikmas/work
    documents:
      display_name: Documents
      path: /home/snikmas/Documents
    obsidian:
      display_name: Obsidian
      path: /home/snikmas/Documents/Obsidian Vault
```

The bot token is referenced by environment variable name:

```yaml
telegram:
  bot_token_env: TG_FILER_BOT_TOKEN
```

Useful filesystem settings:

| Setting | Purpose |
| --- | --- |
| `max_preview_bytes` | Maximum bytes read for text previews. |
| `max_upload_bytes` | Maximum file size sent directly to Telegram. |
| `search_result_limit` | Maximum search/recent results returned. |
| `content_search_max_bytes` | Maximum file size read during content search. |
| `search_snippet_chars` | Maximum snippet length for content matches. |
| `searchable_extensions` | File extensions eligible for content search. |
| `search_exclude_names` | Names or glob patterns skipped by search. |
| `show_hidden_files` | Whether hidden files appear while browsing. |
| `delete_mode` | Current MVP mode is `trash`. |

Audit events are written as JSONL to `logging.audit_log_path`. The default is
`./data/audit.jsonl`; the parent directory is created at startup.

## Run With Systemd

Install the user service template:

```bash
mkdir -p ~/.config/tg-filer ~/.config/systemd/user
cp packaging/env.example ~/.config/tg-filer/env
cp packaging/tg-filer.service ~/.config/systemd/user/
```

Edit `~/.config/tg-filer/env` and set the real bot token. If your checkout or
config path is different, edit `WorkingDirectory` and `ExecStart` inside
`~/.config/systemd/user/tg-filer.service`.

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

| Problem | What to check |
| --- | --- |
| Bot will not start | Run `tg-filer --config config.local.yaml --check-config --require-token`. |
| Token error | Check `.env` or `~/.config/tg-filer/env` and the `bot_token_env` config key. |
| Telegram timeout | Set `TG_FILER_PROXY` if this laptop needs a proxy. |
| Access denied | Make sure `telegram.owner_user_ids` contains your numeric Telegram user ID. |
| Root config error | Root paths must be absolute existing directories. |
| File cannot open | Permissions, traversal attempts, and symlink escapes are rejected. |
| Audit log error | Check `logging.audit_log_path` and parent directory permissions. |

## Development

Run a token-free config check with the committed example config:

```bash
PYTHONPATH=src python -m telegram_laptop_files --config config.example.yaml --check-config
```

Run tests:

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

Project docs:

- `PRODUCT.md` explains product scope and non-goals.
- `ARCHITECTURE.md` explains the local polling architecture and safety rules.
- `CHANGELOG.md` records notable changes.

## Status

The current version is a usable personal MVP for owner-only laptop file access
through Telegram. It is intended for a single trusted owner, not shared hosting
or multi-user permission management.
