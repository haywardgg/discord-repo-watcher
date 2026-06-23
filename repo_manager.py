"""
Manages the list of watched repositories.
Repositories are stored in a text file (one per line, lines starting with # are ignored).
Format: owner/repo <user_id>  (user_id optional for backward compatibility)
"""

import os
import re
from typing import Dict, List, Optional


def clean_repo(input_str: str) -> str:
    """
    Normalize a repo string to 'owner/name' format.
    Handles: https://github.com/owner/repo, github.com/owner/repo.git, owner/repo, etc.
    Strips trailing user IDs (e.g. 'owner/repo 12345' -> 'owner/repo').
    """
    repo = input_str.strip()
    # Strip trailing user ID if present
    parts = repo.rsplit(None, 1)
    if len(parts) == 2 and parts[1].isdigit():
        repo = parts[0]
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
    Returns a list of cleaned owner/repo strings (user IDs stripped).
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


def load_repos_with_owners(file_path: str) -> Dict[str, Optional[int]]:
    """
    Load repository list with owner user IDs.
    Returns a dict of {repo: user_id} where user_id is an int, or None for ownerless repos.
    """
    repos: Dict[str, Optional[int]] = {}
    if not os.path.isfile(file_path):
        return repos

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Extract repo and optional user ID
            parts = stripped.rsplit(None, 1)
            user_id: Optional[int] = None
            if len(parts) == 2 and parts[1].isdigit():
                repo_str = parts[0]
                user_id = int(parts[1])
            else:
                repo_str = stripped
            cleaned = clean_repo(repo_str)
            if cleaned and re.match(r"^[\w.-]+/[\w.-]+$", cleaned):
                repos[cleaned] = user_id
    return repos


def get_repo_owner(file_path: str, repo: str) -> Optional[int]:
    """
    Get the Discord user ID that added a repository.
    Returns the user ID (int), or None if the repo has no owner or doesn't exist.
    """
    repos = load_repos_with_owners(file_path)
    return repos.get(clean_repo(repo))


def save_repos(file_path: str, repos: Dict[str, Optional[int]]) -> None:
    """
    Write the repository list to a file, preserving the header comment.
    repos is a dict of {repo: user_id} where user_id can be None.
    """
    header = (
        "# Add one repository per line in the format: <owner>/<repo-name> [<user-id>]\n"
        "#\n"
        "# Lines starting with # are ignored.\n"
        "# The optional user ID tracks who added the repo for ownership-based removal.\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(header)
        for repo in sorted(repos):
            uid = repos[repo]
            if uid is not None:
                f.write(f"{repo} {uid}\n")
            else:
                f.write(f"{repo}\n")


def add_repo(file_path: str, repo: str, user_id: Optional[int] = None) -> bool:
    """
    Add a repository to the list with an optional user ID for ownership tracking.
    Returns True if added, False if it already exists.
    """
    repo = clean_repo(repo)
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        raise ValueError(
            f"Invalid repository format: '{repo}'. Use <owner>/<repo> format."
        )

    current = load_repos_with_owners(file_path)
    if repo in current:
        return False  # Already exists

    current[repo] = user_id
    save_repos(file_path, current)
    return True


def remove_repo(file_path: str, repo: str) -> bool:
    """
    Remove a repository from the list.
    Returns True if removed, False if not found.
    """
    repo = clean_repo(repo)
    current = load_repos_with_owners(file_path)
    if repo not in current:
        return False

    del current[repo]
    save_repos(file_path, current)
    return True