# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **`!help` and `!list-repos` now send results via DM** — Keeps channels completely clean. Falls back to in-channel with auto-delete after 30 seconds if the user has DMs disabled.
- **Shortened command response lifetimes** — All in-channel command response messages now auto-delete after 10 seconds.
- **Repo ownership tracking** — `!add-repo` records the Discord user ID of who added each repository. `!remove-repo` allows any member to remove only repos they added themselves; admins and moderators can remove any. When a non-owner tries to remove, the bot pings who originally added it. Backward compatible with existing repos.
- **`!add-repo` access expanded** — Members who joined ≥ 24 hours ago can now add repos. Newer members get a friendly message telling them to wait or ask an admin.
- **Repository URL rejection** — `!add-repo` now requires the short `owner/repo` format. Full URLs are rejected to prevent Discord timeout penalties.
- **Repository existence verification** — `!add-repo` verifies the repo exists on GitHub via the API before saving.

### Fixed

- **Pylance type error on `bot.user` in `on_ready()`** — Added `assert bot.user is not None` to narrow the `Optional[ClientUser]` type, resolving the "id is not a known attribute of None" diagnostic.

### Added

- **Strict command channel option** — New `.env` setting `STRICT_COMMAND_CHANNEL` (default: empty/disabled). When set to a channel name (e.g. `repo-watcher`), the bot silently deletes any non-command message in that channel. Only official bot commands are allowed; all other messages are removed instantly with no warning or notification. Off by default.
- **`on_message` event in `bot.py`** — New event handler that intercepts messages in the strict channel, processes commands normally, and deletes everything else.
- **`get_strict_command_channel()` in `config.py`** — Returns the configured strict channel name, or empty string when disabled.
- **`is_admin_or_mod_or_member()` check in `bot.py`** — New decorator for `!add-repo`: admins/mods always allowed; members allowed if joined ≥ 24h ago.
- **`repo_exists()` in `watcher.py`** — Verifies a GitHub repository exists and is accessible via the API before adding.
- **`get_repo_owner()` / `load_repos_with_owners()` in `repo_manager.py`** — New functions for ownership tracking. `repos.txt` now stores `owner/repo <user_id>` format, backward compatible with old format.

- **Delete previous notifications option** — New `.env` setting `DELETE_PREVIOUS_NOTIFICATIONS` (default `false`). When set to `true`, the bot deletes a repo's previous commit notification embed before posting a new one, keeping exactly one notification per repo in the chat channel.
- **`notification_tracker.py`** — New module that tracks the Discord channel ID and message ID of each repo's last notification in a `.notification-messages` file.
- **`_handle_commit_update()` in `bot.py`** — New wrapper function that conditionally deletes old notifications and tracks new ones when the feature is enabled.
- **Config functions in `config.py`** — `get_delete_previous_notifications()` and `get_notification_tracking_path()`.

- **Smart commit filtering** — New `.env` options to reduce notification spam:
  - `MIN_EDIT_THRESHOLD` — Minimum total lines changed (additions + deletions) required to trigger a notification. Ignores tiny commits like typos or single-line README fixes.
  - `IGNORE_FILE_PATTERNS` — Comma-separated glob patterns for files to ignore. If ALL changed files match, the notification is suppressed (e.g. `README.md,*.txt`).
  - `IGNORE_FOLDER_PATTERNS` — Comma-separated folder substrings to ignore. If ALL changed files are within ignored folders, the notification is suppressed (e.g. `docs/,assets/`).
  - `IGNORE_STRINGS` — Comma-separated strings in commit messages (case-insensitive). Matches suppress the notification (e.g. `typo,chore,dependabot`).
- **`_check_commit_filters()` in `watcher.py`** — New function that orchestrates all commit-level filters before deciding whether to send a notification.
- **`_should_skip_by_commit_message()` in `watcher.py`** — Checks commit messages against `IGNORE_STRINGS`.
- **`_check_ignore_patterns()` in `watcher.py`** — Checks changed files against `IGNORE_FILE_PATTERNS` (glob-style via `fnmatch`) and `IGNORE_FOLDER_PATTERNS` (substring match).
- **Config functions in `config.py`** — `get_min_edit_threshold()`, `get_ignore_file_patterns()`, `get_ignore_folder_patterns()`, `get_ignore_strings()`.

- **Repository owner avatar in commit embeds** — Commit notifications now display the repository owner's profile photo (user or organization avatar) as the embed thumbnail instead of the generic GitHub logo. Fetched once from the GitHub API and cached in-memory; falls back to the GitHub logo gracefully on failure.
- **`get_repo_avatar_url()` in `watcher.py`** — New function to fetch and cache the repository owner's avatar URL from the GitHub API.
- **Configurable help command name** — Set `HELP_COMMAND` in your `.env` file to change the help command (e.g. `HELP_COMMAND="repos-help"` makes it `!repos-help`). Defaults to `help` for backwards compatibility. `!commands` always works as an alias regardless of the configured name.
- **Access control for `!add-repo` and `!remove-repo` commands** — Only server administrators and moderators can now use these commands. Regular users receive a permission error. The check uses Discord's built-in permission system:
  - Users with `Administrator` permission are allowed
  - Users with moderator-level permissions (`Manage Server`, `Manage Messages`, `Kick Members`, `Ban Members`) are allowed
  - The bot owner is allowed unconditionally
- **Global error handler for permission errors** — Catches `MissingPermissions` exceptions and sends a user-friendly "Only server admins and moderators can use this command" message
- **`is_admin_or_mod()` check decorator** — Reusable permission check function that can be applied to any command

### Changed

- **Help command updated** — `!help` now shows "Restricted to Admins & Moderators" on `!add-repo` and `!remove-repo` entries
- **README updated** — Commands table shows access restriction, Features list includes access control, How It Works section documents the permission model, FAQ added about who can use restricted commands, Troubleshooting covers permission-denied scenarios, Security section documents access control

## [0.1.0] - 2024-01-01

### Added

- Initial release
- `!add-repo` / `!add` command to add repositories to watch
- `!remove-repo` / `!remove` / `!rm` command to remove repositories
- `!list-repos` / `!list` / `!repos` command to list watched repositories
- `!check-now` / `!check` / `!scan` command to manually check for new commits
- `!help` / `!commands` command to show available commands
- Background loop that periodically checks all watched repos for new commits
- Rich Discord embed notifications for new commits
- GitHub API integration with rate limit handling and retry logic
- State persistence to avoid duplicate notifications across restarts
- Configurable check interval, log file paths, and retry settings via `.env`
- Support for GitHub personal access tokens for higher API rate limits
- Input sanitization supporting multiple repo URL formats
- Auto-deletion of command messages for clean channels
- Comprehensive rotating file logging

[Unreleased]: https://github.com/haywardgg/discord-repo-watcher/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/haywardgg/discord-repo-watcher/releases/tag/v0.1.0