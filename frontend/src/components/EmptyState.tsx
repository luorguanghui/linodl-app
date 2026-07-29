import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  kicker: string;
  title: string;
  detail: string;
  compact?: boolean;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({
  icon,
  kicker,
  title,
  detail,
  compact = false,
  action,
}: EmptyStateProps) {
  return (
    <section className={`empty-state${compact ? " compact" : ""}`}>
      <span className="empty-state-icon" aria-hidden="true">
        {icon}
      </span>
      <p className="empty-state-kicker">{kicker}</p>
      <h2 className="empty-state-title">{title}</h2>
      <p className="empty-state-detail">{detail}</p>
      {action ? (
        <button
          className="empty-state-action"
          type="button"
          onClick={action.onClick}
        >
          {action.label}
        </button>
      ) : null}
    </section>
  );
}
