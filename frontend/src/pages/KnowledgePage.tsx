import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";

type Doc = { id: string; title: string; source_type: string; created_at: string };

export function KnowledgePage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [title, setTitle] = useState("Scrum Guide");
  const [content, setContent] = useState("Scrum - это фреймворк адаптивной разработки с ролями, событиями и артефактами.");

  async function load() {
    const data = await api<Doc[]>("/api/knowledge/documents");
    setDocs(data);
  }

  useEffect(() => {
    void load();
  }, []);

  async function upload(event: FormEvent) {
    event.preventDefault();
    await api("/api/knowledge/upload", {
      method: "POST",
      body: JSON.stringify({
        title,
        content,
        source_uri: "manual://ui-upload",
        metadata_json: { domain: "project-management" },
      }),
    });
    await load();
  }

  return (
    <main className="container">
      <h2>База знаний</h2>
      <form onSubmit={upload} className="form">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название документа" />
        <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={6} />
        <button type="submit">Загрузить в RAG</button>
      </form>
      <h3>Документы</h3>
      {docs.map((doc) => (
        <article key={doc.id} className="card">
          <strong>{doc.title}</strong>
          <div>{new Date(doc.created_at).toLocaleString()}</div>
          <div>{doc.source_type}</div>
        </article>
      ))}
    </main>
  );
}
