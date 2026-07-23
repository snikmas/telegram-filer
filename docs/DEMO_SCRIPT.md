# Safe Portfolio Demo Script

Use only `config.demo.yaml` and the fictional `demo-data/` tree.

## Prepare

1. Run `python scripts/reset-demo.py`.
2. Copy `.env.example` to `.env` and add an approved demo bot token.
3. Replace the sample owner ID in `config.demo.yaml`.
4. Run `tg-filer --config config.demo.yaml --check-config --require-token`.
5. Start the bot with `tg-filer --config config.demo.yaml --require-token`.
6. Confirm the recording does not show the token, owner ID, chat ID, proxy
   details, private notifications, or local private paths.

## Record

1. Send `/start` and show the safe-demo banner and one allowlisted root.
2. Open `Reports/weekly-summary.md`.
3. Preview the report.
4. Download the report.
5. Run `/search invoice`.
6. Run `/content Telegram workflow`.
7. Open the fictional invoice.
8. Open the delete confirmation, then cancel it.
9. Send `/status` and show demo mode, configured limits, and healthy audit log.
10. End on the help screen or root list.

## After

1. Stop the demo bot.
2. Review every frame for identifiers or notifications.
3. Crop or blur Telegram account details.
4. Restore the demo tree with `python scripts/reset-demo.py`.
5. Do not publish until Mary approves the final recording.
