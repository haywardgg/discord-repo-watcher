"""
Configuration loader for the Discord Repo Watcher bot.
Loads settings from a .env file in the same directory as this script.
"""

import os
from dotenv import load_dotenv

# Determine the script directory (works for both source and frozen packages)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env from the script directory
dotenv_path = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(dotenv_path)


def get_bot_token() -> str:
    """Get the Discord bot token from environment."""
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        raise ValueError(
            "DISCORD_BOT_TOKEN is not set. "
            f"Add it to {dotenv_path} or set the environment variable."
        )
    return token


def get_github_token() -> str:
    """Get the GitHub personal access token (may be empty)."""
    return os.getenv("GITHUB_TOKEN", "")


def get_repo_list_path() -> str:
    """Get the path to the repo list file."""
    return os.getenv("REPO_LIST", os.path.join(SCRIPT_DIR, "repos.txt"))


def get_state_file_path() -> str:
    """Get the path to the state file."""
    return os.getenv("STATE_FILE", os.path.join(SCRIPT_DIR, ".repo-state"))


def get_log_file_path() -> str:
    """Get the path to the log file."""
    return os.getenv("LOG_FILE", os.path.join(SCRIPT_DIR, "repo-watcher.log"))


def get_check_interval() -> int:
    """Get the repo check interval in seconds (default: 300 = 5 min)."""
    return int(os.getenv("CHECK_INTERVAL", "300"))


def get_max_retries() -> int:
    """Get maximum retry count for rate-limited API calls (default: 3)."""
    return int(os.getenv("MAX_RETRIES", "3"))


def get_retry_delay() -> int:
    """Get delay in seconds between retries (default: 5)."""
    return int(os.getenv("RETRY_DELAY", "5"))


def get_ignore_file_patterns() -> list[str]:
    """
    Get the ignore file patterns from the environment.
    Returns a list of lowercase substrings. If a commit's changed files ALL match
    any of these patterns, the notification is suppressed.
    Example: IGNORE_FILE_PATTERNS="README.md,.gitignore,LICENSE"
    """
    raw = os.getenv("IGNORE_FILE_PATTERNS", "")
    if not raw or not raw.strip():
        return []
    return [pattern.strip().lower() for pattern in raw.split(",") if pattern.strip()]


def get_help_command() -> str:
    """Get the custom help command name (default: help)."""
    return os.getenv("HELP_COMMAND", "help").strip().lower()
