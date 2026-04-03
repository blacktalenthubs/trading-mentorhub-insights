/** SSE hook for real-time alert stream (Pro only). */

import { Capacitor } from "@capacitor/core";
import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "../stores/auth";
import { useFeatureGate } from "./useFeatureGate";

const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
  : "";

export interface AlertEvent {
  symbol: string;
  alert_type: string;
  direction: string;
  price: number;
  message: string;
}

export function useAlertStream(onAlert?: (alert: AlertEvent) => void) {
  const { isPro } = useFeatureGate();
  const token = useAuthStore((s) => s.accessToken);
  const [connected, setConnected] = useState(false);
  const [lastAlert, setLastAlert] = useState<AlertEvent | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!isPro || !token) return;

    const es = new EventSource(`${API_HOST}/api/v1/alerts/stream`);
    esRef.current = es;

    es.addEventListener("alert", (e) => {
      try {
        const data: AlertEvent = JSON.parse(e.data);
        setLastAlert(data);
        onAlert?.(data);
      } catch {
        // ignore malformed events
      }
    });

    es.addEventListener("ping", () => {
      setConnected(true);
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [isPro, token]);

  return { connected, lastAlert };
}
