/** Minimal toast notification system.
 *
 *  Usage:
 *    import { toast } from "../components/Toast";
 *    toast.success("Symbol added");
 *    toast.error("Failed to remove");
 *
 *  Mount <ToastContainer /> once in your app root.
 */

import { useState, useCallback } from "react";
import { Check, X, AlertTriangle, Info } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

let _addToast: ((message: string, type: ToastType) => void) | null = null;
let _nextId = 0;

export const toast = {
  success: (message: string) => _addToast?.(message, "success"),
  error: (message: string) => _addToast?.(message, "error"),
  info: (message: string) => _addToast?.(message, "info"),
};

const ICONS = {
  success: <Check className="h-3.5 w-3.5" />,
  error: <AlertTriangle className="h-3.5 w-3.5" />,
  info: <Info className="h-3.5 w-3.5" />,
};

const STYLES = {
  success: "bg-bullish/10 border-bullish/20 text-bullish-text",
  error: "bg-bearish/10 border-bearish/20 text-bearish-text",
  info: "bg-accent/10 border-accent/20 text-accent",
};

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  _addToast = useCallback((message: string, type: ToastType) => {
    const id = ++_nextId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium shadow-elevated animate-in slide-in-from-right ${STYLES[t.type]}`}
          style={{ animation: "slideIn 0.2s ease-out" }}
        >
          {ICONS[t.type]}
          {t.message}
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="ml-2 opacity-50 hover:opacity-100"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
