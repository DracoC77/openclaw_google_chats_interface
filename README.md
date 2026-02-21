# OpenClaw Google Chat Interface

A sidecar service + OpenClaw skill that lets your OpenClaw agent read and send
messages in a Google Chat group.

## What It Does

- **Read messages**: "What did I miss in the group chat?"
- **Catch up**: "Summarize today's conversation"
- **Reply**: "Tell them I'll be there at 7"
- **Check status**: "Is the chat integration connected?"

Messages appear as coming from your Google account (via User OAuth).

## Architecture

```
┌──────────────┐  HTTP   ┌────────────────────────┐
│   OpenClaw   │◄───────►│  Google Chat Sidecar    │
│   (skill)    │  :3100  │  (Python + SQLite)      │
└──────────────┘         └──────────┬─────────────┘
                                    │ Google Chat API
                                    ▼
                             Your Group Chat
```

**Sidecar** (Python/FastAPI): Handles Google OAuth, polls for messages, stores
history in SQLite, exposes a REST API.

**Skill** (TypeScript): Thin OpenClaw extension that gives the agent tools to
call the sidecar.

**Adaptive polling**: Polls every 30s when you're actively chatting with the
agent, decays to every 4h when idle.

## Quick Start

```bash
# 1. Configure
cp .env.example .env
# Edit .env with your Google OAuth credentials and space ID

# 2. Start the sidecar
docker compose up -d

# 3. Complete OAuth (one-time)
curl http://localhost:3100/auth/url
# Open the returned URL in your browser and grant consent

# 4. Install the skill into OpenClaw
cp -r skill/ /path/to/openclaw/extensions/google-chat/
```

See [setup-guide.md](setup-guide.md) for detailed instructions including GCP
project setup.

## Project Structure

```
├── sidecar/              Python sidecar service
│   ├── src/
│   │   ├── main.py       FastAPI app entry point
│   │   ├── auth.py       OAuth flow + token management
│   │   ├── chat_api.py   Google Chat API wrapper
│   │   ├── db.py         SQLite storage
│   │   ├── poller.py     Adaptive polling engine
│   │   ├── routes.py     REST API handlers
│   │   └── config.py     Environment variable config
│   ├── Dockerfile
│   └── requirements.txt
├── skill/                OpenClaw skill extension
│   └── src/
│       └── index.ts      Tool definitions
├── docker-compose.yml
├── .env.example
└── setup-guide.md
```

## Sidecar API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/messages` | Fetch messages (query: `since`, `limit`, `sender`) |
| GET | `/messages/unread` | Messages since last read marker |
| POST | `/messages/mark-read` | Advance the read marker |
| POST | `/messages/send` | Send a message (`{"text": "..."}`) |
| POST | `/polling/boost` | Switch to active polling |
| GET | `/status` | Health and connection info |
| GET | `/auth/url` | Get OAuth consent URL |
| GET | `/auth/callback` | OAuth redirect handler |

## Agent Tools

| Tool | Description |
|------|-------------|
| `google_chat_read` | Read recent messages (optionally filtered by time) |
| `google_chat_unread` | Get unread messages, auto-marks as read |
| `google_chat_send` | Send a message to the group chat |
| `google_chat_status` | Check integration status |

## License

MIT
