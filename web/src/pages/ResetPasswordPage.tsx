import { useRef, useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Crosshair } from "lucide-react";

/** Dual-mode page:
 *  - No ?token param: show "enter your email" form (forgot password).
 *  - With ?token param: show "enter new password" form (reset password).
 */
export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token");

  return token ? <ResetForm token={token} /> : <ForgotForm />;
}

function ForgotForm() {
  const emailRef = useRef<HTMLInputElement>(null);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const email = emailRef.current?.value ?? "";
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <div className="w-full max-w-sm space-y-5 rounded-xl border border-border-subtle bg-surface-1 p-8 shadow-elevated">
        <BrandHeader />

        {sent ? (
          <div className="space-y-4">
            <div className="bg-bullish/10 border border-bullish/20 rounded-lg px-3 py-3 text-sm text-bullish-text">
              If that email is registered, a reset link has been sent. Check your inbox.
            </div>
            <Link
              to="/login"
              className="block text-center text-sm text-accent hover:text-accent-hover font-medium"
            >
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <p className="text-sm text-text-muted">
              Enter your email and we'll send you a link to reset your password.
            </p>
            {error && (
              <div className="bg-bearish/10 border border-bearish/20 rounded-lg px-3 py-2 text-sm text-bearish-text">
                {error}
              </div>
            )}
            <input
              ref={emailRef}
              type="email"
              name="email"
              autoComplete="email"
              placeholder="Email"
              className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {loading ? "Sending..." : "Send Reset Link"}
            </button>
            <p className="text-center text-sm text-text-muted">
              <Link to="/login" className="text-accent hover:text-accent-hover font-medium">
                Back to sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function ResetForm({ token }: { token: string }) {
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [pwMismatch, setPwMismatch] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const password = passwordRef.current?.value ?? "";
    const confirm = confirmRef.current?.value ?? "";

    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: password,
      });
      setSuccess(true);
      // Redirect to login after a short delay
      setTimeout(() => navigate("/login", { replace: true }), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <div className="w-full max-w-sm space-y-5 rounded-xl border border-border-subtle bg-surface-1 p-8 shadow-elevated">
        <BrandHeader />

        {success ? (
          <div className="space-y-4">
            <div className="bg-bullish/10 border border-bullish/20 rounded-lg px-3 py-3 text-sm text-bullish-text">
              Password has been reset successfully. Redirecting to sign in...
            </div>
            <Link
              to="/login"
              className="block text-center text-sm text-accent hover:text-accent-hover font-medium"
            >
              Sign in now
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <p className="text-sm text-text-muted">Enter your new password.</p>
            {error && (
              <div className="bg-bearish/10 border border-bearish/20 rounded-lg px-3 py-2 text-sm text-bearish-text">
                {error}
              </div>
            )}
            <input
              ref={passwordRef}
              type="password"
              name="new-password"
              autoComplete="new-password"
              placeholder="New password (min 6 characters)"
              className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
              required
              minLength={6}
            />
            <div>
              <input
                ref={confirmRef}
                type="password"
                name="confirm-password"
                autoComplete="new-password"
                placeholder="Confirm new password"
                onChange={() => {
                  const pw = passwordRef.current?.value ?? "";
                  const cf = confirmRef.current?.value ?? "";
                  setPwMismatch(cf.length > 0 && pw !== cf);
                }}
                className={`w-full rounded-md border bg-surface-3 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:outline-none focus:ring-1 ${
                  pwMismatch
                    ? "border-bearish focus:border-bearish focus:ring-bearish/30"
                    : "border-border-subtle focus:border-accent focus:ring-accent/30"
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
              className="w-full rounded bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {loading ? "Resetting..." : "Reset Password"}
            </button>
            <p className="text-center text-sm text-text-muted">
              <Link to="/login" className="text-accent hover:text-accent-hover font-medium">
                Back to sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function BrandHeader() {
  return (
    <div className="flex items-center gap-2.5 mb-2">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent">
        <Crosshair className="h-4 w-4 text-white" />
      </div>
      <h1 className="font-display text-2xl font-bold text-text-primary">
        <span className="text-accent">Trade</span>CoPilot
      </h1>
    </div>
  );
}
