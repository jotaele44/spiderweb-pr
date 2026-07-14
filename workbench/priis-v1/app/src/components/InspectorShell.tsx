import type { ReactNode } from "react";

/**
 * Shared right-inspector scaffold: `<aside class="inspector">` with a head
 * (eyebrow + title + optional badges row) and a body. Replaces the aside/head/
 * body markup repeated across every Inspector variant.
 */
export function InspectorShell({
  eyebrow,
  title,
  badges,
  children,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  badges?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <aside className="inspector">
      <div className="inspector-head">
        <div className="subtle mono">{eyebrow}</div>
        <h2>{title}</h2>
        {badges && <div className="row">{badges}</div>}
      </div>
      <div className="inspector-body">{children}</div>
    </aside>
  );
}
