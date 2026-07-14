import type { ReactNode } from "react";

/** Left-rail section: an uppercase title over its content, with an empty state. */
export function RailSection({
  title,
  isEmpty = false,
  empty = "None",
  children,
}: {
  title: string;
  isEmpty?: boolean;
  empty?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rail-section">
      <div className="rail-title">{title}</div>
      {isEmpty ? <div className="rail-empty">{empty}</div> : children}
    </section>
  );
}
