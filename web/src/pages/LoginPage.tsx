import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import type { AuthTokens } from "../types";

export default function LoginPage() {
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    // Read directly from DOM to capture browser autofill values
    const email = emailRef.current?.value ?? "";
    const password = passwordRef.current?.value ?? "";
    try {
      const data = await api.post<AuthTokens>("/auth/login", { email, password });
      setAuth(data.user, data.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent">
            <svg className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/><line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="18"/></svg>
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">
            <span className="text-accent">Trade</span>CoPilot
          </h1>
        </div>
        {error && <p className="text-sm text-bearish-text">{error}</p>}
        <input
          ref={emailRef}
          type="email"
          name="email"
          autoComplete="email"
          placeholder="Email"
          className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
          required
        />
        <input
          ref={passwordRef}
          type="password"
          name="password"
          autoComplete="current-password"
          placeholder="Password"
          className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
        <p className="text-right">
          <Link to="/reset-password" className="text-xs text-text-muted hover:text-accent transition-colors">
            Forgot password?
          </Link>
        </p>
        <p className="text-center text-sm text-text-muted">
          Don't have an account?{" "}
          <Link to="/register" className="text-accent hover:text-accent-hover">
            Create one
          </Link>
        </p>
      </form>
    </div>
  );
}
