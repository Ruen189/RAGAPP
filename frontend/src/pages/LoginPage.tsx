import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EyeClosedIcon, EyeOpenIcon } from "../components/EyeIcons";

const PASSWORD_HINT =
  "Пароль: не менее 8 символов, хотя бы одна буква и одна цифра.";

export function LoginPage() {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [showPassword, setShowPassword] = useState(false);
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
      setError(err instanceof Error ? err.message : "Ошибка запроса");
    }
  };

  return (
    <main className="container">
      <h2>{mode === "login" ? "Авторизация" : "Регистрация"}</h2>
      <form onSubmit={submit} className="form">
        <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Логин" autoComplete="username" />
        <div className="password-field">
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль"
            type={showPassword ? "text" : "password"}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          <button
            type="button"
            className="password-toggle"
            onClick={() => setShowPassword((value) => !value)}
            aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            title={showPassword ? "Скрыть пароль" : "Показать пароль"}
          >
            {showPassword ? <EyeClosedIcon /> : <EyeOpenIcon />}
          </button>
        </div>
        {mode === "register" && <p className="form-hint">{PASSWORD_HINT}</p>}
        <button type="submit">{mode === "login" ? "Войти" : "Создать пользователя и войти"}</button>
      </form>
      <button className="link-button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
      </button>
      {error && <pre className="error">{error}</pre>}
    </main>
  );
}
