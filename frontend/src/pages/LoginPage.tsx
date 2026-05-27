import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export function LoginPage() {
  const [login, setLogin] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      if (mode === "register") {
        await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ login, password }),
        });
      }
      const data = await api<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ login, password }),
      });
      localStorage.setItem("token", data.access_token);
      navigate("/chat");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <main className="container">
      <h2>{mode === "login" ? "Авторизация" : "Регистрация"}</h2>
      <form onSubmit={submit} className="form">
        <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Логин" />
        <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Пароль" type="password" />
        <button type="submit">{mode === "login" ? "Войти" : "Создать пользователя и войти"}</button>
      </form>
      <button className="link-button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Нужен обычный пользователь? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
      </button>
      {error && <pre className="error">{error}</pre>}
    </main>
  );
}
