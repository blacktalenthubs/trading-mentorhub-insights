import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import type { AuthTokens } from "../types";
import { Mail, Lock, User, Eye, EyeOff, Check, Clock, ShieldCheck, ArrowRight } from "lucide-react";
import GoogleSignInButton from "../components/GoogleSignInButton";
import AuthShell, { AuthDivider, AuthError, AuthField } from "../components/AuthShell";

export default function RegisterPage() {
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [pw, setPw] = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  const pwScore = useMemo(() => scorePassword(pw), [pw]);
  const pwMismatch = pwConfirm.length > 0 && pw !== pwConfirm;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const email = emailRef.current?.value ?? "";
    const password = passwordRef.current?.value ?? "";
    const confirm = confirmRef.current?.value ?? "";
    const displayName = nameRef.current?.value ?? "";
    if (password !== confirm) { setError("Passwords don't match — re-enter to confirm."); return; }
    setLoading(true);
    try {
      const { getAttribution } = await import("../lib/attribution");
      const attr = getAttribution();
      const data = await api.post<AuthTokens>("/auth/register", {
        email, password,
        display_name: displayName || undefined,
        utm_source: attr?.utm_source,
        utm_medium: attr?.utm_medium,
        utm_campaign: attr?.utm_campaign,
        referrer: attr?.referrer,
      });
      await setAuth(data.user, data.access_token, data.refresh_token);
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start your 3-day Pro trial. No card required."
      footer={
        <>Already have an account?{" "}
          <Link to="/login" className="text-accent font-medium hover:underline">Sign in</Link>
        </>
      }
    >
      <GoogleSignInButton destination="/onboarding" />
      <AuthDivider />

      <form onSubmit={handleSubmit} className="space-y-3">
        <AuthError message={error} />

        <AuthField
          inputRef={nameRef}
          name="name"
          autoComplete="name"
          placeholder="Display name (optional)"
          icon={<User className="h-4 w-4" />}
        />
        <AuthField
          inputRef={emailRef}
          type="email"
          name="email"
          autoComplete="email"
          placeholder="Email"
          required
          icon={<Mail className="h-4 w-4" />}
        />

        <div>
          <div className="relative">
            <span className="absolute inset-y-0 left-3 flex items-center text-text-faint pointer-events-none">
              <Lock className="h-4 w-4" />
            </span>
            <input
              ref={passwordRef}
              type={showPw ? "text" : "password"}
              name="new-password"
              autoComplete="new-password"
              placeholder="Password (min 6 characters)"
              minLength={6}
              required
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              className="w-full rounded-lg border border-border-subtle bg-surface-3 pl-9 pr-10 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              tabIndex={-1}
              aria-label={showPw ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-3 flex items-center text-text-faint hover:text-text-secondary"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {pw.length > 0 && <PasswordMeter score={pwScore} />}
        </div>

        <AuthField
          inputRef={confirmRef}
          type={showPw ? "text" : "password"}
          name="confirm-password"
          autoComplete="new-password"
          placeholder="Confirm password"
          required
          onChange={(e) => setPwConfirm(e.target.value)}
          invalid={pwMismatch}
          icon={<Lock className="h-4 w-4" />}
        />
        {pwMismatch && <p className="-mt-2 text-[11px] text-bearish-text">Passwords don't match.</p>}

        <button
          type="submit"
          disabled={loading || pwMismatch}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-bullish py-2.5 text-sm font-bold text-surface-0 hover:bg-bullish/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-[0_0_15px_rgba(34,197,94,0.18)]"
        >
          {loading ? "Creating account…" : (<>Create account <ArrowRight className="h-3.5 w-3.5" /></>)}
        </button>

        <TrustBadges />
      </form>
    </AuthShell>
  );
}

/* ── Password strength meter ──────────────────────────────────── */

function scorePassword(pw: string): { score: number; label: string; tone: string } {
  if (pw.length === 0) return { score: 0, label: "", tone: "bg-surface-3" };
  let n = 0;
  if (pw.length >= 6) n++;
  if (pw.length >= 10) n++;
  if (/\d/.test(pw)) n++;
  if (/[^A-Za-z0-9]/.test(pw)) n++;
  const labels = ["Too short", "Weak", "OK", "Strong", "Very strong"];
  const tones = ["bg-bearish/60", "bg-warning/60", "bg-warning", "bg-bullish", "bg-bullish"];
  return { score: n, label: labels[n], tone: tones[n] };
}

function PasswordMeter({ score }: { score: { score: number; label: string; tone: string } }) {
  return (
    <div className="mt-1.5 flex items-center gap-2">
      <div className="flex-1 flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${i < score.score ? score.tone : "bg-surface-3"}`}
          />
        ))}
      </div>
      <span className="text-[10px] uppercase tracking-wider text-text-faint w-20 text-right">
        {score.label}
      </span>
    </div>
  );
}

/* ── Trust badges ─────────────────────────────────────────────── */

function TrustBadges() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 pt-1 text-[10px] text-text-faint">
      <span className="inline-flex items-center gap-1"><Check className="h-3 w-3 text-bullish-text" /> 3-day free trial</span>
      <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3 text-bullish-text" /> Cancel anytime</span>
      <span className="inline-flex items-center gap-1"><ShieldCheck className="h-3 w-3 text-bullish-text" /> No card required</span>
    </div>
  );
}
