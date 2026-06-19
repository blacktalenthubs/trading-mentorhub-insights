/** UpdatePrompt — shows a "New version available · Reload" banner when the PWA
 *  service worker has a fresh build cached. Fixes the stale-bundle problem where
 *  deploys silently served old JS until a manual cache clear.
 */

import { useRegisterSW } from "virtual:pwa-register/react";
import { RefreshCw } from "lucide-react";

export default function UpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      // Check for a new build OFTEN — every 60s and whenever the tab regains focus —
      // so the update prompt appears within ~a minute of a deploy. Was 60min, which is
      // why fresh deploys appeared to "not ship" until a manual hard-refresh.
      if (registration) {
        const check = () => registration.update().catch(() => {});
        setInterval(check, 60 * 1000);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") check();
        });
      }
    },
  });

  if (!needRefresh) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-3 bg-surface-1 border border-accent/30 rounded-xl px-4 py-2.5 shadow-elevated"
      style={{ marginBottom: "env(safe-area-inset-bottom)" }}
    >
      <RefreshCw className="h-4 w-4 text-accent shrink-0" />
      <span className="text-sm text-text-primary">A new version is available.</span>
      <button
        onClick={() => updateServiceWorker(true)}
        className="text-xs font-semibold bg-accent text-white px-3 py-1.5 rounded-lg hover:bg-accent-hover transition-colors"
      >
        Reload
      </button>
      <button
        onClick={() => setNeedRefresh(false)}
        className="text-xs text-text-muted hover:text-text-primary transition-colors"
      >
        Later
      </button>
    </div>
  );
}
