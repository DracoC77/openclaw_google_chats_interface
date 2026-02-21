"""Configuration loaded from environment variables."""

import os


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_CHAT_SPACE_ID = os.environ.get("GOOGLE_CHAT_SPACE_ID", "")

# OAuth redirect — during initial setup the user visits /auth/url in a browser,
# consents, and Google redirects back here with an auth code.
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI", "http://localhost:3100/auth/callback"
)

SIDECAR_PORT = int(os.environ.get("SIDECAR_PORT", "3100"))

# Polling intervals (seconds)
POLL_ACTIVE_INTERVAL = int(os.environ.get("POLL_ACTIVE_INTERVAL", "30"))
POLL_IDLE_INTERVAL = int(os.environ.get("POLL_IDLE_INTERVAL", "14400"))  # 4 hours
POLL_DECAY_TIMEOUT = int(os.environ.get("POLL_DECAY_TIMEOUT", "600"))  # 10 minutes

# SQLite database path — should be on a Docker volume for persistence
DB_PATH = os.environ.get("DB_PATH", "/data/google_chat.db")

SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.messages.create",
]
