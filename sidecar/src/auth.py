"""OAuth 2.0 flow for Google Chat API with User credentials.

Handles:
  - Generating the consent URL for initial browser-based auth
  - Exchanging the auth code for tokens
  - Persisting tokens in SQLite
  - Auto-refreshing expired access tokens
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from . import config

log = logging.getLogger(__name__)


def _make_client_config() -> dict:
    return {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [config.OAUTH_REDIRECT_URI],
        }
    }


def build_consent_url() -> str:
    """Return the URL the user should open in a browser to grant consent."""
    flow = Flow.from_client_config(
        _make_client_config(),
        scopes=config.SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    return url


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for tokens. Returns a dict with
    refresh_token, access_token, and expiry (ISO-8601)."""
    flow = Flow.from_client_config(
        _make_client_config(),
        scopes=config.SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "refresh_token": creds.refresh_token,
        "access_token": creds.token,
        "token_expiry": creds.expiry.isoformat() if creds.expiry else "",
        "token_scopes": json.dumps(list(creds.scopes or [])),
    }


def load_credentials(db) -> Credentials | None:
    """Load credentials from the database and refresh if expired.

    Returns a valid Credentials object, or None if no tokens are stored.
    Automatically persists refreshed tokens back to the database.
    """
    refresh_token = db.get_auth("refresh_token")
    if not refresh_token:
        return None

    access_token = db.get_auth("access_token")
    expiry_raw = db.get_auth("token_expiry")
    expiry = datetime.fromisoformat(expiry_raw) if expiry_raw else None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        scopes=config.SCOPES,
    )
    if expiry:
        creds.expiry = expiry

    if creds.expired or not creds.valid:
        log.info("Access token expired, refreshing...")
        creds.refresh(Request())
        db.set_auth("access_token", creds.token)
        if creds.expiry:
            db.set_auth("token_expiry", creds.expiry.isoformat())
        log.info("Token refreshed successfully.")

    return creds
