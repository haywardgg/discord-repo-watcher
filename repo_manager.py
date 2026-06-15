"""
Manages the list of watched repositories.
Repositories are stored in a text file (one per line, lines starting with # are ignored).
Compatible with the original bash script's repos.txt format.
"""

import os
import re
from typing import List


def clean_repo(input_str: str) -> str:
    """
    Normalize a repo string to 'owner/name' format.
    Handles: https://github.com/owner/repo, github.com/owner/repo.git, owner/repo, etc.
    """
    repo = input_str.strip()
    # Remove URL prefixes
    for prefix in ["https://github.com/", "http://github.com/", "github.com/"]:
        if repo.startswith(prefix):
            repo = repo[len(prefix):]
    # Remove .git suffix
    if repo.endswith(".git"):
        repo = repo[:-4]
    # Remove trailing slashes
    repo = repo.rstrip("/")
    # Remove quotes
    repo = repo.replace('"', "").replace("'", "")
    # Remove newlines/carriage returns
    repo = repo.replace("\n", "").replace("\r", "")
    return repo.strip()


def load_repos(file_path: str) -> List[str]:
    """
    Load repository list from a file.
    Returns a list of cleaned owner/repo strings.
    Skips empty lines and lines starting with #.
    """
    repos: List[str] = []
    if not os.path.isfile(file_path):
        return repos

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue
            cleaned = clean_repo(stripped)
            if cleaned and re.match(r"^[\w.-]+/[\w.-]+$", cleaned):
                repos.append(cleaned)
    return repos


def save_repos(file_path: str, repos: List[str]) -> None:
    """
    Write the repository list to a file, preserving the header comment.
    """
    header = (
        "# Add one repository per line in the format: <owner>/<repo-name>\n"
        "#\n"
        "# Lines starting with # are ignored.\n"
        "# Acceptable formats: owner/repo, https://github.com/owner/repo, github.com/owner/repo.git\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(header)
        for repo in repos:
            f.write(f"{repo}\n")


def add_repo(file_path: str, repo: str) -> bool:
    """
    Add a repository to the list.
    Returns True if added, False if it already exists.
    """
    repo = clean_repo(repo)
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        raise ValueError(
            f"Invalid repository format: '{repo}'. Use <owner>/<repo> format."
        )

    current = load_repos(file_path)
    if repo in current:
        return False  # Already exists

    current.append(repo)
    save_repos(file_path, sorted(current))
    return True


def remove_repo(file_path: str, repo: str) -> bool:
    """
    Remove a repository from the list.
    Returns True if removed, False if not found.
    """
    repo = clean_repo(repo)
    current = load_repos(file_path)
    if repo not in current:
        return False

    current.remove(repo)
    save_repos(file_path, sorted(current))
    return True