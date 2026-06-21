/** AuthShell — shared visual container for Register / Login / Reset pages.
 *  Centers a card with the BusyTradersDesk brand mark on a dark surface,
 *  with consistent spacing, typography, and inline trust microcopy.
 */

import { Crosshair, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  /** Footer line under the card, e.g. "Already have an account? Sign in" */
  footer?: React.ReactNode;
}

export default function AuthShell({ title, subtitle, children, footer }: Props) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-surface-0 px-4 py-10">
      {/* Explicit back affordance — the logo also links home, but users (esp. on mobile)
          don't realize it; this gives a clear way out of the auth flow. */}
      <Link to="/" className="absolute top-4 left-4 inline-flex items-center gap-1 text-[13px] text-text-muted hover:text-text-primary active:opacity-70">
        <ArrowLeft size={16} /> Back
      </Link>
      {/* Brand */}
      <Link to="/" className="flex items-center gap-2.5 mb-6 group">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent transition-transform group-hover:scale-105">
          <Crosshair className="h-4.5 w-4.5 text-white" />
        </div>
        <span className="font-display text-xl font-bold text-text-primary">
          <span className="text-accent">Busy</span>TradersDesk
        </span>
      </Link>

      {/* Card */}
      <div className="w-full max-w-sm rounded-2xl border border-border-subtle bg-surface-1 p-7 shadow-elevated">
        <h1 className="text-xl font-bold text-text-primary">{title}</h1>
        {subtitle && (
          <p className="mt-1.5 text-sm text-text-muted leading-relaxed">{subtitle}</p>
        )}
        <div className="mt-5 space-y-4">{children}</div>
      </div>

      {/* Footer line */}
      {footer && (
        <p className="mt-5 text-sm text-text-muted text-center">{footer}</p>
      )}

      {/* Legal microcopy */}
      <p className="mt-4 text-[11px] text-text-faint text-center max-w-xs leading-relaxed">
        By continuing you agree to our <a href="/terms" className="underline hover:text-text-secondary">Terms</a> and <a href="/privacy" className="underline hover:text-text-secondary">Privacy Policy</a>. Not investment advice.
      </p>
    </div>
  );
}

/* ── Inline atoms ──────────────────────────────────────────────── */

export function AuthDivider({ label = "or use email" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-text-faint">
      <div className="flex-1 h-px bg-border-subtle" />
      <span>{label}</span>
      <div className="flex-1 h-px bg-border-subtle" />
    </div>
  );
}

export function AuthError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-bearish/25 bg-bearish/10 px-3 py-2 text-xs text-bearish-text">
      <svg className="h-3.5 w-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span className="leading-relaxed">{message}</span>
    </div>
  );
}

interface FieldProps {
  type?: string;
  name: string;
  autoComplete?: string;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  invalid?: boolean;
  icon?: React.ReactNode;
}

export function AuthField({
  type = "text", name, autoComplete, placeholder, required, minLength, inputRef, onChange, invalid, icon,
}: FieldProps) {
  return (
    <div className="relative">
      {icon && (
        <span className="absolute inset-y-0 left-3 flex items-center text-text-faint pointer-events-none">
          {icon}
        </span>
      )}
      <input
        ref={inputRef}
        type={type}
        name={name}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={onChange}
        required={required}
        minLength={minLength}
        className={[
          "w-full rounded-lg border bg-surface-3 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:outline-none focus:ring-1 transition-colors",
          icon ? "pl-9 pr-3" : "px-3",
          invalid
            ? "border-bearish/60 focus:border-bearish focus:ring-bearish/30"
            : "border-border-subtle focus:border-accent focus:ring-accent/30",
        ].join(" ")}
      />
    </div>
  );
}
