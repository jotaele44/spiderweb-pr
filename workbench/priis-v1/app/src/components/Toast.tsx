import { useEffect } from "react";

export type ToastKind = "error" | "warn" | "info";

export interface ToastMessage {
  id: string;
  kind: ToastKind;
  text: string;
  /** Auto-dismiss after this many ms. 0 = sticky. */
  ttl?: number;
}

/**
 * Stack of dismissible toasts. Auto-dismisses messages whose `ttl` is set
 * (default 6s). Surfaces failures from background work that wouldn't
 * otherwise interrupt the user's flow — pipeline errors, API failures,
 * background re-index completion notices, etc.
 */
export function ToastStack({
  messages,
  dismiss,
}: {
  messages: ToastMessage[];
  dismiss: (id: string) => void;
}) {
  if (messages.length === 0) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {messages.map((m) => (
        <Toast key={m.id} message={m} dismiss={() => dismiss(m.id)} />
      ))}
    </div>
  );
}

function Toast({ message, dismiss }: { message: ToastMessage; dismiss: () => void }) {
  const ttl = message.ttl ?? 6_000;
  useEffect(() => {
    if (ttl <= 0) return;
    const t = window.setTimeout(dismiss, ttl);
    return () => window.clearTimeout(t);
  }, [ttl, dismiss]);

  return (
    <div className="toast" data-kind={message.kind} role="alert">
      <span className="toast-text">{message.text}</span>
      <button
        className="toast-close"
        onClick={dismiss}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}
