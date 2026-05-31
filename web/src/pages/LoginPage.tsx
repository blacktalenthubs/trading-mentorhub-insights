import { useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import type { AuthTokens } from "../types";
import { Mail, Lock, Eye, EyeOff, ArrowRight } from "lucide-react";
import GoogleSignInButton from "../components/GoogleSignInButton";
import AuthShell, { AuthDivider, AuthError, AuthField } from "../components/AuthShell";

export default function LoginPage() {
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  // Bounce already-authenticated users straight into the app.
  if (user) {
    return <Navigate to="/trading" replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    // Read directly from DOM to capture browser autofill values
    const email = emailRef.current?.value ?? "";
    const password = passwordRef.current?.value ?? "";
    try {
      const data = await api.post<AuthTokens>("/auth/login", { email, password });
      await setAuth(data.user, data.access_token, data.refresh_token);
      navigate("/trading", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to continue to your trading desk."
      footer={
        <>Don't have an account?{" "}
          <Link to="/register" className="text-accent font-medium hover:underline">Create one</Link>
        </>
      }
    >
      <GoogleSignInButton destination="/trading" />
      <AuthDivider />

      <form onSubmit={handleSubmit} className="space-y-3">
        <AuthError message={error} />

        <AuthField
          inputRef={emailRef}
          type="email"
          name="email"
          // iOS Password Autofill pairs "username" + "current-password";
          // "email" alone is less reliable for the Save Password prompt.
          autoComplete="username"
          placeholder="Email"
          required
          icon={<Mail className="h-4 w-4" />}
        />

        <div className="relative">
          <span className="absolute inset-y-0 left-3 flex items-center text-text-faint pointer-events-none">
            <Lock className="h-4 w-4" />
          </span>
          <input
            ref={passwordRef}
            type={showPw ? "text" : "password"}
            name="password"
            autoComplete="current-password"
            placeholder="Password"
            required
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

        <div className="flex justify-end">
          <Link to="/reset-password" className="text-xs text-text-muted hover:text-accent transition-colors">
            Forgot password?
          </Link>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent py-2.5 text-sm font-bold text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Signing in…" : (<>Sign in <ArrowRight className="h-3.5 w-3.5" /></>)}
        </button>
      </form>
    </AuthShell>
  );
}
