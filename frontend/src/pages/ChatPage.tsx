import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, streamJob } from "../api";
import { MarkdownMessage } from "../MarkdownMessage";

type Conversation = { id: string; title: string };
type Message = { id: string; role: "user" | "assistant" | "system"; content: string };
type RetrievalResult = { document_id: string; chunk_id: string; score: number };
type Capabilities = { model_hf: string; multimodal: boolean; max_queue_size: number };

const STATUSES = ["queued", "thinking", "retrieving", "responding", "done", "error"] as const;

export function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<(typeof STATUSES)[number] | "idle">("idle");
  const [sources, setSources] = useState<RetrievalResult[]>([]);
  const [modelMode, setModelMode] = useState<"rag" | "general">("general");
  const [thinkingNotice, setThinkingNotice] = useState<string>("");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [attachmentName, setAttachmentName] = useState<string>("");
  const [attachmentPayload, setAttachmentPayload] = useState<{ kind: string; content_type: string; value: string }[]>([]);
  const [error, setError] = useState<string>("");
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");

  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === conversationId),
    [conversations, conversationId]
  );

  async function loadConversations() {
    const data = await api<Conversation[]>("/api/chat/conversations");
    setConversations(data);
    if (!conversationId && data.length) setConversationId(data[0].id);
  }

  async function loadCapabilities() {
    const data = await api<Capabilities>("/api/chat/capabilities");
    setCapabilities(data);
  }

  async function loadMessages(id: string) {
    const data = await api<Message[]>(`/api/chat/conversations/${id}/messages`);
    setMessages(data);
  }

  useEffect(() => {
    void loadConversations();
    void loadCapabilities();
  }, []);

  useEffect(() => {
    if (conversationId) void loadMessages(conversationId);
  }, [conversationId]);

  async function createConversation() {
    const created = await api<Conversation>("/api/chat/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "Новый диалог" }),
    });
    setConversations((prev) => [created, ...prev]);
    setConversationId(created.id);
    setMessages([]);
  }

  function startRename() {
    if (!activeConversation) return;
    setDraftTitle(activeConversation.title);
    setIsRenaming(true);
  }

  async function renameConversation(event: FormEvent) {
    event.preventDefault();
    if (!conversationId || !draftTitle.trim()) return;
    const renamed = await api<Conversation>(`/api/chat/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: draftTitle.trim() }),
    });
    setConversations((prev) => prev.map((item) => (item.id === renamed.id ? renamed : item)));
    setIsRenaming(false);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!conversationId || !input.trim()) return;
    setError("");
    if (attachmentPayload.length > 0 && !capabilities?.multimodal) {
      setError("Простите, я понимаю только текст");
      return;
    }
    setStatus("queued");
    const requestText = input;
    setInput("");
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: requestText }]);
    let enqueue: { job_id: string };
    try {
      enqueue = await api<{ job_id: string }>(`/api/chat/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: requestText, attachments: attachmentPayload }),
      });
    } catch (err) {
      setStatus("error");
      setError((err as Error).message);
      return;
    }
    setAttachmentPayload([]);
    setAttachmentName("");
    let assistantBuffer = "";
    let sourceHandle: { close: () => void } | null = null;
    try {
      sourceHandle = await streamJob(enqueue.job_id, (eventPayload) => {
      const nextStatus = eventPayload.status as (typeof STATUSES)[number];
      if (nextStatus) setStatus(nextStatus);
      const notice = eventPayload?.payload?.thinking_notice as string | undefined;
      if (notice) setThinkingNotice(notice);
      const delta = eventPayload?.payload?.delta as string | undefined;
      if (delta) {
        assistantBuffer += delta;
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant" && last.id === enqueue.job_id) {
            last.content = assistantBuffer;
          } else {
            copy.push({ id: enqueue.job_id, role: "assistant", content: assistantBuffer });
          }
          return copy;
        });
      }
      const finalMessage = eventPayload?.payload?.message as string | undefined;
      if (finalMessage && !assistantBuffer) {
        assistantBuffer = finalMessage;
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant" && last.id === enqueue.job_id) {
            last.content = finalMessage;
          } else {
            copy.push({ id: enqueue.job_id, role: "assistant", content: finalMessage });
          }
          return copy;
        });
      }
      if (eventPayload?.payload?.retrieval_results) {
        setSources(eventPayload.payload.retrieval_results as RetrievalResult[]);
      }
      if (eventPayload?.payload?.mode) {
        setModelMode(eventPayload.payload.mode as "rag" | "general");
      }
      const streamError = eventPayload?.payload?.error as string | undefined;
      if (streamError) {
        setError(streamError);
      }
      if (nextStatus === "done" || nextStatus === "error") {
        sourceHandle?.close();
        setThinkingNotice("");
        if (conversationId) void loadMessages(conversationId);
      }
      });
    } catch (err) {
      setStatus("error");
      setError((err as Error).message);
    }
  }

  async function onAttachFile(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Поддерживаются только изображения");
      return;
    }
    const base64Value = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
      reader.readAsDataURL(file);
    });
    setAttachmentName(file.name);
    setAttachmentPayload([{ kind: "image", content_type: file.type, value: base64Value }]);
  }

  return (
    <main className="chat-layout">
      <aside className="sidebar">
        <button onClick={createConversation}>+ Новый диалог</button>
        {conversations.map((conv) => (
          <button key={conv.id} onClick={() => setConversationId(conv.id)} className={conv.id === conversationId ? "active" : ""}>
            {conv.title}
          </button>
        ))}
      </aside>
      <section className="chat-panel">
        <div className="conversation-heading">
          {isRenaming ? (
            <form onSubmit={renameConversation} className="rename-form">
              <input value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} autoFocus />
              <button type="submit">СОХРАНИТЬ</button>
              <button type="button" onClick={() => setIsRenaming(false)}>
                ОТМЕНА
              </button>
            </form>
          ) : (
            <>
              <h2>{activeConversation?.title || "Диалог"}</h2>
              {activeConversation && <button onClick={startRename}>ПЕРЕИМЕНОВАТЬ</button>}
            </>
          )}
        </div>
        <div className="status">
          Статус: {status === "queued" ? "queued — запрос в очереди или ожидает свободный worker" : status}
        </div>
        {thinkingNotice && <div className="status-note">{thinkingNotice}</div>}
        {error && <div className="error">{error}</div>}
        <div className="messages">
          {messages.map((msg) => (
            <article key={msg.id} className={`msg ${msg.role}`}>
              <strong>{msg.role === "user" ? "Вы" : "Ассистент"}:</strong>
              {msg.role === "assistant" ? <MarkdownMessage content={msg.content} /> : <div>{msg.content}</div>}
            </article>
          ))}
        </div>
        <form onSubmit={send} className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Введите вопрос..."
            rows={4}
          />
          <div className="attachment-row">
            <input type="file" accept="image/*" onChange={(e) => void onAttachFile(e.target.files?.[0] ?? null)} />
            {attachmentName && <span>Файл: {attachmentName}</span>}
            {capabilities && !capabilities.multimodal && <span>Мультимодальность отключена</span>}
          </div>
          <button type="submit">Отправить</button>
        </form>
      </section>
      <aside className="sources">
        <h3>Источники</h3>
        <p>Режим ответа: {modelMode === "rag" ? "На основе базы знаний" : "Общий ответ модели"}</p>
        {sources.length === 0 ? (
          <p>Нет</p>
        ) : (
          sources.map((src) => <p key={`${src.document_id}-${src.chunk_id}`}>{src.document_id} / {src.chunk_id} / {src.score.toFixed(3)}</p>)
        )}
      </aside>
    </main>
  );
}
