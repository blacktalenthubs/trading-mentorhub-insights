import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import type { AuthTokens } from "../types";
import { Crosshair } from "lucide-react";

export default function RegisterPage() {
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [pwMismatch, setPwMismatch] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const email = emailRef.current?.value ?? "";
    const password = passwordRef.current?.value ?? "";
    const confirm = confirmRef.current?.value ?? "";
    const displayName = nameRef.current?.value ?? "";

    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const data = await api.post<AuthTokens>("/auth/register", {
        email,
        password,
        display_name: displayName || undefined,
      });
      setAuth(data.user, data.access_token);
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-xl border border-border-subtle bg-surface-1 p-8 shadow-elevated"
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent">
            <Crosshair className="h-4 w-4 text-white" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">
            <span className="text-accent">Trade</span>Signal
          </h1>
        </div>

        <p className="text-sm text-text-muted">Create your account to start getting trade alerts.</p>

        {error && (
          <div className="bg-bearish/10 border border-bearish/20 rounded-lg px-3 py-2 text-sm text-bearish-text">
            {error}
          </div>
        )}

        <input
          ref={nameRef}
          type="text"
          name="name"
          autoComplete="name"
          placeholder="Display name (optional)"
          className="w-full rounded-lg border border-border-subtle bg-surface-3 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
        />
        <input
          ref={emailRef}
          type="email"
          name="email"
          autoComplete="email"
          placeholder="Email"
          className="w-full rounded-lg border border-border-subtle bg-surface-3 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          required
        />
        <input
          ref={passwordRef}
          type="password"
          name="new-password"
          autoComplete="new-password"
          placeholder="Password (min 6 characters)"
          className="w-full rounded-lg border border-border-subtle bg-surface-3 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          required
          minLength={6}
        />
        <div>
          <input
            ref={confirmRef}
            type="password"
            name="confirm-password"
            autoComplete="new-password"
            placeholder="Confirm password"
            onChange={() => {
              const pw = passwordRef.current?.value ?? "";
              const cf = confirmRef.current?.value ?? "";
              setPwMismatch(cf.length > 0 && pw !== cf);
            }}
            className={`w-full rounded-lg border bg-surface-3 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:outline-none ${
              pwMismatch ? "border-bearish focus:border-bearish" : "border-border-subtle focus:border-accent"
            }`}
            required
          />
          {pwMismatch && (
            <p className="text-[10px] text-bearish-text mt-1">Passwords do not match</p>
          )}
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-bullish py-2.5 text-sm font-bold text-surface-0 hover:bg-bullish/90 disabled:opacity-50 transition-colors shadow-[0_0_15px_rgba(34,197,94,0.15)]"
        >
          {loading ? "Creating account..." : "Create Account"}
        </button>
        <p className="text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:text-accent-hover font-medium">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
