/** EmptyState — actionable "nothing here" placeholder.
 *  Every empty zone should name *why* it's empty and offer one concrete next step.
 *  Use the size prop to match the host surface: 'sm' fits inside tables/lists,
 *  'md' fits inside cards, 'lg' fits a full page.
 */

import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

interface ActionProps {
  label: string;
  /** Either onClick or `to` (internal route) or `href` (external) — pick one. */
  onClick?: () => void;
  to?: string;
  href?: string;
}

interface Props {
  title: string;
  hint?: string;
  icon?: LucideIcon;
  primary?: ActionProps;
  secondary?: ActionProps;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE = {
  sm: { wrap: "py-8 px-4", icon: "h-6 w-6", title: "text-sm", hint: "text-xs", iconWrap: "h-10 w-10" },
  md: { wrap: "py-12 px-6", icon: "h-7 w-7", title: "text-base", hint: "text-sm", iconWrap: "h-12 w-12" },
  lg: { wrap: "py-20 px-8", icon: "h-8 w-8", title: "text-lg", hint: "text-sm", iconWrap: "h-14 w-14" },
};

function ActionButton({ a, primary }: { a: ActionProps; primary: boolean }) {
  const cls = primary
    ? "inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-bg-base text-sm font-semibold hover:bg-accent/90 transition-colors"
    : "inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-border-subtle text-sm font-medium text-text-secondary hover:bg-surface-2/60 hover:text-text-primary transition-colors";
  if (a.to) return <Link to={a.to} className={cls}>{a.label}</Link>;
  if (a.href) return <a href={a.href} className={cls} target="_blank" rel="noreferrer">{a.label}</a>;
  return <button type="button" onClick={a.onClick} className={cls}>{a.label}</button>;
}

export default function EmptyState({
  title,
  hint,
  icon: Icon = Inbox,
  primary,
  secondary,
  size = "md",
  className = "",
}: Props) {
  const s = SIZE[size];
  return (
    <div className={`flex flex-col items-center justify-center text-center ${s.wrap} ${className}`}>
      <div className={`${s.iconWrap} rounded-full bg-surface-2/60 border border-border-subtle/60 flex items-center justify-center mb-3`}>
        <Icon className={`${s.icon} text-text-faint`} aria-hidden="true" />
      </div>
      <p className={`${s.title} font-semibold text-text-primary`}>{title}</p>
      {hint && <p className={`${s.hint} text-text-muted mt-1 max-w-xs`}>{hint}</p>}
      {(primary || secondary) && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {primary && <ActionButton a={primary} primary />}
          {secondary && <ActionButton a={secondary} primary={false} />}
        </div>
      )}
    </div>
  );
}
