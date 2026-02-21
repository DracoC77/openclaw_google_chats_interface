/**
 * OpenClaw Google Chat Skill
 *
 * Exposes tools that let the OpenClaw agent read, search, and send messages
 * in a Google Chat group via the sidecar service.
 *
 * The sidecar base URL defaults to http://google-chat-sidecar:3100 when
 * running inside Docker Compose (container DNS), or can be overridden with
 * the GOOGLE_CHAT_SIDECAR_URL environment variable.
 */

const SIDECAR_URL =
  process.env.GOOGLE_CHAT_SIDECAR_URL || "http://google-chat-sidecar:3100";

// ── Helpers ──────────────────────────────────────────────────────────

async function sidecarGet(path: string): Promise<any> {
  const res = await fetch(`${SIDECAR_URL}${path}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Sidecar ${path} returned ${res.status}: ${detail}`);
  }
  return res.json();
}

async function sidecarPost(path: string, body?: object): Promise<any> {
  const res = await fetch(`${SIDECAR_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Sidecar ${path} returned ${res.status}: ${detail}`);
  }
  return res.json();
}

/** Auto-boost polling whenever the skill is used. */
async function boost(): Promise<void> {
  try {
    await sidecarPost("/polling/boost");
  } catch {
    // Non-critical — don't fail the tool call
  }
}

interface Message {
  sender_name: string;
  text: string;
  created_at: string;
}

function formatMessages(messages: Message[]): string {
  if (messages.length === 0) return "No messages found.";
  return messages
    .map((m) => `[${m.created_at}] ${m.sender_name}: ${m.text}`)
    .join("\n");
}

// ── Tool Definitions ─────────────────────────────────────────────────
// These follow the OpenClaw tool/skill registration pattern.
// Adapt the export shape to match your OpenClaw version's extension API.

export const tools = {
  google_chat_read: {
    description:
      "Read recent messages from the Google Chat group. " +
      "Use this to catch up on what friends have been talking about.",
    parameters: {
      type: "object" as const,
      properties: {
        since: {
          type: "string",
          description:
            'ISO-8601 timestamp to fetch messages after, e.g. "2026-02-20T10:00:00Z". ' +
            "Omit for the most recent messages.",
        },
        limit: {
          type: "number",
          description: "Maximum number of messages to return (default 50).",
        },
      },
    },
    execute: async (params: { since?: string; limit?: number }) => {
      await boost();
      const query = new URLSearchParams();
      if (params.since) query.set("since", params.since);
      query.set("limit", String(params.limit || 50));
      const messages = await sidecarGet(`/messages?${query}`);
      return formatMessages(messages);
    },
  },

  google_chat_unread: {
    description:
      "Get unread messages from the Google Chat group since you last checked. " +
      "Automatically marks messages as read afterward.",
    parameters: { type: "object" as const, properties: {} },
    execute: async () => {
      await boost();
      const data = await sidecarGet("/messages/unread");
      if (data.messages?.length > 0) {
        await sidecarPost("/messages/mark-read");
      }
      return data.count === 0
        ? "No unread messages."
        : `${data.count} unread message(s):\n\n${formatMessages(data.messages)}`;
    },
  },

  google_chat_send: {
    description:
      "Send a message to the Google Chat group on behalf of the user. " +
      "The message will appear as coming from the user's Google account.",
    parameters: {
      type: "object" as const,
      properties: {
        text: {
          type: "string",
          description: "The message text to send.",
        },
      },
      required: ["text"],
    },
    execute: async (params: { text: string }) => {
      await boost();
      const result = await sidecarPost("/messages/send", { text: params.text });
      return `Message sent: "${result.message?.text || params.text}"`;
    },
  },

  google_chat_status: {
    description:
      "Check the status of the Google Chat integration — " +
      "whether it's authenticated, polling mode, unread count, etc.",
    parameters: { type: "object" as const, properties: {} },
    execute: async () => {
      const status = await sidecarGet("/status");
      const lines = [
        `Authenticated: ${status.authenticated ? "Yes" : "No — run /auth/url to set up"}`,
        `Space: ${status.space_id}`,
        `Poll mode: ${status.poll_mode}`,
        `Last poll: ${status.last_poll_at || "never"}`,
        `Total messages stored: ${status.message_count}`,
        `Unread: ${status.unread_count}`,
      ];
      return lines.join("\n");
    },
  },
};
