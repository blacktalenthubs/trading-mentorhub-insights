import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import type { AuthTokens } from "../types";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
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
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-1 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-border-subtle bg-surface-2 p-8 shadow-card"
      >
        <div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Create Account</h1>
          <p className="mt-1 text-sm text-text-muted">Sign up for TradeSignal</p>
        </div>
        {error && <p className="text-sm text-bearish-text">{error}</p>}
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          required
        />
        <input
          type="text"
          placeholder="Display Name (optional)"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          required
          minLength={6}
        />
        <input
          type="password"
          placeholder="Confirm Password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {loading ? "Creating account..." : "Create Account"}
        </button>
        <p className="text-center text-sm text-text-muted">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:text-accent-hover">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
