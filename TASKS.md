# tg-filer - MVP Tasks

## Working Plan

Target: 1-2 week MVP.

Scope: private Telegram bot for safe file browsing, preview, download, delete confirmation, and filename search across allowlisted laptop folders.

## Milestone 1 - Product Skeleton

- [x] Choose final project name and repo folder.
- [x] Choose Python Telegram framework.
- [x] Create minimal app structure.
- [x] Add local config example with roots for `/home/snikmas/work`, `/home/snikmas/Documents`, and `/home/snikmas/Documents/Obsidian Vault`.
- [x] Add `.env` handling or documented environment variable loading.
- [x] Add `.gitignore` entries for secrets, logs, local data, and virtualenv.
- [x] Add README quickstart.

Acceptance:

- App starts locally.
- Config loads.
- Bot token is not committed.

## Milestone 2 - Telegram Auth And Commands

- [x] Implement Telegram bot startup.
- [x] Add owner Telegram user ID allowlist.
- [x] Reject unauthorized users.
- [x] Add `/start`.
- [x] Add `/roots`.
- [x] Add `/help`.
- [x] Add `/cancel`.
- [x] Add basic error handling wrapper.

Acceptance:

- My Telegram account can use the bot.
- Another Telegram account receives a denial or no useful access.
- `/start` shows configured root folders.

## Milestone 3 - Safe Filesystem Layer

- [x] Define root-folder config model.
- [x] Implement shared path resolver.
- [x] Canonicalize allowed roots at startup.
- [x] Reject path traversal.
- [x] Reject symlink escape from allowed roots.
- [x] Add file/folder metadata helper.
- [x] Add tests for resolver safety.

Acceptance:

- All file actions go through one resolver.
- Attempts to access paths outside allowed roots fail.
- Resolver behavior is covered by tests.

## Milestone 4 - Browse UX

- [x] Render root list with shell-style text selection.
- [x] Render folder contents.
- [x] Show hidden files inside allowlisted folders.
- [x] Sort folders before files.
- [x] Add parent navigation with `..`.
- [x] Add pagination with `more` and `prev`.
- [x] Add file detail view.
- [x] Handle empty folders.
- [x] Handle missing or permission-denied folders.

Acceptance:

- I can navigate from `/start` into configured folders.
- Large folders remain usable through pagination.
- File detail view offers valid next actions.

## Milestone 5 - Preview And Download

- [x] Define previewable extensions.
- [x] Implement text preview size limit.
- [x] Format preview safely for Telegram.
- [x] Show metadata for unsupported or binary files.
- [x] Implement file download.
- [x] Add upload size check.
- [x] Show metadata for files larger than 45 MB.
- [x] Add create-compressed-archive action for oversized files.
- [x] Send compressed archive when it is below the upload limit.
- [x] Report compressed size clearly when archive is still too large.
- [x] Handle Telegram upload errors.

Acceptance:

- I can preview Markdown notes from Obsidian.
- I can download a normal document.
- Oversized files show metadata and offer compressed archive creation.

## Milestone 6 - Delete Confirmation

- [x] Create pending action model.
- [x] Add delete button to file detail view.
- [x] Add confirmation screen.
- [x] Add expiration for pending delete actions.
- [x] Implement cancel.
- [x] Move deleted files to trash.
- [x] If trash is unavailable, fail clearly instead of permanently deleting.
- [x] Do not allow folder deletion in MVP.

Acceptance:

- Delete cannot happen from one accidental tap.
- Confirmed file deletion works.
- Expired or canceled confirmation cannot delete anything.

## Milestone 7 - Filename Search

- [x] Add `/search <query>`.
- [x] Search across allowed roots.
- [x] Match case-insensitively.
- [x] Tokenize multi-word query.
- [x] Limit result count.
- [x] Include path, size, and modified date in results.
- [x] Make each result selectable.

Acceptance:

- `/search invoice pdf` returns matching files.
- Selecting a result opens the file detail view.
- Empty results are handled cleanly.

## Milestone 8 - Audit Logs And Reliability

- [x] Add append-only JSONL audit log.
- [x] Log unauthorized access attempts.
- [x] Log browse, preview, download, delete, and search actions.
- [x] Log failures with error type.
- [x] Add graceful startup validation.
- [x] Add graceful shutdown handling.
- [x] Add basic local run script or command.

Acceptance:

- Important actions are visible in local logs.
- Common errors do not crash the bot.
- Startup fails clearly when config is invalid.

## Milestone 9 - Packaging For Personal Use

- [x] Add install/run instructions.
- [x] Add user-level systemd service template.
- [x] Add environment file template.
- [x] Add troubleshooting notes.
- [ ] Test laptop restart behavior if systemd is added.

Acceptance:

- I can start the bot reliably after reboot through a user-level systemd service, or with one documented command during development.
- Troubleshooting steps cover token, auth, config, and filesystem failures.

## Testing Checklist

- [x] Unauthorized Telegram user cannot browse roots.
- [x] Owner can browse all configured roots.
- [x] Path traversal attempts are rejected.
- [x] Symlink escape attempts are rejected.
- [x] Missing file produces a clear message.
- [x] Permission denied produces a clear message.
- [x] Large folder pagination works.
- [x] Preview truncates large text files.
- [x] Binary preview is blocked.
- [x] File download works.
- [x] Oversized download shows metadata.
- [x] Oversized file archive creation works when compression brings it under the upload limit.
- [x] Oversized archive failure reports the compressed size clearly.
- [x] Delete requires confirmation.
- [x] Delete confirmation expires.
- [x] Folder delete is blocked.
- [x] Search returns useful results.
- [x] Audit log records important actions.

## Suggested 2-Week Schedule

### Days 1-2

- Project skeleton.
- Config.
- Telegram startup.
- Owner allowlist.
- Basic commands.

### Days 3-4

- Filesystem resolver.
- Safety tests.
- Root list and folder browsing.

### Days 5-6

- File detail view.
- Preview.
- Download.
- Upload size handling.

### Days 7-8

- Delete confirmation.
- Pending action expiration.
- Audit logging.

### Days 9-10

- Filename search.
- Result selection.
- UX cleanup.

### Days 11-12

- Error handling hardening.
- Manual end-to-end testing from phone.
- Documentation updates.

### Days 13-14

- Optional user systemd service.
- Final bug fixes.
- Decide next iteration: GPT search, content index, or editing.

## Post-MVP Backlog

- Full-text search index for selected roots.
- Natural-language GPT/Codex search.
- File summaries for Markdown, PDF, and documents.
- Upload-to-laptop flow.
- Replace-file flow with backup.
- Append-to-note flow.
- Text-file edit flow with diff preview.
- Codex patch proposal flow.
- Folder delete with stronger confirmation.
- Per-root permissions.
- Local web admin page.
- Encrypted local config.
- Health check command.

## Deferred Risks

- Telegram file-size limits may affect large documents and media.
- Laptop sleep/offline state means the bot cannot respond.
- Editing files from chat can easily corrupt important files without backup and diff UX.
- GPT/Codex file access needs strict boundaries to avoid leaking private data or changing files unexpectedly.
