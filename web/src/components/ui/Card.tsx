import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  elevated?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
  className?: string;
}

const PADDING_CLASSES = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

export default function Card({
  children,
  title,
  subtitle,
  elevated = false,
  padding = "md",
  className = "",
}: CardProps) {
  return (
    <div
      className={`rounded-lg border border-border-subtle bg-surface-2 ${
        elevated ? "shadow-elevated" : "shadow-card"
      } ${PADDING_CLASSES[padding]} ${className}`}
    >
      {(title || subtitle) && (
        <div className={`${padding === "none" ? "px-4 pt-4" : ""} ${title ? "mb-3" : ""}`}>
          {title && (
            <h3 className="font-display text-sm font-semibold text-text-primary">
              {title}
            </h3>
          )}
          {subtitle && (
            <p className="mt-0.5 text-xs text-text-muted">{subtitle}</p>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
