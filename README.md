# tg-filer

Private Telegram file browser for your laptop.

`tg-filer` runs locally on your computer and lets you browse selected folders
from Telegram. It is built for personal, owner-only access: find a file, preview
it, download it, archive it if it is too large, or move it to trash after
confirmation.

```text
Phone -> Telegram Bot API -> tg-filer -> allowlisted laptop folders
```

## Features

- Owner-only Telegram access.
- Allowlisted root folders only.
- Shell-style mobile navigation with numbered lists and folder prefixes.
- Text previews for Markdown, logs, config files, Python, JSON, YAML, and more.
- Direct downloads for normal files.
- Zip archive download for oversized files.
- Filename/path search with `/search <query>`.
- Text content search with `/content <query>`.
- Recent-file lookup with `/recent`.
- Runtime health check with `/status`.
- Delete-to-trash with confirmation.
- JSONL audit logging.

## Safety

- No public web server.
- No inbound port required.
- Bot tokens are read from environment variables.
- Path traversal and symlink escapes are rejected.
- Folder deletion is disabled.
- Search skips common machine and secret paths by default.
- Audit logs do not store file contents.

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Open the bot and show roots. |
| `/roots` | List configured root folders. |
| `/recent` | Show recently modified files. |
| `/search invoice pdf` | Search filenames and paths. |
| `/content meeting notes` | Search inside text files. |
| `/status` | Show bot health and limits. |
| `/help` | Show controls. |
| `/cancel` | Cancel the current action. |

Navigation:

- Send `1`, `2`, `3`, etc. to open a listed item.
- Send `/folder-name` to enter a folder by exact name or unique 3+ character
  prefix.
- Send `/..` to go up.
- Send `/` to return to the selected root.
- Use file buttons for preview, download, zip, delete, and back.

## Quickstart

Requirements:

- Python 3.11+
- Telegram bot token from BotFather
- Your numeric Telegram user ID

Install:

```bash
python -m pip install -e .
```

Create your own config from the example, set your bot token in the environment,
then check startup:

```bash
export TG_FILER_BOT_TOKEN=your-token-from-botfather
tg-filer --config path/to/settings.yml --check-config --require-token
```

Start the bot:

```bash
tg-filer --config path/to/settings.yml
```

Open Telegram and send `/start`.

## Config

Start from `config.example.yaml` and change:

- `telegram.owner_user_ids`: your numeric Telegram user ID.
- `filesystem.roots`: the folders the bot may expose.
- `filesystem.max_preview_bytes`: preview size limit.
- `filesystem.max_upload_bytes`: direct upload size limit.
- `filesystem.search_result_limit`: number of search results.
- `filesystem.searchable_extensions`: file types used for content search.
- `filesystem.search_exclude_names`: names skipped by search.

Root paths must be absolute existing directories.

## Service Mode

A user-level systemd template is included:

```bash
mkdir -p ~/.config/tg-filer ~/.config/systemd/user
cp packaging/env.example ~/.config/tg-filer/env
cp packaging/tg-filer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tg-filer.service
```

Edit the copied environment and service files for your token, checkout path,
and config path.

## Development

```bash
PYTHONPATH=src python -m telegram_laptop_files --config config.example.yaml --check-config
python -m pytest -q
```

## Status

`tg-filer` is a usable personal MVP for private laptop file access through
Telegram. It is not a hosted service and does not include multi-user permission
management.
