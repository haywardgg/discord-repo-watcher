"""
Core logic for fetching commits from the GitHub API and checking for new commits.
"""

import datetime
import logging
import time
from typing import Optional, Tuple, Union

import requests

import config
import state_manager

logger = logging.getLogger("repo_watcher")


# In-memory cache: {repo: avatar_url}
_avatar_cache: dict[str, str] = {}


def _github_api_call(endpoint: str) -> Optional[list]:
    """
    Make a call to the GitHub API with retry logic for rate limiting.
    Returns the parsed JSON response (a list for the commits endpoint), or None on failure.
    """
    url = f"https://api.github.com/{endpoint}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    github_token = config.get_github_token()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    max_retries = config.get_max_retries()
    retry_delay = config.get_retry_delay()

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=(10, 30))
        except requests.exceptions.Timeout:
            logger.warning("Timeout calling GitHub API: %s", endpoint)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            continue
        except requests.exceptions.RequestException as e:
            logger.warning("Network error calling GitHub API: %s", e)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            continue

        if resp.status_code == 429 or resp.status_code == 403:
            error_data = resp.json()
            message = error_data.get("message", "Unknown rate limit error")
            logger.warning("Rate limited: %s, retrying in %ds...", message, retry_delay)
            time.sleep(retry_delay)
            continue

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                message = error_data.get("message", f"HTTP {resp.status_code}")
                logger.warning("GitHub API error: %s", message)
            except Exception:
                logger.warning("GitHub API error: HTTP %s", resp.status_code)
            return None

        return resp.json()

    logger.error("Failed to call GitHub API after %d attempts: %s", max_retries, endpoint)
    return None


def get_repo_avatar_url(repo: str) -> Optional[str]:
    """
    Fetch the avatar URL of a repository's owner (user or organisation).
    Results are cached in memory to avoid repeated API calls.
    Returns the avatar URL string, or None on failure.
    """
    # Check cache first
    cached = _avatar_cache.get(repo)
    if cached:
        logger.debug("Using cached avatar URL for %s", repo)
        return cached

    data = _github_api_call(f"repos/{repo}")
    if not data or not isinstance(data, dict):
        logger.warning("Could not fetch repo metadata for %s", repo)
        return None

    owner = data.get("owner")
    if not owner or not isinstance(owner, dict):
        logger.warning("No owner data found for %s", repo)
        return None

    avatar_url = owner.get("avatar_url")
    if not avatar_url:
        logger.warning("No avatar_url for owner of %s", repo)
        return None

    # Cache it
    _avatar_cache[repo] = avatar_url
    logger.debug("Cached avatar URL for %s: %s", repo, avatar_url)
    return avatar_url


def get_latest_commit(repo: str) -> Optional[Tuple[str, str, str, str, str]]:
    """
    Fetch the latest commit from a repository's default branch.
    Returns a tuple: (commit_hash, commit_message, author_name, commit_date, commit_url)
    Returns None if the repo can't be reached or has no commits.
    """
    data = _github_api_call(f"repos/{repo}/commits?per_page=1")
    if not data:
        return None

    if not isinstance(data, list) or len(data) == 0:
        logger.debug("No commits found for %s", repo)
        return None

    commit = data[0]
    commit_hash = commit.get("sha", "")
    if not commit_hash:
        return None

    commit_data = commit.get("commit", {})
    commit_msg = commit_data.get("message", "")
    author_info = commit_data.get("author", {})
    author_name = author_info.get("name", "") or commit.get("author", {}).get("login", "Unknown")
    commit_date = author_info.get("date", "") or commit_data.get("committer", {}).get("date", "")
    commit_url = f"https://github.com/{repo}/commit/{commit_hash}"

    # Use only the first line of the commit message
    commit_msg = commit_msg.split("\n")[0].strip()

    return (commit_hash, commit_msg, author_name, commit_date, commit_url)


# Result type for check_repo:
# (has_update: False, error_message: str | None)
# (has_update: True, commit_hash: str, reason: str, msg: str, author: str, date: str, url: str)
CheckRepoResult = Union[
    Tuple[bool, Optional[str]],
    Tuple[bool, str, str, str, str, str, str],
]


def _parse_iso_date(date_str: str) -> Optional[datetime.datetime]:
    """
    Parse an ISO 8601 date string into an aware UTC datetime.
    GitHub returns dates in ISO 8601 format (e.g. '2024-01-15T10:30:00Z').
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        # Handle 'Z' suffix and timezone offsets
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        logger.warning("Failed to parse commit date: %s", date_str)
        return None


def _is_commit_old_enough(commit_date: str, min_age_hours: int) -> bool:
    """
    Check if a commit is old enough to notify about.
    Returns True if the commit should be notified (i.e. it's >= min_age_hours old).
    """
    commit_dt = _parse_iso_date(commit_date)
    if commit_dt is None:
        # If we can't parse the date, err on the side of notifying
        logger.warning("Could not parse commit date '%s' - notifying anyway", commit_date)
        return True

    now = datetime.datetime.now(datetime.timezone.utc)
    age = now - commit_dt
    age_hours = age.total_seconds() / 3600

    logger.debug("Commit age: %.1f hours (min required: %d)", age_hours, min_age_hours)
    return age_hours >= min_age_hours


def check_repo(repo: str) -> CheckRepoResult:
    """
    Check a single repository for new commits.
    Returns either:
      (False, error_message) if something went wrong, or
      (True, None) if no new commit, or
      (True, commit_hash, reason, msg, author, date, url) on update.
    """
    state_file = config.get_state_file_path()

    commit_info = get_latest_commit(repo)
    if not commit_info:
        return (False, "Could not fetch commit data - check if repo exists and is public")

    commit_hash, commit_msg, author_name, commit_date, commit_url = commit_info

    last_hash = state_manager.get_last_seen(state_file, repo)

    if not last_hash:
        # First time seeing this repo
        logger.info("First time tracking %s - recording initial commit %s", repo, commit_hash[:7])
        state_manager.set_last_seen(state_file, repo, commit_hash)
        return (True, commit_hash, "first_seen", commit_msg, author_name, commit_date, commit_url)

    if commit_hash != last_hash:
        min_age_hours = config.get_min_commit_age_hours()

        if min_age_hours > 0 and not _is_commit_old_enough(commit_date, min_age_hours):
            logger.info(
                "New commit in %s (%s) is too young (%s) - deferring notification "
                "(min age: %dh)",
                repo, commit_hash[:7], commit_date, min_age_hours,
            )
            # Return (True, None) so the caller does nothing.
            # State is NOT updated, so this commit will be re-evaluated
            # on the next check cycle until it's old enough.
            return (True, None)

        logger.info(
            "New commit detected in %s: %s (was %s)", repo, commit_hash[:7], last_hash[:7]
        )
        return (True, commit_hash, "new_commit", commit_msg, author_name, commit_date, commit_url)
    else:
        logger.debug("No new commits for %s (current: %s)", repo, commit_hash[:7])
        return (True, None)


def confirm_notification(repo: str, commit_hash: str) -> None:
    """Persist a commit hash after a successful Discord notification."""
    state_file = config.get_state_file_path()
    state_manager.set_last_seen(state_file, repo, commit_hash)
    logger.info("Successfully updated state for %s -> %s", repo, commit_hash[:7])