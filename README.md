<div align="center">

# GitHub Repo Watcher Bot

**A Discord bot that monitors GitHub repositories and sends rich commit notifications to your server.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Discord](https://img.shields.io/badge/discord-py-5865F2)](https://discordpy.readthedocs.io/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)]()

</div>

---

<img width="1280" height="720" alt="grok-image-06282362-a7b8-47b7-b544-bc70b73660bb" src="https://github.com/user-attachments/assets/77b13517-eb40-48a8-9169-eb6c958589a8" />


## Quick Start

```bash
# Clone and enter the repository
git clone https://github.com/haywardgg/discord-repo-watcher.git
cd discord-repo-watcher

# Set up a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create your configuration
cp example.env .env
# Edit .env and add your DISCORD_BOT_TOKEN

# Run the bot
python bot.py
```

---

## Features

- ✅ **Interactive commands** — `!add-repo`, `!remove-repo`, `!list-repos`, `!check-now`
- ✅ **Automated monitoring** — checks all watched repos every 5 minutes (configurable)
- ✅ **Rich Discord embeds** — commit details, author, timestamp, direct links, and repo owner's avatar
- ✅ **Rate limit handling** — detects GitHub API rate limits and retries automatically
- ✅ **Token support** — GitHub token for 5,000 API requests/hour
- ✅ **State persistence** — never sends duplicate notifications, survives restarts
- ✅ **Clean channels** — `!help` and `!list-repos` send results via DM to keep channels clean; other command responses auto-delete after 10 seconds. Falls back to in-channel with auto-delete if DMs are disabled.
- ✅ **Smart notification filtering** — customize thresholds and ignore patterns to reduce spam
- ✅ **One-notification-per-repo** — enable `DELETE_PREVIOUS_NOTIFICATIONS` to keep only the latest commit embed per repo in the channel
- ✅ **Comprehensive logging** — rotating log files with debug-level detail
- ✅ **Input sanitization** — `!add-repo` requires short `owner/repo` format; verifies repos exist on GitHub before adding
- ✅ **Access control** — `!add-repo` available to all members (24h+); `!remove-repo` allows members to remove their own repos, admins/mods can remove any

---

## Prerequisites

- **Python 3.10+** installed on your system
- A **Discord Bot Token** — create one at the [Discord Developer Portal](https://discord.com/developers/applications)
- (Optional) A **GitHub personal access token** for higher API rate limits

---

## Setup

### 1. Create a Discord Bot Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → give it a name (e.g., "Repo Watcher")
3. Go to **Bot** → **Add Bot**
4. Under **Token**, click **Copy** — save this as your bot token
5. Under **Privileged Gateway Intents**, enable **Message Content Intent** and **Server Members Intent**

### 2. Invite the Bot to Your Server

In the Developer Portal, go to **OAuth2** → **URL Generator**:

| Setting | Value |
|---------|-------|
| **Scopes** | `bot` |
| **Permissions** | Send Messages, Send Messages in Threads, Embed Links, Manage Messages, Read Message History, Server Members Intent |

Copy the generated URL and open it in your browser to invite the bot.

### 3. Configure the Bot

```bash
cp example.env .env
```

Edit `.env` with your settings:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | ✅ Yes | — | Your Discord bot token |
| `GITHUB_TOKEN` | ❌ No | `""` | GitHub token for higher API rate limits |
| `REPO_LIST` | ❌ No | `./repos.txt` | Path to the repository list file |
| `STATE_FILE` | ❌ No | `./.repo-state` | Path to the state tracking file |
| `LOG_FILE` | ❌ No | `./repo-watcher.log` | Path to the log file |
| `CHECK_INTERVAL` | ❌ No | `300` | Seconds between background checks |
| `MAX_RETRIES` | ❌ No | `3` | Retry attempts on rate limit errors |
| `HELP_COMMAND` | ❌ No | `"help"` | Custom name for the help command (e.g. `repos-help`) |
| `RETRY_DELAY` | ❌ No | `5` | Seconds between retries |
| `MIN_EDIT_THRESHOLD` | ❌ No | `0` | Minimum lines changed (additions + deletions) to trigger a notification. `0` = no threshold |
| `IGNORE_FILE_PATTERNS` | ❌ No | `""` | Comma-separated glob patterns for files to ignore (e.g. `README.md,*.txt`). Notification suppressed when ALL files match |
| `IGNORE_FOLDER_PATTERNS` | ❌ No | `""` | Comma-separated folder substrings to ignore (e.g. `docs/,assets/`). Notification suppressed when ALL files are in ignored folders |
| `IGNORE_STRINGS` | ❌ No | `""` | Comma-separated strings in commit messages to suppress (case-insensitive, e.g. `typo,chore,dependabot`) |
| `STRICT_COMMAND_CHANNEL` | ❌ No | `""` | Channel name where only bot commands are allowed. Non-command messages are silently deleted. Leave empty to disable. |
| `DELETE_PREVIOUS_NOTIFICATIONS` | ❌ No | `false` | When `true`, deletes a repo's previous commit notification embed from the channel before posting a new one, keeping only one notification per repo |

### 4. Run the Bot

```bash
# Activate your virtual environment first
source venv/bin/activate

# Start the bot
python bot.py
```

---

## Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `!add-repo <owner/repo>` | `!add` | Add a repository to watch *(Admins, Mods, or members 24h+)* |
| `!remove-repo <owner/repo>` | `!remove`, `!rm` | Remove a repository *(Admins/Mods: any; members: own repos only)* |
| `!list-repos` | `!list`, `!repos` | Show all watched repositories |
| `!check-now` | `!check`, `!scan` | Manually check all repos for new commits *(Admins & Moderators only)* |
| `!help` | `!commands` | Show available commands |

### Examples

```
!add-repo microsoft/vscode
!remove-repo microsoft/vscode
!list-repos
!check-now
```

---

## How It Works

1. **Bot starts** — connects to Discord, loads the repo list from `repos.txt`
2. **Background loop** — every `CHECK_INTERVAL` seconds, checks all watched repos for new commits via the GitHub API
3. **New commit detected** — posts a rich embed with commit hash, message, author, timestamp, and repo owner's avatar as the thumbnail
4. **State tracked** — saves the last-seen commit hash to `.repo-state`, ensuring no duplicate notifications
5. **Commands** — `!add-repo` and `!remove-repo` update `repos.txt` in real time
6. **Access control** — `!add-repo` is available to members who joined ≥ 24 hours ago, plus admins and mods always. `!remove-repo` lets any member remove repos they added themselves, while admins/mods can remove any
7. **Smart filtering** — commits are checked against `MIN_EDIT_THRESHOLD`, `IGNORE_FILE_PATTERNS`, `IGNORE_FOLDER_PATTERNS`, and `IGNORE_STRINGS` before sending notifications. Filtered commits are still tracked to avoid re-notification
8. **Delete previous notifications** — when `DELETE_PREVIOUS_NOTIFICATIONS=true`, the bot deletes a repo's previous notification embed from the channel before posting a new one, keeping exactly one notification per repo

### Notification Channel Selection

The bot automatically picks a channel for background notifications using this priority:

1. A channel named `repo-watcher` (or `repo_watcher`)
2. A channel named `github` (or `github-watcher`)
3. The first available text channel in the server

> **Tip:** Create a dedicated `#repo-watcher` channel for clean, organized notifications.

### First Run Behavior

When a new repository is added, the bot:
1. Verifies the repo exists on GitHub
2. Records who added it for ownership tracking
3. Sends a "Now tracking this repository!" message (auto-deletes after 10s)
4. Posts a full commit embed for the latest commit
5. Saves the commit hash — subsequent runs only notify on **new** commits

### Member Leave Cleanup

When a member leaves the server, the bot automatically:
1. Removes all repos they added from the watch list
2. Deletes their commit notification embeds from the channel
3. Clears their tracking data to keep everything clean
4. Notifies the server owner via DM
5. Posts a light-hearted farewell message in the repo-watcher channel

---

## Running in Production

### Option 1: systemd Service (Recommended)

Create a service file:

```bash
sudo nano /etc/systemd/system/repo-watcher.service
```

```ini
[Unit]
Description=GitHub Repo Watcher Bot
After=network.target

[Service]
Type=simple
User=your-username
Group=your-username
WorkingDirectory=/path/to/discord-repo-watcher
ExecStart=/path/to/discord-repo-watcher/venv/bin/python3 /path/to/discord-repo-watcher/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Replace `your-username` and `/path/to/discord-repo-watcher` with your actual values. Use `which python3` inside your venv to find the correct Python path.

```bash
# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable repo-watcher
sudo systemctl start repo-watcher

# Monitor the service
sudo systemctl status repo-watcher
sudo journalctl -u repo-watcher -f
```

### Option 2: screen/tmux

```bash
screen -S repo-watcher
source venv/bin/activate
python bot.py
# Detach with Ctrl+A then D
```

---

## File Reference

| File | Purpose | Editable? |
|------|---------|-----------|
| `CHANGELOG.md` | Version history and changes | ❌ No |
| `bot.py` | Main Discord bot — commands and background loop | ❌ No |
| `config.py` | Configuration loader from `.env` | ❌ No |
| `watcher.py` | GitHub API calls and commit checking logic | ❌ No |
| `repo_manager.py` | Add/remove/list repositories | ❌ No |
| `state_manager.py` | Persist last-seen commit hashes | ❌ No |
| `notification_tracker.py` | Track last notification message IDs per repo (for delete previous notifications feature) | ❌ No |
| `.env` | Your configuration (gitignored) | ✅ Yes |
| `repos.txt` | List of repositories to watch | ✅ Yes |
| `.repo-state` | Commit hash tracking state (auto-generated) | ⚠️ Reset to re-notify |
| `.notification-messages` | Tracked message IDs for deleting previous notifications (auto-generated when feature is enabled) | ❌ No |
| `repo-watcher.log` | Application logs (auto-generated) | ❌ No |

---

## Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| `ModuleNotFoundError: No module named 'discord'` | Dependencies not installed | Run `pip install -r requirements.txt` (activate your venv first) |
| `DISCORD_BOT_TOKEN is not set` | Token missing in `.env` | Add your bot token to `.env` |
| Bot doesn't respond to commands | Missing Message Content Intent | Enable it in Discord Developer Portal → Bot settings |
| No notifications sent | No suitable channel found | Create a channel named `repo-watcher` or `github` |
| Bot can't send messages in channel | Channel permission overwrites | Add the bot's role to the channel permissions with Send Messages ✅ |
| `!add-repo` fails | Invalid repo format | Use `owner/repo` format (e.g., `microsoft/vscode`) |
| `!add-repo` says "No permission" | New member (< 24h) or invalid format | Wait 24 hours after joining, or ask an admin/moderator for help |
| `!remove-repo` says "not the owner" | Trying to remove someone else's repo | Only admins/mods can remove any repo; members can only remove their own |
| Messages aren't deleting | Missing permissions or cache issue | Ensure the bot has Manage Messages permission and Server Members Intent enabled |
| GitHub API errors | Rate limited or no token | Add a `GITHUB_TOKEN` or reduce repo count |
| Duplicate commit notifications | State file corruption | See "State File Recovery" below |

### State File Recovery

If the bot sends duplicate notifications or stops detecting new commits, reset the state:

```bash
# Stop the bot, then:
rm -f .repo-state

# Restart and run !check-now in Discord
```

### Service Not Starting

If `sudo systemctl status repo-watcher` shows failure:

```bash
# Check the logs
sudo journalctl -u repo-watcher -f

# Common issues:
# - Wrong Python path: system Python doesn't have discord.py installed
#   Fix: point ExecStart to your venv's Python
# - Permission denied: user can't access the directory
#   Fix: check ownership with `ls -la /path/to/discord-repo-watcher`
# - .env not found: WorkingDirectory is wrong
#   Fix: ensure WorkingDirectory matches the bot.py location
```

---

## FAQ

**Q: Does the bot require the `applications.commands` scope?**  
A: No. The bot uses `!` prefix commands only. Slash command support may be added in the future.

**Q: How do I add a GitHub token?**  
A: Generate one at [GitHub Settings → Tokens](https://github.com/settings/tokens) (no permissions needed for public repos). Add it to `GITHUB_TOKEN` in your `.env`.

**Q: Can I run multiple instances for different servers?**  
A: Yes. The bot can be in multiple servers simultaneously. Notifications go to the first suitable channel in each server.

**Q: Who can use `!add-repo` and `!remove-repo`?**  
A: `!add-repo` — members who joined ≥ 24 hours ago can add repos (admins/mods always). The bot verifies repos exist on GitHub before adding, and requires the short `owner/repo` format (URLs are rejected). `!remove-repo` — members can remove only repos they added themselves; admins/mods can remove any. When a member leaves, all their repos are automatically cleaned up.

**Q: How do I stop the bot from auto-deleting response messages?**  
A: Change or remove the `delete_after=10` values on `ctx.send()` calls in `bot.py`. Command messages (what users type) are handled separately via `_delete_command()`.

**Q: Can I change the command prefix from `!` to something else?**  
A: Yes. Change `command_prefix="!"` in `bot.py` to your preferred prefix.

**Q: What happens if the bot is offline when a commit is pushed?**  
A: The bot checks the latest commit on each scan cycle. If a commit was missed while offline, it will be detected and notified on the next cycle.

**Q: Is there a Docker image available?**  
A: Not yet, but a `Dockerfile` is planned for future releases.

---

## Security

- **`.env` is gitignored** — your bot token and GitHub token are never committed to the repository
- **Bot permissions are minimal** — only Send Messages, Embed Links, Manage Messages, and Read Message History
- **No database** — all data is stored in plain text files with no external service dependencies
- **Process visibility** — tokens are passed as environment variables, not hardcoded in scripts
- **Access control** — `!add-repo` is gated by server join age (24h) and validates repos before adding. `!remove-repo` enforces repo ownership — members can only remove their own repos, while admins/mods can remove any. Repos are auto-removed when a member leaves the server.
- **No data leakage** — all filtering (edit thresholds, file/folder ignore patterns, message strings) is applied server-side. Filtered commits are never sent to Discord

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run the tests: `python -m py_compile *.py`
5. Commit and push: `git commit -m "Add my feature" && git push origin feature/my-feature`
6. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/haywardgg/discord-repo-watcher.git
cd discord-repo-watcher
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## License

This project is open source and available under the [MIT License](LICENSE).
