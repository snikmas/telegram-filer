# Telegram Laptop Files

A private Telegram bot for browsing allowlisted laptop folders from a phone.

The MVP runs locally on the laptop and uses Telegram long polling, so no public
web server is needed.

## MVP Status

Milestones 1 through 3 are in place:

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

Only Telegram users listed in `telegram.owner_user_ids` can use the bot. Other
users receive an access-denied response and no folder details.

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

## Development

Run the module directly during development:

```bash
PYTHONPATH=src python -m telegram_laptop_files --config config.example.yaml --check-config
```

Run the tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
