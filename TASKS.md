# Telegram Laptop Files - MVP Tasks

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

- [ ] Implement Telegram bot startup.
- [ ] Add owner Telegram user ID allowlist.
- [ ] Reject unauthorized users.
- [ ] Add `/start`.
- [ ] Add `/roots`.
- [ ] Add `/help`.
- [ ] Add `/cancel`.
- [ ] Add basic error handling wrapper.

Acceptance:

- My Telegram account can use the bot.
- Another Telegram account receives a denial or no useful access.
- `/start` shows configured root folders.

## Milestone 3 - Safe Filesystem Layer

- [ ] Define root-folder config model.
- [ ] Implement shared path resolver.
- [ ] Canonicalize allowed roots at startup.
- [ ] Reject path traversal.
- [ ] Reject symlink escape from allowed roots.
- [ ] Add file/folder metadata helper.
- [ ] Add tests for resolver safety.

Acceptance:

- All file actions go through one resolver.
- Attempts to access paths outside allowed roots fail.
- Resolver behavior is covered by tests.

## Milestone 4 - Browse UX

- [ ] Render root list with inline buttons.
- [ ] Render folder contents.
- [ ] Show hidden files inside allowlisted folders.
- [ ] Sort folders before files.
- [ ] Add parent navigation.
- [ ] Add pagination.
- [ ] Add file detail view.
- [ ] Handle empty folders.
- [ ] Handle missing or permission-denied folders.

Acceptance:

- I can navigate from `/start` into configured folders.
- Large folders remain usable through pagination.
- File detail view offers valid next actions.

## Milestone 5 - Preview And Download

- [ ] Define previewable extensions.
- [ ] Implement text preview size limit.
- [ ] Format preview safely for Telegram.
- [ ] Show metadata for unsupported or binary files.
- [ ] Implement file download.
- [ ] Add upload size check.
- [ ] Show metadata for files larger than 45 MB.
- [ ] Add create-compressed-archive action for oversized files.
- [ ] Send compressed archive when it is below the upload limit.
- [ ] Report compressed size clearly when archive is still too large.
- [ ] Handle Telegram upload errors.

Acceptance:

- I can preview Markdown notes from Obsidian.
- I can download a normal document.
- Oversized files show metadata and offer compressed archive creation.

## Milestone 6 - Delete Confirmation

- [ ] Create pending action model.
- [ ] Add delete button to file detail view.
- [ ] Add confirmation screen.
- [ ] Add expiration for pending delete actions.
- [ ] Implement cancel.
- [ ] Move deleted files to trash.
- [ ] If trash is unavailable, fail clearly instead of permanently deleting.
- [ ] Do not allow folder deletion in MVP.

Acceptance:

- Delete cannot happen from one accidental tap.
- Confirmed file deletion works.
- Expired or canceled confirmation cannot delete anything.

## Milestone 7 - Filename Search

- [ ] Add `/search <query>`.
- [ ] Search across allowed roots.
- [ ] Match case-insensitively.
- [ ] Tokenize multi-word query.
- [ ] Limit result count.
- [ ] Include path, size, and modified date in results.
- [ ] Make each result selectable.

Acceptance:

- `/search invoice pdf` returns matching files.
- Selecting a result opens the file detail view.
- Empty results are handled cleanly.

## Milestone 8 - Audit Logs And Reliability

- [ ] Add append-only JSONL audit log.
- [ ] Log unauthorized access attempts.
- [ ] Log browse, preview, download, delete, and search actions.
- [ ] Log failures with error type.
- [ ] Add graceful startup validation.
- [ ] Add graceful shutdown handling.
- [ ] Add basic local run script or command.

Acceptance:

- Important actions are visible in local logs.
- Common errors do not crash the bot.
- Startup fails clearly when config is invalid.

## Milestone 9 - Packaging For Personal Use

- [ ] Add install/run instructions.
- [ ] Add user-level systemd service template.
- [ ] Add environment file template.
- [ ] Add troubleshooting notes.
- [ ] Test laptop restart behavior if systemd is added.

Acceptance:

- I can start the bot reliably after reboot through a user-level systemd service, or with one documented command during development.
- Troubleshooting steps cover token, auth, config, and filesystem failures.

## Testing Checklist

- [ ] Unauthorized Telegram user cannot browse roots.
- [ ] Owner can browse all configured roots.
- [ ] Path traversal attempts are rejected.
- [ ] Symlink escape attempts are rejected.
- [ ] Missing file produces a clear message.
- [ ] Permission denied produces a clear message.
- [ ] Large folder pagination works.
- [ ] Preview truncates large text files.
- [ ] Binary preview is blocked.
- [ ] File download works.
- [ ] Oversized download shows metadata.
- [ ] Oversized file archive creation works when compression brings it under the upload limit.
- [ ] Oversized archive failure reports the compressed size clearly.
- [ ] Delete requires confirmation.
- [ ] Delete confirmation expires.
- [ ] Folder delete is blocked.
- [ ] Search returns useful results.
- [ ] Audit log records important actions.

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
