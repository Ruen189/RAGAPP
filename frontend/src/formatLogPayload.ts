const DATA_IMAGE_URL_RE = /^data:image\/([\w+.-]+);base64,/i;
const FULL_TEXT_KEYS = new Set(["response", "text", "query", "answer", "message", "content", "error", "delta"]);

export type LogDisplayInput = {
  trace_id: string;
  user_id: string;
  conversation_id: string;
  message_id: string;
  created_at: string;
  payload: Record<string, unknown>;
};

function shortenImageDataUrl(value: string): string {
  const match = value.match(DATA_IMAGE_URL_RE);
  if (match) {
    return match[1];
  }
  if (value.startsWith("data:")) {
    const mimeEnd = value.indexOf(";");
    const slash = value.indexOf("/");
    if (mimeEnd > slash) {
      return value.slice(slash + 1, mimeEnd);
    }
  }
  return value;
}

function sanitizeLogString(value: string, keyHint?: string): string {
  const shortenedImage = shortenImageDataUrl(value);
  if (shortenedImage !== value) {
    return shortenedImage;
  }
  if (keyHint === "prompt" && value.length > 120) {
    return `[prompt, ${value.length} chars]`;
  }
  if (keyHint && FULL_TEXT_KEYS.has(keyHint)) {
    return value;
  }
  if (value.length > 800) {
    return `[${value.length} chars]`;
  }
  return value;
}

export function sanitizeForLogDisplay(value: unknown, keyHint?: string): unknown {
  if (typeof value === "string") {
    return sanitizeLogString(value, keyHint);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForLogDisplay(item));
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const next: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(record)) {
      if (key === "value" && record.kind === "image" && typeof nested === "string") {
        next[key] = shortenImageDataUrl(nested);
        continue;
      }
      next[key] = sanitizeForLogDisplay(nested, key);
    }
    return next;
  }
  return value;
}

export function prepareLogForDisplay(row: LogDisplayInput): Record<string, unknown> {
  const merged = {
    trace_id: row.trace_id,
    user_id: row.user_id,
    conversation_id: row.conversation_id,
    message_id: row.message_id,
    created_at: row.created_at,
    ...row.payload,
  };
  return sanitizeForLogDisplay(merged) as Record<string, unknown>;
}
