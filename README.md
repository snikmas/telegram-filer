# tg-filer

Secure, owner-only Telegram access to explicitly approved files and folders.

`tg-filer` runs locally on your computer and lets you browse selected folders
from Telegram. It is built for personal, owner-only access: find a file, preview
it, download it, archive it if it is too large, or move it to trash after
confirmation.

It is a portfolio-ready example of a private Telegram workflow: the bot runs on
the owner's computer, opens no inbound web port, and rejects every Telegram user
who is not on the configured owner allowlist.

```text
Phone -> Telegram Bot API -> tg-filer -> allowlisted laptop folders
```

## Safe Demo

The repository includes fictional invoices, reports, and meeting notes so the
full interface can be demonstrated without exposing private files.

```bash
python scripts/reset-demo.py
python -m pip install -e .
tg-filer --config config.demo.yaml --check-config
```

To connect the safe demo to Telegram, copy `.env.example` to `.env`, add a bot
token, replace the example owner ID in `config.demo.yaml`, and run:

```bash
tg-filer --config config.demo.yaml --require-token
```

Demo mode is shown explicitly in `/start` and `/status`. Its allowlist contains
only the ignored `demo-data/` directory. Run `python scripts/reset-demo.py`
again after testing deletion to restore the fictional files. Demo deletions use
the separate ignored `demo-trash/` directory, not the user's normal desktop
trash.

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
- A polling watchdog can exit a stalled process so a supervisor such as
  `systemd` restarts it.

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
python -m pip install --user .
```

Restore the safe sample files and copy the configuration:

```bash
python scripts/reset-demo.py
mkdir -p ~/.config/tg-filer
cp config.example.yaml ~/.config/tg-filer/config.yaml
cp packaging/env.example ~/.config/tg-filer/env
chmod 600 ~/.config/tg-filer/config.yaml ~/.config/tg-filer/env
```

Edit `~/.config/tg-filer/config.yaml`:

- Change `telegram.owner_user_ids`.
- Change the root path to the folder you intentionally allow.
- Set `app.demo_mode: false` for private use.

Put the real token in `~/.config/tg-filer/env`, then validate without starting:

```bash
~/.local/bin/tg-filer \
  --config ~/.config/tg-filer/config.yaml \
  --env-file ~/.config/tg-filer/env \
  --check-config \
  --require-token
```

## Config

Start from `config.example.yaml` and change:

- `telegram.owner_user_ids`: your numeric Telegram user ID.
- `filesystem.roots`: the folders the bot may expose.
- `filesystem.max_preview_bytes`: preview size limit.
- `filesystem.max_upload_bytes`: direct upload size limit.
- `filesystem.search_result_limit`: number of search results.
- `filesystem.searchable_extensions`: file types used for content search.
- `filesystem.search_exclude_names`: names skipped by search.

Root paths must point to existing directories. Absolute paths are supported;
relative paths are resolved from the directory containing the YAML config.

## Service Mode

A user-level systemd template is included:

```bash
mkdir -p ~/.config/tg-filer ~/.config/systemd/user
cp packaging/env.example ~/.config/tg-filer/env
cp config.example.yaml ~/.config/tg-filer/config.yaml
chmod 600 ~/.config/tg-filer/config.yaml ~/.config/tg-filer/env
cp packaging/tg-filer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tg-filer.service
```

The template includes `~/.local/bin` in its service PATH and launches the
installed `tg-filer` command, so it does not contain a developer-specific
checkout path. Edit the copied environment and configuration files before
starting it.

To keep the user service available after a PC restart, enable linger once:

```bash
loginctl enable-linger "$USER"
```

Verify the persistent user service:

```bash
systemctl --user status tg-filer.service
systemctl --user is-enabled tg-filer.service
loginctl show-user "$USER" -p Linger --value
journalctl --user -u tg-filer.service --since today
```

`tg-filer.service` is a user service, so it appears under `systemctl --user`,
not the root-level `systemctl` service list. If Telegram polling stops consuming
updates while the process remains alive, the watchdog records a
`polling_stall` audit event and exits with code `75`; the service template then
restarts it.

## What Can Be Customized

For a client project, the same core can be adapted for:

- controlled document lookup and delivery;
- daily or weekly report delivery;
- filename and text search over approved folders;
- owner-only notifications and approval flows;
- custom commands, limits, branding, and deployment;
- installation on a Linux computer or VPS.

This repository is not public multi-user cloud storage. It does not protect a
machine whose operating-system account or Telegram owner account is already
compromised.

## Troubleshooting

- **Missing token:** put `TG_FILER_BOT_TOKEN=...` in the selected env file and
  run the config check with `--require-token`.
- **Access denied:** replace the sample `owner_user_ids` value with the numeric
  Telegram ID of the intended owner.
- **Root does not exist:** use an existing directory; relative roots are
  resolved from the YAML file's directory.
- **Permission denied:** run the bot as an operating-system user who can read
  the selected root. Do not solve this by granting broad filesystem access.
- **Telegram is unreachable:** set `TG_FILER_PROXY` when the local network
  requires a proxy, then verify that proxy independently.
- **File is too large:** direct upload follows `max_upload_bytes`; the bot can
  try a ZIP archive, but Telegram's own upload limits still apply.
- **Service is active but replies stop:** inspect
  `journalctl --user -u tg-filer.service`; the polling watchdog should record
  pending/stall events and let systemd restart the process.
- **Demo files were moved to trash:** run `python scripts/reset-demo.py`.

## Development

```bash
python scripts/reset-demo.py
python -m pip install -e . pytest
tg-filer --config config.demo.yaml --check-config
python -m pytest -q
```

## Status

`tg-filer` is a usable personal MVP for private laptop file access through
Telegram. It is not a hosted service and does not include multi-user permission
management. The repository includes a safe demonstration dataset, automated
tests, CI configuration, an MIT license, and a portable user-service template.
