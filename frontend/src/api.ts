export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

type ValidationErrorItem = { msg?: string };

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "msg" in item) {
          let msg = String((item as ValidationErrorItem).msg ?? "");
          if (msg.startsWith("Value error, ")) {
            msg = msg.slice("Value error, ".length);
          }
          return msg;
        }
        return null;
      })
      .filter((item): item is string => Boolean(item));
    return messages.join("; ") || "Ошибка запроса";
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Ошибка запроса";
}

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
    let message = text || "Ошибка запроса";
    try {
      const payload = JSON.parse(text) as { detail?: unknown };
      if (payload.detail !== undefined) {
        message = formatApiErrorDetail(payload.detail);
      }
    } catch {
      message = text || "Ошибка запроса";
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function apiUploadFile<T>(path: string, file: File): Promise<T> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: form });
  if (!response.ok) {
    const text = await response.text();
    let message = text || "Ошибка запроса";
    try {
      const payload = JSON.parse(text) as { detail?: unknown };
      if (payload.detail !== undefined) {
        message = formatApiErrorDetail(payload.detail);
      }
    } catch {
      message = text || "Ошибка запроса";
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function downloadAuthenticatedFile(path: string, fileName: string): Promise<void> {
  const token = localStorage.getItem("token");
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Не удалось скачать файл");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
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
