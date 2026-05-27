export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      message = payload.detail || text;
    } catch {
      message = text;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function streamJob(
  jobId: string,
  onEvent: (payload: any) => void
): Promise<{ close: () => void }> {
  const token = localStorage.getItem("token");
  const controller = new AbortController();
  const response = await fetch(`${API_BASE}/api/chat/stream/${jobId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: controller.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error("SSE connection failed");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const pump = async () => {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const rawEvent of events) {
        const line = rawEvent.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const data = line.replace("data: ", "");
        try {
          onEvent(JSON.parse(data));
        } catch {
          onEvent(data);
        }
      }
    }
  };
  void pump();

  return {
    close: () => controller.abort(),
  };
}
