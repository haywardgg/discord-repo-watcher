"""
Manages the state file that tracks the last-seen commit hash per repository.
Compatible with the original bash script's .repo-state format.
Format: owner/repo:commit_hash (one per line)
"""

import os
from typing import Dict


def load_state(file_path: str) -> Dict[str, str]:
    """
    Load the state file and return a dict mapping repo -> last_seen_commit_hash.
    Returns an empty dict if the file doesn't exist.
    """
    state: Dict[str, str] = {}
    if not os.path.isfile(file_path):
        return state

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped:
                repo, _, commit_hash = stripped.partition(":")
                if repo and commit_hash:
                    state[repo] = commit_hash
    return state


def save_state(file_path: str, state: Dict[str, str]) -> None:
    """
    Write the state dict to a file.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        for repo, commit_hash in sorted(state.items()):
            f.write(f"{repo}:{commit_hash}\n")


def get_last_seen(file_path: str, repo: str) -> str:
    """
    Get the last-seen commit hash for a repository.
    Returns empty string if not found.
    """
    state = load_state(file_path)
    return state.get(repo, "")


def set_last_seen(file_path: str, repo: str, commit_hash: str) -> None:
    """
    Update the last-seen commit hash for a repository.
    """
    state = load_state(file_path)
    state[repo] = commit_hash
    save_state(file_path, state)


def remove_repo(file_path: str, repo: str) -> bool:
    """
    Remove a repository from the state file.
    Returns True if removed, False if not found.
    """
    state = load_state(file_path)
    if repo not in state:
        return False
    del state[repo]
    save_state(file_path, state)
    return True