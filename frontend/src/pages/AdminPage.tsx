import { useEffect, useState } from "react";
import { api } from "../api";

type LogRow = {
  trace_id: string;
  user_id: string;
  conversation_id: string;
  message_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export function AdminPage() {
  const [rows, setRows] = useState<LogRow[]>([]);
  const [users, setUsers] = useState<{ id: string; login: string; role: string }[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<LogRow[]>("/api/admin/logs")
      .then(setRows)
      .catch((err) => setError((err as Error).message));
    api<{ id: string; login: string; role: string }[]>("/api/admin/users")
      .then((data) => {
        setUsers(data);
        if (data.length > 0) setSelectedUserId(data[0].id);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  async function makeAdmin() {
    if (!selectedUserId) return;
    await api("/api/admin/make-admin", {
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
        <button onClick={makeAdmin}>Сделать админом</button>
      </section>
      {rows.map((row) => (
        <article key={row.trace_id + row.message_id} className="card">
          <div>trace_id: {row.trace_id}</div>
          <div>conversation_id: {row.conversation_id}</div>
          <div>created_at: {new Date(row.created_at).toLocaleString()}</div>
          <pre>{JSON.stringify(row.payload, null, 2)}</pre>
        </article>
      ))}
    </main>
  );
}
