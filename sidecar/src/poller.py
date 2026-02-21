"""Adaptive polling engine for Google Chat messages.

State machine:
    IDLE  ──(skill call)──►  ACTIVE
    (4h)                     (30-60s)
     ▲                          │
     └──(10min no calls)────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum

from . import config

log = logging.getLogger(__name__)


class PollMode(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"


class Poller:
    """Background polling loop with adaptive frequency."""

    def __init__(self, db, poll_fn):
        """
        Args:
            db: Database instance for state persistence.
            poll_fn: Callable that fetches new messages and stores them.
                     Signature: poll_fn(db) -> int (number of new messages).
        """
        self.db = db
        self.poll_fn = poll_fn
        self._mode = PollMode.IDLE
        self._last_skill_touch: float = 0.0
        self._task: asyncio.Task | None = None

    @property
    def mode(self) -> str:
        return self._mode.value

    def touch(self) -> None:
        """Called when the skill makes a request — boosts to ACTIVE."""
        self._last_skill_touch = time.monotonic()
        if self._mode != PollMode.ACTIVE:
            log.info("Polling boosted to ACTIVE")
            self._mode = PollMode.ACTIVE

    async def start(self) -> None:
        """Start the background polling loop."""
        self._task = asyncio.create_task(self._loop())
        log.info("Poller started in %s mode", self._mode.value)

    async def stop(self) -> None:
        """Cancel the background task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            log.info("Poller stopped")

    async def _loop(self) -> None:
        while True:
            # Determine current interval
            interval = self._current_interval()

            # Check for decay: ACTIVE → IDLE after timeout
            if self._mode == PollMode.ACTIVE and self._last_skill_touch > 0:
                elapsed = time.monotonic() - self._last_skill_touch
                if elapsed > config.POLL_DECAY_TIMEOUT:
                    log.info(
                        "No skill activity for %ds, decaying to IDLE",
                        int(elapsed),
                    )
                    self._mode = PollMode.IDLE
                    interval = config.POLL_IDLE_INTERVAL

            # Poll
            try:
                new_count = await asyncio.to_thread(self.poll_fn, self.db)
                self.db.set_state(
                    "last_poll_at",
                    datetime.now(timezone.utc).isoformat(),
                )
                if new_count > 0:
                    log.info("Fetched %d new message(s)", new_count)
            except Exception:
                log.exception("Poll cycle failed")

            await asyncio.sleep(interval)

    def _current_interval(self) -> int:
        if self._mode == PollMode.ACTIVE:
            return config.POLL_ACTIVE_INTERVAL
        return config.POLL_IDLE_INTERVAL
