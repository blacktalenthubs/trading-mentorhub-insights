/** StickyLandingCTA — pinned bottom bar that appears once the user scrolls
 *  past the hero, so the primary action stays one tap away on long scrolls.
 *  Mobile-first (full width, bottom). On md+ it sits as a centered pill.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

export default function StickyLandingCTA() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      // Show after ~80% of the viewport has scrolled — past the hero on any screen
      const threshold = Math.max(480, window.innerHeight * 0.8);
      setVisible(window.scrollY > threshold);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      aria-hidden={!visible}
      className={[
        "fixed inset-x-0 bottom-0 z-40 pointer-events-none",
        "transition-all duration-300 ease-out",
        visible ? "translate-y-0 opacity-100" : "translate-y-full opacity-0",
      ].join(" ")}
    >
      <div className="mx-auto max-w-3xl px-3 pb-3 md:pb-4">
        <div className="pointer-events-auto flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface-1/95 backdrop-blur px-4 py-3 shadow-2xl shadow-black/40">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-text-primary truncate">
              Try BusyTradersDesk free for 3 days
            </p>
            <p className="text-[11px] text-text-faint truncate">
              No card required · Cancel anytime
            </p>
          </div>
          <Link
            to="/register"
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-base hover:bg-accent/90 transition-colors whitespace-nowrap"
          >
            Start free
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
