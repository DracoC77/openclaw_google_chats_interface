# Google Chat Sidecar — Setup Guide

## Prerequisites

- Docker and Docker Compose installed
- A Google account that is a member of the target group chat
- A web browser for the one-time OAuth consent flow

---

## Step 1: Google Cloud Project

### If you already have a GCP project

1. Go to [APIs & Services > Library](https://console.cloud.google.com/apis/library)
2. Search for **Google Chat API** and click **Enable**
3. Skip to Step 2

### Starting from scratch

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it (e.g. `openclaw-google-chat`) and create it
4. In the sidebar go to **APIs & Services > Library**
5. Search for **Google Chat API** and click **Enable**

---

## Step 2: OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Choose **External** user type (required for consumer Gmail accounts)
3. Fill in the required fields:
   - **App name**: e.g. `OpenClaw Chat Bridge`
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/chat.spaces.readonly`
   - `https://www.googleapis.com/auth/chat.messages`
   - `https://www.googleapis.com/auth/chat.messages.create`
6. Click **Save and Continue**
7. On the **Test users** page, add your Gmail address
8. Click **Save and Continue** → **Back to Dashboard**

> **Note**: While the app is in "Testing" mode, only the test users you added
> can complete the OAuth flow. This is fine for personal use.

---

## Step 3: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Web application**
4. Name: e.g. `OpenClaw Chat Sidecar`
5. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:3100/auth/callback
   ```
6. Click **Create**
7. Copy the **Client ID** and **Client Secret**

---

## Step 4: Find Your Google Chat Space ID

The space ID identifies which group chat to monitor.

### Option A: From the URL

1. Open [Google Chat](https://mail.google.com/chat/) in a browser
2. Navigate to your group chat
3. Look at the URL — it will contain something like:
   ```
   https://mail.google.com/chat/u/0/#chat/space/AAAA_BBBBBB
   ```
4. Your space ID is `spaces/AAAA_BBBBBB`

### Option B: Using the API (after auth setup)

After completing the OAuth flow (Step 6), you can list your spaces:
```bash
curl http://localhost:3100/status
```

---

## Step 5: Configure Environment

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your values:
   ```env
   GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxx
   GOOGLE_CHAT_SPACE_ID=spaces/AAAA_BBBBBB
   ```

---

## Step 6: Start the Sidecar

```bash
docker compose up -d
```

Check that it's running:
```bash
docker compose logs google-chat-sidecar
```

You should see the FastAPI server start on port 3100.

---

## Step 7: Complete OAuth Flow (One-Time)

1. Get the consent URL:
   ```bash
   curl http://localhost:3100/auth/url
   ```
   This returns a JSON object with a `url` field.

2. Open that URL in your browser

3. Sign in with your Google account and grant the requested permissions

4. Google redirects to `http://localhost:3100/auth/callback?code=...`

5. You should see: `{"status": "authenticated", "message": "OAuth setup complete..."}`

6. Verify it worked:
   ```bash
   curl http://localhost:3100/status
   ```
   `authenticated` should be `true`.

---

## Step 8: Connect to OpenClaw

### Option A: Shared Docker network

If OpenClaw runs in Docker, put both services on the same network:

```yaml
# In your OpenClaw docker-compose.yml, add:
networks:
  default:
    name: openclaw-network

# In this project's docker-compose.yml, add:
networks:
  default:
    name: openclaw-network
    external: true
```

The skill can then reach the sidecar at `http://google-chat-sidecar:3100`.

### Option B: Host networking

If OpenClaw runs on the host, the sidecar is already accessible at
`http://localhost:3100`.

### Installing the skill

Copy or symlink the `skill/` directory into your OpenClaw extensions path:

```bash
# Example — adjust to your OpenClaw setup
cp -r skill/ /path/to/openclaw/extensions/google-chat/
```

Set the sidecar URL if not using Docker DNS:
```bash
export GOOGLE_CHAT_SIDECAR_URL=http://localhost:3100
```

---

## Verify Everything Works

Ask your OpenClaw agent:

> "Check my Google Chat — what have I missed?"

The agent should invoke `google_chat_unread` and return your recent messages.

Try sending:

> "Tell my friends I'll be 10 minutes late"

The agent should invoke `google_chat_send` with an appropriate message.

---

## Troubleshooting

### "Not authenticated" errors
Re-run the OAuth flow (Step 7). The refresh token may have been revoked.

### No messages returned
- Verify the space ID is correct: `curl http://localhost:3100/status`
- Check that the authenticated account is a member of the target space
- Consumer Google Chat API access can be limited — check GCP Console for API errors

### Token refresh failures
Google OAuth refresh tokens for apps in "Testing" mode expire after 7 days.
To avoid this, publish the app (even as internal-only if using Workspace) or
re-authorize periodically.

### Container can't reach Google APIs
Ensure the Docker container has internet access. Check DNS resolution:
```bash
docker compose exec google-chat-sidecar python -c "import urllib.request; print(urllib.request.urlopen('https://www.googleapis.com').status)"
```
