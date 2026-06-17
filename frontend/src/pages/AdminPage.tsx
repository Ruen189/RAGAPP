import { useEffect, useState } from "react";
import { api } from "../api";
import { prepareLogForDisplay } from "../formatLogPayload";

type LogRow = {
  trace_id: string;
  user_id: string;
  conversation_id: string;
  message_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type PaginatedLogs = {
  items: LogRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

const LOGS_PAGE_SIZE = 10;

export function AdminPage() {
  const [rows, setRows] = useState<LogRow[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<{ id: string; login: string; role: string }[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ id: string; login: string; role: string }[]>("/api/admin/users")
      .then((data) => {
        setUsers(data);
        if (data.length > 0) setSelectedUserId(data[0].id);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    setLoading(true);
    api<PaginatedLogs>(`/api/admin/logs?page=${page}&page_size=${LOGS_PAGE_SIZE}`)
      .then((data) => {
        setRows(data.items);
        setTotalPages(data.total_pages);
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [page]);

  async function changeRole() {
    if (!selectedUserId) return;
    await api("/api/admin/change-role", {
      method: "POST",
      body: JSON.stringify({ target_user_id: selectedUserId }),
    });
    const refreshed = await api<{ id: string; login: string; role: string }[]>("/api/admin/users");
    setUsers(refreshed);
  }

  return (
    <main className="container">
      <h2>Логи пайплайна (только админ)</h2>
      {error && <pre className="error">{error}</pre>}
      <section className="card">
        <h3>Управление ролями</h3>
        <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.login} ({user.role})
            </option>
          ))}
        </select>
        <button onClick={changeRole}>ИЗМЕНИТЬ РОЛЬ</button>
      </section>
      <div className="logs-panel">
        {loading ? (
          <p className="logs-status">Загрузка логов...</p>
        ) : (
          rows.map((row) => (
            <article key={row.trace_id + row.message_id} className="log-card">
              <pre>{JSON.stringify(prepareLogForDisplay(row), null, 2)}</pre>
            </article>
          ))
        )}
        <div className="logs-pagination">
          <button type="button" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>
            Назад
          </button>
          <span>
            Страница {page}
            {totalPages > 0 ? ` из ${totalPages}` : ""}
          </span>
          <button
            type="button"
            disabled={loading || page >= totalPages || totalPages === 0}
            onClick={() => setPage((value) => value + 1)}
          >
            Вперёд
          </button>
        </div>
      </div>
    </main>
  );
}
