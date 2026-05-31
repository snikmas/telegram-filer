# tg-filer - Tasks

## Current State

MVP 1 is functionally complete.

Completed:

- Private Telegram bot startup with long polling.
- Owner-only Telegram allowlist.
- Configured allowlisted root folders.
- Safe filesystem resolver.
- Folder browsing with pagination.
- File detail view.
- Text preview.
- File download.
- Oversized-file archive action.
- Delete-to-trash with confirmation.
- Filename search.
- Recent files command.
- Health/status command.
- JSONL audit logs.
- Startup config validation.
- Local run script.
- User-level systemd service template.
- README quickstart and troubleshooting.
- Test coverage for core safety and bot behavior.

Remaining MVP 1 operational check:

- [ ] Validate user-level systemd behavior after laptop restart.

## MVP 2 - File And Content Search

Goal: make the bot useful when I remember what a file is about, not only where it is.

MVP 2 should add:

- Filename/path search improvements.
- Content search inside text-like files.
- Compact result snippets.
- Result selection that opens the existing file detail screen.

No AI for MVP 2.

## Milestone 10 - Search Settings

- [x] Add config for content-search file-size limit.
- [x] Add config for searchable text extensions.
- [x] Add config for max search results.
- [x] Add config for max snippet length.
- [x] Document search limits in README.

Acceptance:

- Search behavior can be tuned without code changes.
- Large/binary files are skipped predictably.

## Milestone 11 - Filename Search Cleanup

- [x] Review current `/search <query>` behavior.
- [x] Make token matching consistent and documented.
- [x] Ensure path/name matching is case-insensitive.
- [x] Keep results limited and sorted usefully.
- [x] Show root, relative path, size, and modified date.
- [x] Add or update tests for filename search edge cases.

Acceptance:

- `/search invoice pdf` finds matching filenames or paths.
- Selecting a result opens the existing file detail view.
- Empty results are clear.

## Milestone 12 - Content Search

- [x] Add `/content <query>` command.
- [x] Scan only configured roots.
- [x] Search only likely text files.
- [x] Skip oversized files.
- [x] Decode text safely.
- [x] Match query case-insensitively.
- [x] Support multi-token queries.
- [x] Return snippets around matched text.
- [x] Limit result count.
- [x] Log content-search actions to the audit log.
- [x] Add tests for content matches, skipped files, permission errors, and empty results.

Acceptance:

- `/content telegram config` finds files containing those words.
- Results show a useful snippet.
- Selecting a result opens the file detail view.
- Permission errors and unreadable files do not crash the bot.

## Milestone 13 - Search UX

- [x] Update `/help` with filename and content search commands.
- [x] Add short examples to search error messages.
- [ ] Add "Search again" or back navigation where it fits naturally.
- [ ] Keep Telegram messages compact enough for phone use.
- [ ] Reuse existing buttons and file-detail actions.

Acceptance:

- I can search, open, preview, and download a result from my phone without remembering exact paths.

## Optional MVP 2 Enhancements

These are useful, but not required for the MVP 2 finish line:

- [ ] Add `/find <query>` alias for filename search.
- [ ] Add `/grep <query>` alias for content search.
- [ ] Add root filters, for example `/content obsidian meeting notes`.
- [ ] Add extension filters, for example Markdown-only search.
- [x] Add recent-files command.
- [x] Add health/status command.

## Implementation Notes

Do not run arbitrary shell commands from Telegram.

Recommended order:

1. Implement search in Python with `pathlib` and safe file reads.
2. Add tests around security and edge cases.
3. Manually test on real folders.
4. Consider optional `rg` backend only if Python scanning is too slow.
5. Consider SQLite indexing only if live scanning is still not good enough.

If `rg` is added later, call it with fixed arguments and `shell=False`. Do not build shell command strings from Telegram input.

## MVP 2 Finish Line

- I can search by filename/path.
- I can search by file content.
- I can open any search result in the existing file view.
- I can preview or download the result.
- Search stays inside allowlisted roots.
- Search errors are handled cleanly.

## Future Backlog

- Optional SQLite full-text index.
- Better search ranking.
- Root and extension filters.
- Favorite folders.
- Recent files.
- Upload-to-laptop flow.
- Safer text edit flow with backup and diff preview.
- Local web admin page.
