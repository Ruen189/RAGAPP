import { useEffect, useState } from "react";

type DeleteConversationModalProps = {
  title: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
};

export function DeleteConversationModal({ title, onClose, onConfirm }: DeleteConversationModalProps) {
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  function closeWithAnimation() {
    if (busy) return;
    setVisible(false);
    window.setTimeout(onClose, 200);
  }

  async function confirm() {
    setError(null);
    setBusy(true);
    try {
      await onConfirm();
      setVisible(false);
      window.setTimeout(onClose, 200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить диалог");
      setBusy(false);
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
        aria-labelledby="delete-conversation-title"
      >
        <h3 id="delete-conversation-title">Удалить диалог?</h3>
        <p className="modal-subtitle">
          Диалог «{title}» и все сообщения в нём будут удалены без возможности восстановления.
        </p>
        {error && <p className="error inline-error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="modal-secondary" onClick={closeWithAnimation} disabled={busy}>
            Отмена
          </button>
          <button type="button" className="modal-danger" onClick={() => void confirm()} disabled={busy}>
            {busy ? "Удаление..." : "Удалить"}
          </button>
        </div>
      </div>
    </div>
  );
}
