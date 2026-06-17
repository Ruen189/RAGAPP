import { ChangeEvent, useEffect, useRef, useState } from "react";
import { api, apiUploadFile, downloadAuthenticatedFile } from "../api";
import { EyeClosedIcon, EyeOpenIcon } from "../components/EyeIcons";

type Doc = {
  id: string;
  title: string;
  file_name: string;
  source_type: string;
  visible_to_users: boolean;
};

type CurrentUser = { role: "admin" | "user" };

export function KnowledgePage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [userRole, setUserRole] = useState<"admin" | "user" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const isAdmin = userRole === "admin";

  async function load() {
    const me = await api<CurrentUser>("/api/auth/me");
    setUserRole(me.role);
    const documents = await api<Doc[]>("/api/knowledge/documents");
    setDocs(documents);
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "Ошибка загрузки"));
  }, []);

  async function onFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await apiUploadFile("/api/knowledge/upload", file);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить файл");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function toggleVisibility(docId: string) {
    setError(null);
    try {
      const updated = await api<Doc>(`/api/knowledge/documents/${docId}/visibility`, { method: "PATCH" });
      setDocs((prev) => prev.map((doc) => (doc.id === updated.id ? updated : doc)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить видимость");
    }
  }

  async function downloadDoc(doc: Doc) {
    setError(null);
    try {
      await downloadAuthenticatedFile(`/api/knowledge/documents/${doc.id}/download`, doc.file_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось скачать файл");
    }
  }

  async function deleteDoc(docId: string) {
    setError(null);
    setDeletingId(docId);
    try {
      await api(`/api/knowledge/documents/${docId}`, { method: "DELETE" });
      setDocs((prev) => prev.filter((doc) => doc.id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить файл");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="container knowledge-page">
      <h2>База знаний</h2>
      <p className="knowledge-intro">
        {isAdmin
          ? "Загрузите .txt, .md, .docx или .pdf — файл сразу попадёт в RAG. Таблицы из PDF и DOCX тоже индексируются."
          : "Скачайте доступные материалы по управлению проектами и методологиям."}
      </p>
      {error && <pre className="error">{error}</pre>}

      {isAdmin && (
        <section className="card knowledge-upload-card">
          <h3>Загрузка в RAG</h3>
          <p className="form-hint">Поддерживаются файлы .txt, .md, .docx и .pdf (до 10 МБ).</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.docx,.pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf"
            onChange={(event) => void onFileSelected(event)}
            hidden
          />
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? "Загрузка..." : "Выбрать файл"}
          </button>
        </section>
      )}

      <section className="knowledge-files">
        <h3>Файлы</h3>
        {docs.length === 0 ? (
          <p className="empty-state">Доступных файлов пока нет.</p>
        ) : (
          docs.map((doc) => (
            <article key={doc.id} className="knowledge-file-row card">
              <div className="knowledge-file-main">
                <strong>{doc.file_name}</strong>
              </div>
              <div className="knowledge-file-actions">
                <button type="button" className="knowledge-action-button" onClick={() => void downloadDoc(doc)}>
                  Скачать
                </button>
                {isAdmin && (
                  <>
                    <button
                      type="button"
                      className="visibility-toggle"
                      onClick={() => void toggleVisibility(doc.id)}
                      aria-label={
                        doc.visible_to_users
                          ? "Скрыть файл от обычных пользователей"
                          : "Открыть файл для скачивания обычным пользователям"
                      }
                      title={doc.visible_to_users ? "Виден пользователям" : "Скрыт от пользователей"}
                    >
                      {doc.visible_to_users ? <EyeOpenIcon /> : <EyeClosedIcon />}
                    </button>
                    <button
                      type="button"
                      className="knowledge-action-button danger-button"
                      onClick={() => void deleteDoc(doc.id)}
                      disabled={deletingId === doc.id}
                    >
                      {deletingId === doc.id ? "Удаление..." : "Удалить"}
                    </button>
                  </>
                )}
              </div>
            </article>
          ))
        )}
      </section>
    </main>
  );
}
