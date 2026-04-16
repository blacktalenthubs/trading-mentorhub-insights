/** SSE hook for AI coach streaming responses.
 *
 *  Sends OHLCV bars with every request so the AI can analyze the actual chart.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "../stores/auth";
import type { OHLCBar } from "../api/hooks";

const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
  : "";

interface CoachMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChartContext {
  symbol: string;
  timeframe: string;
  bars: OHLCBar[];
}

/** Save a single message to the API (fire-and-forget). */
function persistMessage(role: string, content: string, symbol?: string) {
  const token = useAuthStore.getState().accessToken;
  if (!token || !content) return;
  fetch(`${API_HOST}/api/v1/coach-history/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ role, content, symbol }),
  }).catch(() => {}); // fire-and-forget
}

/** Load messages from API. */
async function loadMessagesFromAPI(): Promise<CoachMessage[]> {
  const token = useAuthStore.getState().accessToken;
  if (!token) return [];
  try {
    const res = await fetch(`${API_HOST}/api/v1/coach-history/messages?limit=50`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.map((m: any) => ({ role: m.role, content: m.content }));
  } catch { return []; }
}

export function useCoachStream() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const loadedRef = useRef(false);

  // Load from API on mount
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    loadMessagesFromAPI().then((msgs) => {
      if (msgs.length > 0) setMessages(msgs);
    });
  }, []);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // Store chart context as both ref (for immediate reads) and state (for re-renders)
  const chartContextRef = useRef<ChartContext | null>(null);

  const setChartContext = useCallback((ctx: ChartContext | null) => {
    chartContextRef.current = ctx;
  }, []);

  const sendMessage = useCallback(async (text: string, chartOverride?: ChartContext | null) => {
    const token = useAuthStore.getState().accessToken;
    if (!token) return;

    const userMsg: CoachMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    persistMessage("user", text, chartContextRef.current?.symbol);
    setStreaming(true);

    // Use explicit override first, then ref
    const chartCtx = chartOverride !== undefined ? chartOverride : chartContextRef.current;

    // Extract symbol from message pattern [Looking at SYMBOL]
    const symbolMatch = text.match(/\[Looking at ([^\]]+)\]/);
    const symbol = symbolMatch ? symbolMatch[1] : chartCtx?.symbol;

    const lastBars = chartCtx?.bars?.slice(-20);

    const body: Record<string, unknown> = {
      messages: [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      })),
      symbols: symbol ? [symbol] : undefined,
    };

    // Always include OHLCV bars if available
    if (lastBars && lastBars.length > 0) {
      body.ohlcv_bars = lastBars.map((b) => ({
        timestamp: b.timestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
      }));
      body.timeframe = chartCtx?.timeframe || "D";
    }

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_HOST}/api/v1/intel/coach`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = err.detail;
        if (res.status === 429 && typeof detail === "object" && detail?.error === "usage_limit_reached") {
          throw new Error(`Daily limit reached (${detail.limit} queries). Upgrade your plan for unlimited access.`);
        }
        if (res.status === 403 && typeof detail === "object" && detail?.error === "upgrade_required") {
          navigate("/billing");
          return;
        }
        throw new Error(typeof detail === "string" ? detail : detail?.message || "Coach request failed");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let assistantText = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data:")) {
            const dataStr = line.slice(5).trim();
            if (!dataStr) continue;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.text) {
                assistantText += parsed.text;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: "assistant",
                    content: assistantText,
                  };
                  return updated;
                });
              }
            } catch {
              // skip non-JSON lines
            }
          }
        }
      }
      // Persist complete assistant response to API
      if (assistantText) {
        persistMessage("assistant", assistantText, chartContextRef.current?.symbol);
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        const errMsg = (err as Error).message;
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: errMsg },
        ]);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [messages]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    // Clear from API too
    const token = useAuthStore.getState().accessToken;
    if (token) {
      fetch(`${API_HOST}/api/v1/coach-history/messages`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
  }, []);

  return { messages, streaming, sendMessage, stopStreaming, clearMessages, setChartContext };
}
