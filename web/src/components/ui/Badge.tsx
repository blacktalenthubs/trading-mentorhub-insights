import type { ReactNode } from "react";

type BadgeVariant =
  | "bullish"
  | "bearish"
  | "warning"
  | "info"
  | "neutral"
  | "pro"
  | "purple"
  | "orange";

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  bullish: "bg-bullish-muted text-bullish-text",
  bearish: "bg-bearish-muted text-bearish-text",
  warning: "bg-warning-muted text-warning-text",
  info: "bg-info-muted text-info-text",
  neutral: "bg-surface-4 text-text-secondary",
  pro: "bg-accent-muted text-info-text",
  purple: "bg-purple-muted text-purple-text",
  orange: "bg-orange-muted text-orange-text",
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

export default function Badge({
  variant = "neutral",
  children,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
