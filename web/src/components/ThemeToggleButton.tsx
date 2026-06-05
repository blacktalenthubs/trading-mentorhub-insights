/** One-tap light/dark theme toggle. Reuses the same mechanism as the Settings
 *  toggle (a `.light` class on <html> + localStorage "theme"), surfaced in the
 *  global chrome so it's one tap from anywhere. Shows the icon for the theme
 *  you'll switch TO (Sun while dark, Moon while light).
 */

import { useState } from "react";
import { Sun, Moon } from "lucide-react";

function applyTheme(dark: boolean) {
  if (dark) {
    document.documentElement.classList.remove("light");
    localStorage.setItem("theme", "dark");
  } else {
    document.documentElement.classList.add("light");
    localStorage.setItem("theme", "light");
  }
}

export default function ThemeToggleButton({ variant = "icon" }: { variant?: "icon" | "tab" }) {
  const [isDark, setIsDark] = useState(() => !document.documentElement.classList.contains("light"));
  function toggle() {
    const next = !isDark;
    setIsDark(next);
    applyTheme(next);
  }
  const Icon = isDark ? Sun : Moon;

  if (variant === "tab") {
    // Mobile bottom-nav item — matches the NavLink tab styling.
    return (
      <button
        onClick={toggle}
        aria-label="Toggle light/dark theme"
        className="flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium tracking-wide text-text-muted active:text-accent transition-colors"
      >
        <Icon className="h-5 w-5" />
        Theme
      </button>
    );
  }

  // Desktop sidebar icon button — matches the logout/collapse buttons.
  return (
    <button
      onClick={toggle}
      aria-label="Toggle light/dark theme"
      className="group relative flex items-center justify-center w-8 h-8 text-text-faint hover:text-text-secondary transition-colors"
    >
      <Icon className="h-4 w-4" />
      <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
        {isDark ? "Light mode" : "Dark mode"}
      </span>
    </button>
  );
}
