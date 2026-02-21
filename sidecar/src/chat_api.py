"""Google Chat API wrapper.

Thin layer over the Google Chat REST API using the `googleapiclient` library
and user OAuth credentials.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build

from . import config
from .auth import load_credentials

log = logging.getLogger(__name__)


def _get_service(db):
    """Build and return an authenticated Chat API service."""
    creds = load_credentials(db)
    if creds is None:
        raise RuntimeError(
            "Not authenticated. Complete the OAuth flow via /auth/url first."
        )
    return build("chat", "v1", credentials=creds)


def get_space_info(db) -> dict[str, Any]:
    """Return metadata for the configured space."""
    svc = _get_service(db)
    space = svc.spaces().get(name=config.GOOGLE_CHAT_SPACE_ID).execute()
    return {
        "name": space.get("name"),
        "display_name": space.get("displayName"),
        "type": space.get("spaceType"),
    }


def list_messages(
    db,
    *,
    after: datetime | None = None,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Fetch messages from the configured space.

    Args:
        after: Only return messages created after this timestamp.
        page_size: Max messages per page (Google caps at 1000).

    Returns a list of normalised message dicts, oldest first.
    """
    svc = _get_service(db)
    all_messages: list[dict[str, Any]] = []
    page_token: str | None = None

    # Google Chat API filter for messages after a timestamp
    filter_str = ""
    if after:
        ts = after.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        filter_str = f'createTime > "{ts}"'

    while True:
        kwargs: dict[str, Any] = {
            "parent": config.GOOGLE_CHAT_SPACE_ID,
            "pageSize": min(page_size, 1000),
        }
        if filter_str:
            kwargs["filter"] = filter_str
        if page_token:
            kwargs["pageToken"] = page_token

        resp = svc.spaces().messages().list(**kwargs).execute()
        for msg in resp.get("messages", []):
            all_messages.append(_normalize(msg))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # API returns newest first; reverse so oldest is first
    all_messages.reverse()
    return all_messages


def send_message(db, text: str) -> dict[str, Any]:
    """Send a text message to the configured space as the authenticated user.

    Returns the normalised sent message.
    """
    svc = _get_service(db)
    msg = (
        svc.spaces()
        .messages()
        .create(
            parent=config.GOOGLE_CHAT_SPACE_ID,
            body={"text": text},
        )
        .execute()
    )
    return _normalize(msg)


def _normalize(msg: dict[str, Any]) -> dict[str, Any]:
    """Flatten a raw Google Chat message into our internal format."""
    sender = msg.get("sender", {})
    return {
        "id": msg.get("name", ""),
        "sender_name": sender.get("displayName", "Unknown"),
        "sender_email": sender.get("email", ""),
        "text": msg.get("text", ""),
        "created_at": msg.get("createTime", ""),
    }
