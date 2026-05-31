/** GoogleSignInButton — one-tap Google credential flow used on the
 *  Register and Login pages. Posts the Google ID token to /auth/google
 *  and stores the same JWT pair as a password login. Hidden when no
 *  VITE_GOOGLE_CLIENT_ID is configured (the GoogleOAuthProvider in
 *  App.tsx is a pass-through in that case, so <GoogleLogin> would crash).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { api } from "../api/client";
import { useAuthStore } from "../stores/auth";
import type { AuthTokens } from "../types";

interface Props {
  /** Where to send the user on success. Register hits /onboarding, login /trading. */
  destination: "/onboarding" | "/trading";
}

export default function GoogleSignInButton({ destination }: Props) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Hide entirely when no Client ID is configured — GoogleOAuthProvider is
  // a no-op without it, and <GoogleLogin> would throw "GoogleOAuthProvider
  // not found" in that case.
  if (!import.meta.env.VITE_GOOGLE_CLIENT_ID) return null;

  async function handleCredential(credential: string) {
    setError("");
    setLoading(true);
    try {
      const { getAttribution } = await import("../lib/attribution");
      const attr = getAttribution();
      const data = await api.post<AuthTokens>("/auth/google", {
        credential,
        utm_source: attr?.utm_source,
        utm_medium: attr?.utm_medium,
        utm_campaign: attr?.utm_campaign,
        referrer: attr?.referrer,
      });
      await setAuth(data.user, data.access_token, data.refresh_token);
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-center" aria-busy={loading}>
        <GoogleLogin
          onSuccess={(cr) => cr.credential && handleCredential(cr.credential)}
          onError={() => setError("Google sign-in failed")}
          theme="filled_black"
          shape="rectangular"
          text="continue_with"
          size="large"
          width="320"
        />
      </div>
      {error && <p className="text-center text-xs text-bearish-text">{error}</p>}
    </div>
  );
}
