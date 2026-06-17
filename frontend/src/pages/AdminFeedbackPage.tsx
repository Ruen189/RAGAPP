import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api";
import { formatFeedbackTime } from "../formatFeedbackTime";

type FeedbackRow = {
  id: string;
  login: string;
  content: string;
  created_at: string;
};

type ProfileRole = { role: "admin" | "user" };

export function AdminFeedbackPage() {
  const [role, setRole] = useState<"admin" | "user" | null>(null);
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ProfileRole>("/api/profile")
      .then((profile) => {
        setRole(profile.role);
        if (profile.role !== "admin") {
          return;
        }
        return api<FeedbackRow[]>("/api/admin/feedback").then(setRows);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Ошибка загрузки"));
  }, []);

  if (role === "user") {
    return <Navigate to="/profile" replace />;
  }

  return (
    <main className="container profile-page">
      <div className="page-toolbar">
        <Link to="/profile" className="link-button">
          ← Назад в профиль
        </Link>
      </div>
      <h2>Обратная связь</h2>
      {error && <pre className="error">{error}</pre>}
      {role === null && !error && <p>Загрузка...</p>}
      {rows.length === 0 && role === "admin" && !error ? (
        <p className="empty-state">Отзывов пока нет.</p>
      ) : (
        rows.map((row) => (
          <article key={row.id} className="feedback-card">
            <header className="feedback-card-header">
              <strong>{row.login}</strong>
              <time dateTime={row.created_at}>{formatFeedbackTime(row.created_at)}</time>
            </header>
            <p>{row.content}</p>
          </article>
        ))
      )}
    </main>
  );
}
