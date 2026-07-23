# tg-filer 0.2.1 — Portfolio Demo Release

Status: portfolio release candidate; not yet tagged.

## Highlights

- Published a sanitized 55-second walkthrough of the safe Telegram demo.
- Added `/clear` to reset browsing state and cancel pending actions.
- Safe fictional demo files with a repeatable reset command.
- Explicit demo mode in CLI and Telegram status output.
- Relative allowlisted-root paths resolved from the configuration directory.
- Separate disposable demo trash instead of the user's normal desktop trash.
- Polling-stall watchdog for supervised self-recovery.
- Portable user-level systemd template without developer-specific paths.
- GitHub Actions across Python 3.11–3.13.
- MIT license and buyer-oriented public documentation.

## Verification

- 81 tests passing.
- Clean isolated editable installation passing.
- Package wheel builds successfully.
- Example/demo/CI YAML files parse successfully.
- Demo configuration validation passes.
- `systemd-analyze --user verify` passes for the service template.
- Live owner-bot verification passes with zero queued Telegram updates.
- The bot delivered a verification message from the supervised v0.2.1 service.

The source, live demo, and public walkthrough are ready. Tag publication remains
intentionally separate from this source release.
