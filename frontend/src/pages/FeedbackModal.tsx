import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";

type FeedbackModalProps = {
  onClose: () => void;
};

export function FeedbackModal({ onClose }: FeedbackModalProps) {
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  function closeWithAnimation() {
    setVisible(false);
    window.setTimeout(onClose, 200);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const trimmed = content.trim();
    if (!trimmed) {
      setError("Введите сообщение");
      return;
    }
    if (trimmed.length > 500) {
      setError("Сообщение не должно превышать 500 символов");
      return;
    }
    try {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({ content: trimmed }),
      });
      setSuccess(true);
      window.setTimeout(closeWithAnimation, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить отзыв");
    }
  }

  return (
    <div
      className={`modal-backdrop${visible ? " open" : ""}`}
      onClick={closeWithAnimation}
      role="presentation"
    >
      <div
        className={`modal-card${visible ? " open" : ""}`}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-title"
      >
        <h3 id="feedback-title">Обратная связь</h3>
        <p className="modal-subtitle">Расскажите, что можно улучшить в ассистенте.</p>
        {success ? (
          <p className="modal-success">Спасибо! Отзыв отправлен.</p>
        ) : (
          <form onSubmit={submit} className="feedback-form">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value.slice(0, 500))}
              placeholder="Ваш отзыв..."
              rows={6}
              maxLength={500}
              autoFocus
            />
            <div className="feedback-meta">
              <span>{content.length}/500</span>
            </div>
            {error && <p className="error inline-error">{error}</p>}
            <div className="modal-actions">
              <button type="button" className="modal-secondary" onClick={closeWithAnimation}>
                Отмена
              </button>
              <button type="submit">Отправить</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
