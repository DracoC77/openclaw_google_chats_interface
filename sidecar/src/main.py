"""FastAPI application entry point for the Google Chat sidecar."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI

from . import config
from .chat_api import list_messages
from .db import Database
from .poller import Poller
from .routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def poll_fn(db: Database) -> int:
    """Fetch new messages from Google Chat and store them.

    Returns the number of newly inserted messages.
    """
    latest = db.latest_message_time()
    after = datetime.fromisoformat(latest) if latest else None
    try:
        messages = list_messages(db, after=after)
    except RuntimeError:
        # Not authenticated yet — skip silently
        return 0
    if not messages:
        return 0
    return db.upsert_messages(messages)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    db = Database()
    poller = Poller(db, poll_fn)

    app.state.db = db
    app.state.poller = poller

    log.info("Space: %s", config.GOOGLE_CHAT_SPACE_ID)
    log.info("Active poll interval: %ds", config.POLL_ACTIVE_INTERVAL)
    log.info("Idle poll interval: %ds", config.POLL_IDLE_INTERVAL)
    log.info("Decay timeout: %ds", config.POLL_DECAY_TIMEOUT)

    await poller.start()
    yield
    await poller.stop()


app = FastAPI(
    title="Google Chat Sidecar",
    description="Sidecar service for OpenClaw Google Chat integration",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


def main():
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=config.SIDECAR_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
