"""FastAPI route handlers for the sidecar REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from . import config
from .auth import build_consent_url, exchange_code
from .chat_api import get_space_info, send_message as api_send_message

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Pydantic models ----------

class SendBody(BaseModel):
    text: str


class MarkReadBody(BaseModel):
    timestamp: str | None = None


# ---------- Messages ----------

@router.get("/messages")
def get_messages(
    request: Request,
    since: str | None = Query(None, description="ISO-8601 timestamp"),
    limit: int = Query(100, ge=1, le=1000),
    sender: str | None = Query(None),
) -> list[dict[str, Any]]:
    _touch_skill(request)
    return request.app.state.db.get_messages(since=since, limit=limit, sender=sender)


@router.get("/messages/unread")
def get_unread(request: Request) -> dict[str, Any]:
    _touch_skill(request)
    db = request.app.state.db
    messages = db.get_unread_messages()
    return {"count": len(messages), "messages": messages}


@router.post("/messages/mark-read")
def mark_read(request: Request, body: MarkReadBody | None = None) -> dict[str, str]:
    ts = body.timestamp if body else None
    marker = request.app.state.db.mark_read(ts)
    return {"read_marker": marker}


@router.post("/messages/send")
def send_chat_message(request: Request, body: SendBody) -> dict[str, Any]:
    _touch_skill(request)
    db = request.app.state.db
    try:
        msg = api_send_message(db, body.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    # Also store the sent message locally
    db.upsert_messages([{**msg, "fetched_at": datetime.now(timezone.utc).isoformat()}])
    return {"status": "sent", "message": msg}


# ---------- Polling control ----------

@router.post("/polling/boost")
def boost_polling(request: Request) -> dict[str, str]:
    _touch_skill(request)
    return {"poll_mode": "active"}


# ---------- Status ----------

@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    db = request.app.state.db
    poller = request.app.state.poller
    return {
        "authenticated": db.get_auth("refresh_token") is not None,
        "space_id": config.GOOGLE_CHAT_SPACE_ID,
        "poll_mode": poller.mode if poller else "unknown",
        "last_poll_at": db.get_state("last_poll_at"),
        "message_count": db.message_count(),
        "unread_count": db.unread_count(),
    }


# ---------- Auth ----------

@router.get("/auth/url")
def auth_url() -> dict[str, str]:
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.",
        )
    return {"url": build_consent_url()}


@router.get("/auth/callback")
def auth_callback(request: Request, code: str = Query(...)) -> dict[str, str]:
    db = request.app.state.db
    try:
        tokens = exchange_code(code)
    except Exception as exc:
        log.exception("Token exchange failed")
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    db.set_auth("refresh_token", tokens["refresh_token"])
    db.set_auth("access_token", tokens["access_token"])
    db.set_auth("token_expiry", tokens["token_expiry"])

    return {"status": "authenticated", "message": "OAuth setup complete. You can close this tab."}


# ---------- Internal helpers ----------

def _touch_skill(request: Request) -> None:
    """Record that the skill made a request — used by the poller to boost."""
    poller = request.app.state.poller
    if poller:
        poller.touch()
