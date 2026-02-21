# Google Chat Interface for OpenClaw — Implementation Plan

## Architecture: Hybrid Sidecar (Python) + OpenClaw Skill (TypeScript)

### Decisions
- **Sidecar**: Python + FastAPI, runs as a Docker sidecar container
- **Skill**: TypeScript, volume-mounted into OpenClaw container
- **Storage**: SQLite (single file on Docker volume)
- **Auth**: Google User OAuth (consumer Gmail — messages appear as the user)
- **Polling**: Adaptive (idle: every 4h, active: every 30–60s, decays after 10min)
- **Scope**: Single configured group chat (space ID)

---

## Phase 1: Sidecar — OAuth + Google Chat API Client

**Files:**
- `sidecar/src/auth.py` — OAuth flow (generate consent URL, handle callback, store/refresh tokens)
- `sidecar/src/chat_api.py` — Google Chat API wrapper (list messages, send message, get space info)

**Details:**
- OAuth scopes: `chat.spaces.readonly`, `chat.messages`, `chat.messages.create`
- Token storage: SQLite `auth` table (refresh_token, access_token, expiry)
- First-run flow: sidecar exposes `GET /auth/url` → user opens in browser → consents → redirect to `GET /auth/callback` → tokens stored
- Auto-refresh access token on expiry using stored refresh token
- Chat API client methods:
  - `list_messages(space_id, after=None, page_size=100)` → list of messages
  - `send_message(space_id, text)` → send message as authenticated user
  - `get_space(space_id)` → space metadata

## Phase 2: Sidecar — SQLite Storage + REST API

**Files:**
- `sidecar/src/db.py` — SQLite schema, message CRUD, read marker, dedup
- `sidecar/src/routes.py` — FastAPI route handlers
- `sidecar/src/main.py` — App entry point, lifespan events

**SQLite Schema:**
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,          -- Google Chat message name/ID
    sender_name TEXT NOT NULL,    -- Display name of sender
    sender_email TEXT,            -- Email if available
    text TEXT NOT NULL,           -- Message content
    created_at TEXT NOT NULL,     -- ISO8601 timestamp
    fetched_at TEXT NOT NULL      -- When we fetched it
);

CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Keys: 'last_poll_at', 'read_marker' (message timestamp), 'poll_mode'

CREATE TABLE auth (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Keys: 'refresh_token', 'access_token', 'token_expiry'
```

**REST API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/messages` | Fetch messages. Query params: `since` (ISO8601), `limit` (int), `sender` (filter) |
| GET | `/messages/unread` | Messages since last read marker |
| POST | `/messages/mark-read` | Update read marker to now (or to a specific timestamp) |
| POST | `/messages/send` | Body: `{ "text": "..." }` — send to configured space |
| POST | `/polling/boost` | Switch to active polling mode |
| GET | `/status` | Health, poll mode, last poll time, unread count, space info |
| GET | `/auth/url` | Get OAuth consent URL for initial setup |
| GET | `/auth/callback` | OAuth callback (receives auth code, exchanges for tokens) |

## Phase 3: Sidecar — Adaptive Polling Engine

**Files:**
- `sidecar/src/poller.py` — Polling state machine with asyncio background task

**State Machine:**
```
         boost (skill call)
  IDLE ──────────────────► ACTIVE
  (4h)                     (30-60s)
   ▲                          │
   │    10min no skill calls  │
   └──────────────────────────┘
            decay
```

- On startup: enter IDLE mode
- Any REST call from the skill → reset decay timer, enter ACTIVE if not already
- `POST /polling/boost` → explicitly enter ACTIVE
- ACTIVE polls every 30s (configurable)
- After 10min without any skill interaction → decay to IDLE
- IDLE polls every 4h (configurable, or disabled entirely)
- Each poll: fetch new messages since last stored message, insert into SQLite, update `last_poll_at`
- Dedup by message ID (INSERT OR IGNORE)

## Phase 4: OpenClaw Skill

**Files:**
- `skill/package.json`
- `skill/src/index.ts` — Tool definitions that call sidecar REST API

**Tools exposed to agent:**
1. **`google_chat_read`** — Read recent messages
   - Params: `since` (optional, e.g. "2h ago", "today"), `limit` (default 50)
   - Returns: Formatted message history
   - Side effect: boosts polling

2. **`google_chat_unread`** — Get messages since last read
   - No params
   - Returns: Unread messages, marks as read
   - Side effect: boosts polling

3. **`google_chat_send`** — Send a message as the user
   - Params: `text` (required)
   - Returns: Confirmation + sent message

4. **`google_chat_status`** — Check connection status
   - Returns: Unread count, last poll time, polling mode, space name

Each tool auto-calls `/polling/boost` to ensure fresh data during active agent sessions.

## Phase 5: Docker Compose + Configuration

**Files:**
- `docker-compose.yml` — Sidecar service definition
- `sidecar/Dockerfile` — Python image
- `.env.example` — Template for required env vars

**Environment Variables:**
```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_CHAT_SPACE_ID=spaces/...
SIDECAR_PORT=3100
POLL_ACTIVE_INTERVAL=30
POLL_IDLE_INTERVAL=14400
POLL_DECAY_TIMEOUT=600
```

**Docker Compose:**
- Sidecar container on internal network with OpenClaw
- Named volume for SQLite DB + auth tokens (persists across restarts/rebuilds)
- Port 3100 exposed only on internal Docker network (not host)

## Phase 6: Setup Guide

**File:** `setup-guide.md`

Two paths:
1. **Fresh GCP Project**: Create project → enable Chat API → configure OAuth consent screen → create credentials → set redirect URI
2. **Existing GCP Project**: Enable Chat API → create OAuth credentials → set redirect URI

Plus:
- First-run OAuth flow walkthrough
- Docker compose startup instructions
- How to find your Google Chat space ID
- Troubleshooting common issues

---

## File Tree (Final)
```
openclaw_google_chats_interface/
├── sidecar/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py           # FastAPI app, lifespan, entry point
│       ├── auth.py           # OAuth flow + token management
│       ├── chat_api.py       # Google Chat API wrapper
│       ├── db.py             # SQLite schema + queries
│       ├── poller.py         # Adaptive polling state machine
│       ├── routes.py         # REST API handlers
│       └── config.py         # Environment variable config
├── skill/
│   ├── package.json
│   └── src/
│       └── index.ts          # OpenClaw tool definitions
├── docker-compose.yml
├── .env.example
├── setup-guide.md
└── README.md
```

## Implementation Order
1. Phase 1 (OAuth + Chat API) — foundation everything depends on
2. Phase 2 (SQLite + REST API) — makes the sidecar functional
3. Phase 3 (Adaptive poller) — background intelligence
4. Phase 5 (Docker Compose) — containerize and test end-to-end
5. Phase 4 (OpenClaw Skill) — connect to the agent
6. Phase 6 (Setup Guide) — documentation
