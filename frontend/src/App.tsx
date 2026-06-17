import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { ChatPage } from "./pages/ChatPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ProfilePage } from "./pages/ProfilePage";
import { AdminFeedbackPage } from "./pages/AdminFeedbackPage";

const isAuthed = () => Boolean(localStorage.getItem("token"));

type CurrentUser = { id: string; login: string; role: "admin" | "user" };

function Protected({ children }: { children: JSX.Element }) {
  if (!isAuthed()) return <Navigate to="/login" replace />;
  return children;
}

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const authed = isAuthed();

  useEffect(() => {
    if (!authed) {
      setUser(null);
      return;
    }
    api<CurrentUser>("/api/auth/me")
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("token");
        setUser(null);
      });
  }, [authed, location.pathname]);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    navigate("/login");
  }

  return (
    <div>
      <header className="topbar">
        <Link to="/" className="brand-button">
          Проектный менеджер
        </Link>
        <nav className="main-nav" aria-label="Основная навигация">
          <Link to="/chat">ЧАТ</Link>
          <Link to="/knowledge">БАЗА ЗНАНИЙ</Link>
          <Link to="/profile">ПРОФИЛЬ</Link>
        </nav>
        <div className="auth-area">
          {user ? (
            <>
              <span className="user-login">{user.login}</span>
              <span className="auth-divider" />
              <button onClick={logout}>ВЫЙТИ</button>
            </>
          ) : (
            <Link to="/login">ВХОД</Link>
          )}
        </div>
      </header>
      <Routes>
        <Route path="/" element={<OnboardingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/chat"
          element={
            <Protected>
              <ChatPage />
            </Protected>
          }
        />
        <Route
          path="/knowledge"
          element={
            <Protected>
              <KnowledgePage />
            </Protected>
          }
        />
        <Route
          path="/profile/feedback"
          element={
            <Protected>
              <AdminFeedbackPage />
            </Protected>
          }
        />
        <Route
          path="/profile"
          element={
            <Protected>
              <ProfilePage />
            </Protected>
          }
        />
        <Route path="/admin" element={<Navigate to="/profile" replace />} />
      </Routes>
    </div>
  );
}
