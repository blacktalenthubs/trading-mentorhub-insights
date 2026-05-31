/** AppleSignInButton — Sign in with Apple using Apple's vanilla JS SDK
 *  (loaded in index.html). Posts the returned ID token to /auth/apple
 *  and stores the same JWT pair as a password login. Hidden when no
 *  VITE_APPLE_CLIENT_ID (Services ID) is configured.
 *
 *  Quirks worth knowing:
 *    - Apple includes the user's name ONLY on the first sign-in, and only
 *      via a separate `user` payload (not inside the JWT). We forward it
 *      to the backend so first-time accounts get a real display name.
 *    - Subsequent sign-ins return only the ID token; that's expected.
 *    - Apple requires HTTPS even for popup mode, so this won't work over
 *      plain http://localhost. Use ngrok or test against staging.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuthStore } from "../stores/auth";
import type { AuthTokens } from "../types";

declare global {
  interface Window {
    AppleID?: {
      auth: {
        init: (config: {
          clientId: string;
          scope: string;
          redirectURI: string;
          state?: string;
          usePopup: boolean;
        }) => void;
        signIn: () => Promise<AppleSignInResponse>;
      };
    };
  }
}

interface AppleSignInResponse {
  authorization: { code: string; id_token: string; state?: string };
  // `user` is only present on the FIRST sign-in for a given Apple ID
  user?: { name?: { firstName?: string; lastName?: string }; email?: string };
}

interface Props {
  destination: "/onboarding" | "/trading";
}

export default function AppleSignInButton({ destination }: Props) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const initRef = useRef(false);

  const clientId = import.meta.env.VITE_APPLE_CLIENT_ID as string | undefined;

  useEffect(() => {
    if (!clientId || initRef.current) return;
    // Poll for the SDK (loaded async in index.html). Cheap — once it's
    // there we init exactly once and stop polling.
    const poll = setInterval(() => {
      if (window.AppleID?.auth) {
        clearInterval(poll);
        try {
          window.AppleID.auth.init({
            clientId,
            scope: "name email",
            redirectURI: window.location.origin,  // popup mode: Apple bounces back here
            usePopup: true,
          });
          initRef.current = true;
          setReady(true);
        } catch (e) {
          setError("Could not initialise Apple sign-in.");
          console.error("[AppleID.init]", e);
        }
      }
    }, 200);
    return () => clearInterval(poll);
  }, [clientId]);

  if (!clientId) return null;

  async function handleClick() {
    if (!window.AppleID?.auth) { setError("Apple sign-in is still loading — try again in a moment."); return; }
    setError("");
    setLoading(true);
    try {
      const resp = await window.AppleID.auth.signIn();
      const { getAttribution } = await import("../lib/attribution");
      const attr = getAttribution();
      const data = await api.post<AuthTokens>("/auth/apple", {
        id_token: resp.authorization.id_token,
        user_first_name: resp.user?.name?.firstName,
        user_last_name: resp.user?.name?.lastName,
        utm_source: attr?.utm_source,
        utm_medium: attr?.utm_medium,
        utm_campaign: attr?.utm_campaign,
        referrer: attr?.referrer,
      });
      await setAuth(data.user, data.access_token, data.refresh_token);
      navigate(destination, { replace: true });
    } catch (err: unknown) {
      // Apple throws { error: "popup_closed_by_user" } on cancel — silent
      const code = (err as { error?: string })?.error;
      if (code === "popup_closed_by_user") {
        setError("");
      } else {
        setError(err instanceof Error ? err.message : "Apple sign-in failed");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={loading || !ready}
        aria-busy={loading}
        className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-black border border-black text-white py-2.5 text-sm font-semibold hover:bg-black/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
        </svg>
        {loading ? "Signing in…" : "Continue with Apple"}
      </button>
      {error && <p className="text-center text-xs text-bearish-text">{error}</p>}
    </div>
  );
}
