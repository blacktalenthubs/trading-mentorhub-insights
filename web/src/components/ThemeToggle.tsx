/** Dark/light theme toggle — a one-click button for the Trading top bar.
 *
 *  Reuses the app-wide mechanism (the same one Settings → Appearance uses):
 *  toggles the `light` class on <html> and persists `localStorage.theme`. The
 *  boot script in index.html re-applies it on load, so the choice sticks across
 *  reloads and pages. Every component reads CSS variables, so the whole app
 *  re-themes for free.
 */

import { useState } from "react";
import { Moon, Sun } from "lucide-react";

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(
    () => !document.documentElement.classList.contains("light"),
  );

  function toggle() {
    const next = !isDark;
    setIsDark(next);
    if (next) {
      document.documentElement.classList.remove("light");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.add("light");
      localStorage.setItem("theme", "light");
    }
  }

  return (
    <button
      onClick={toggle}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle color theme"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border-subtle bg-surface-2 text-text-muted hover:bg-surface-3 hover:text-text-secondary transition-colors text-[11px] shrink-0"
    >
      {isDark ? <Moon className="h-3 w-3" /> : <Sun className="h-3 w-3" />}
      <span className="font-medium">{isDark ? "Dark" : "Light"}</span>
    </button>
  );
}
