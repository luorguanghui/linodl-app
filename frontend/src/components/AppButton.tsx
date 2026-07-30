import {
  LoaderCircle,
  type LucideIcon,
} from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

export type AppButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger";

export type AppButtonSize = "default" | "compact";

export interface AppButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: AppButtonVariant;
  size?: AppButtonSize;
  icon?: LucideIcon;
  loading?: boolean;
}

export function AppButton({
  variant = "primary",
  size = "default",
  icon: Icon,
  loading = false,
  className,
  disabled,
  type,
  children,
  ...buttonProps
}: AppButtonProps) {
  const VisibleIcon = loading ? LoaderCircle : Icon;
  const classes = [
    "app-button",
    `app-button--${variant}`,
    `app-button--${size}`,
    loading ? "is-loading" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      {...buttonProps}
      type={type ?? "button"}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {VisibleIcon ? (
        <VisibleIcon
          className="app-button__icon"
          size={16}
          strokeWidth={1.8}
          aria-hidden="true"
        />
      ) : null}
      <span className="app-button__label">{children}</span>
    </button>
  );
}
