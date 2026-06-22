"""
Tracks Discord notification messages per repository.
Stores repo -> channel_id:message_id in a simple flat file.
Format: repo:channel_id:message_id (one per line)

Only used when DELETE_PREVIOUS_NOTIFICATIONS is enabled.
"""

import os
from typing import Dict, Optional, Tuple


def _load(file_path: str) -> Dict[str, Tuple[int, int]]:
    """
    Load the notification tracking file.
    Returns a dict mapping repo -> (channel_id, message_id).
    """
    result: Dict[str, Tuple[int, int]] = {}
    if not os.path.isfile(file_path):
        return result

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split(":")
            if len(parts) == 3:
                repo = parts[0]
                try:
                    channel_id = int(parts[1])
                    message_id = int(parts[2])
                    if repo:
                        result[repo] = (channel_id, message_id)
                except ValueError:
                    continue
    return result


def _save(file_path: str, data: Dict[str, Tuple[int, int]]) -> None:
    """
    Write the notification tracking dict to a file.
    """
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# repo:channel_id:message_id — previous notification messages\n")
        for repo, (channel_id, message_id) in sorted(data.items()):
            f.write(f"{repo}:{channel_id}:{message_id}\n")


def get_notification_message(
    file_path: str, repo: str
) -> Optional[Tuple[int, int]]:
    """
    Get the stored channel_id and message_id for a repo's last notification.
    Returns (channel_id, message_id) or None if not tracked.
    """
    data = _load(file_path)
    return data.get(repo)


def set_notification_message(
    file_path: str, repo: str, channel_id: int, message_id: int
) -> None:
    """
    Update the tracked notification message for a repo.
    """
    data = _load(file_path)
    data[repo] = (channel_id, message_id)
    _save(file_path, data)


def remove_notification_message(file_path: str, repo: str) -> bool:
    """
    Remove a repo from notification tracking.
    Returns True if removed, False if not found.
    """
    data = _load(file_path)
    if repo not in data:
        return False
    del data[repo]
    _save(file_path, data)
    return True