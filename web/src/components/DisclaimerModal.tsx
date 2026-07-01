/** Educational-use disclaimer. Shown ONCE per device as a modal (must acknowledge),
 *  then a subtle muted footer line stays on the feed as an ongoing reminder.
 *  Not financial advice · paper-trade-first for new traders. */

import { useState } from "react";
import { ShieldAlert } from "lucide-react";

const ACK_KEY = "disclaimer_ack_v1";

export default function DisclaimerModal() {
  const [ack, setAck] = useState<boolean>(() => {
    try { return localStorage.getItem(ACK_KEY) === "1"; } catch { return true; }
  });
  if (ack) return null;

  function accept() {
    try { localStorage.setItem(ACK_KEY, "1"); } catch { /* private mode — just dismiss */ }
    setAck(true);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm rounded-2xl border border-border-subtle bg-surface-1 p-6 shadow-2xl">
        <div className="mb-3 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-warning-text" />
          <h2 className="text-base font-semibold text-text-primary">Before you start</h2>
        </div>
        <p className="text-sm leading-relaxed text-text-secondary">
          TradeSignal is an <span className="font-medium text-text-primary">educational tool</span>. These
          alerts and setups are for learning the mechanics of price action —{" "}
          <span className="font-medium text-text-primary">not financial advice</span>. If you're new to a
          strategy, <span className="font-medium text-text-primary">paper trade it first</span> to see how it
          actually behaves before risking real money. Trading involves risk of loss.
        </p>
        <button
          onClick={accept}
          className="mt-5 w-full rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent/90 active:scale-[0.99]"
        >
          I understand
        </button>
      </div>
    </div>
  );
}

/** Subtle, always-present reminder — drop at the bottom of a feed/page. */
export function DisclaimerFooter() {
  return (
    <p className="px-4 py-3 text-center text-[10px] leading-relaxed text-text-faint">
      Educational purposes only — not financial advice. New to these setups? Paper trade them first.
    </p>
  );
}
