import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { prepareLogForDisplay } from "../formatLogPayload";

type Role = "admin" | "user";

type Profile = {
  user_id: string;
  login: string;
  role: Role;
  full_name: string;
  university_group: string;
  phone: string;
  telegram: string;
  avatar_data_url: string | null;
};

type LogRow = {
  trace_id: string;
  user_id: string;
  conversation_id: string;
  message_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type AdminUser = { id: string; login: string; role: string };

type PaginatedLogs = {
  items: LogRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

const LOGS_PAGE_SIZE = 10;

const emptyProfile: Profile = {
  user_id: "",
  login: "",
  role: "user",
  full_name: "-",
  university_group: "-",
  phone: "-",
  telegram: "-",
  avatar_data_url: null,
};

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [draft, setDraft] = useState<Profile>(emptyProfile);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [logsPage, setLogsPage] = useState(1);
  const [logsTotalPages, setLogsTotalPages] = useState(0);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logsLoading, setLogsLoading] = useState(false);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const isAdmin = profile.role === "admin";

  async function loadProfile() {
    const data = await api<Profile>("/api/profile");
    setProfile(data);
    setDraft(data);
    if (data.role === "admin") {
      await loadUsers();
    }
  }

  async function loadUsers() {
    const adminUsers = await api<AdminUser[]>("/api/admin/users");
    setUsers(adminUsers);
    if (adminUsers.length > 0) {
      setSelectedUserId((current) => current || adminUsers[0].id);
    }
  }

  async function loadLogs(page: number) {
    setLogsLoading(true);
    try {
      const data = await api<PaginatedLogs>(
        `/api/admin/logs?page=${page}&page_size=${LOGS_PAGE_SIZE}`
      );
      setLogs(data.items);
      setLogsPage(data.page);
      setLogsTotalPages(data.total_pages);
      setLogsTotal(data.total);
    } finally {
      setLogsLoading(false);
    }
  }

  useEffect(() => {
    loadProfile().catch((err) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    void loadLogs(logsPage).catch((err) => setError((err as Error).message));
  }, [isAdmin, logsPage]);

  async function saveProfile(event?: FormEvent) {
    event?.preventDefault();
    const saved = await api<Profile>("/api/profile", {
      method: "PUT",
      body: JSON.stringify({
        full_name: draft.full_name,
        university_group: draft.university_group,
        phone: draft.phone,
        telegram: draft.telegram,
        avatar_data_url: draft.avatar_data_url,
      }),
    });
    setProfile(saved);
    setDraft(saved);
  }

  async function onAvatarSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
      reader.readAsDataURL(file);
    });
    const nextDraft = { ...draft, avatar_data_url: dataUrl };
    setDraft(nextDraft);
    const saved = await api<Profile>("/api/profile", {
      method: "PUT",
      body: JSON.stringify({
        full_name: nextDraft.full_name,
        university_group: nextDraft.university_group,
        phone: nextDraft.phone,
        telegram: nextDraft.telegram,
        avatar_data_url: nextDraft.avatar_data_url,
      }),
    });
    setProfile(saved);
    setDraft(saved);
  }

  async function deleteAvatar() {
    const nextDraft = { ...draft, avatar_data_url: null };
    setDraft(nextDraft);
    const saved = await api<Profile>("/api/profile", {
      method: "PUT",
      body: JSON.stringify({
        full_name: nextDraft.full_name,
        university_group: nextDraft.university_group,
        phone: nextDraft.phone,
        telegram: nextDraft.telegram,
        avatar_data_url: null,
      }),
    });
    setProfile(saved);
    setDraft(saved);
  }

  function downloadAvatar() {
    if (!profile.avatar_data_url) return;
    const link = document.createElement("a");
    link.href = profile.avatar_data_url;
    link.download = `${profile.login || "avatar"}-avatar.png`;
    link.click();
  }

  async function changeRole() {
    if (!selectedUserId) return;
    await api("/api/admin/change-role", {
      method: "POST",
      body: JSON.stringify({ target_user_id: selectedUserId }),
    });
    await loadUsers();
  }

  return (
    <main className="container profile-page">
      <h2>Профиль</h2>
      {error && <pre className="error">{error}</pre>}

      <section className="profile-card">
        <h3>АВАТАР</h3>
        <div className="avatar-panel">
          <button className="avatar-button" onClick={() => fileInputRef.current?.click()} title="Заменить фото">
            {profile.avatar_data_url ? (
              <img src={profile.avatar_data_url} alt="Аватар пользователя" />
            ) : (
              <span>{profile.login ? profile.login.slice(0, 2).toUpperCase() : "PM"}</span>
            )}
          </button>
          <input ref={fileInputRef} type="file" accept="image/*" onChange={onAvatarSelected} hidden />
          <div className="avatar-actions">
            <button onClick={() => fileInputRef.current?.click()} title="Заменить фото">↻</button>
            <button onClick={downloadAvatar} disabled={!profile.avatar_data_url} title="Скачать фото">↓</button>
            <button onClick={deleteAvatar} disabled={!profile.avatar_data_url} title="Удалить фото">×</button>
          </div>
        </div>
      </section>

      <section className="profile-card">
        <h3>ОБЩАЯ ИНФОРМАЦИЯ</h3>
        <form className="profile-form" onSubmit={saveProfile}>
          <label>
            ФИО
            <input value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} />
          </label>
          <label>
            Университетская группа
            <input
              value={draft.university_group}
              onChange={(e) => setDraft({ ...draft, university_group: e.target.value })}
            />
          </label>
          <label>
            Номер телефона
            <input value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} />
          </label>
          <label>
            Telegram
            <input value={draft.telegram} onChange={(e) => setDraft({ ...draft, telegram: e.target.value })} />
          </label>
          <button type="submit">СОХРАНИТЬ</button>
        </form>
      </section>

      {isAdmin && (
        <>
          <section className="profile-card">
            <h3>УПРАВЛЕНИЕ РОЛЯМИ</h3>
            <div className="role-row">
              <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.login} ({user.role})
                  </option>
                ))}
              </select>
              <button onClick={changeRole}>ИЗМЕНИТЬ РОЛЬ</button>
            </div>
          </section>

          <section className="profile-card">
            <h3>ОБРАТНАЯ СВЯЗЬ</h3>
            <p className="profile-card-note">Просмотр отзывов пользователей о работе ассистента.</p>
            <Link to="/profile/feedback" className="profile-link-button">
              Открыть отзывы
            </Link>
          </section>

          <section className="profile-card">
            <h3>ЛОГИ</h3>
            <div className="logs-panel">
              {logsLoading ? (
                <p className="logs-status">Загрузка логов...</p>
              ) : logs.length === 0 ? (
                <p className="logs-status">Логов пока нет.</p>
              ) : (
                logs.map((row) => (
                  <article key={row.trace_id + row.message_id} className="log-card">
                    <pre>{JSON.stringify(prepareLogForDisplay(row), null, 2)}</pre>
                  </article>
                ))
              )}
              <div className="logs-pagination">
                <button type="button" disabled={logsLoading || logsPage <= 1} onClick={() => setLogsPage((page) => page - 1)}>
                  Назад
                </button>
                <span>
                  Страница {logsPage}
                  {logsTotalPages > 0 ? ` из ${logsTotalPages}` : ""} · всего {logsTotal}
                </span>
                <button
                  type="button"
                  disabled={logsLoading || logsPage >= logsTotalPages || logsTotalPages === 0}
                  onClick={() => setLogsPage((page) => page + 1)}
                >
                  Вперёд
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
