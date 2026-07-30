import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

import { AppButton } from "./AppButton";
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
        <AppButton
          className="empty-state-action"
          icon={ArrowRight}
          onClick={action.onClick}
        >
          {action.label}
        </AppButton>
      ) : null}
    </section>
  );
}
