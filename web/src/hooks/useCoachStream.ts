/** SSE hook for AI coach streaming responses.
 *
 *  Sends OHLCV bars with every request so the AI can analyze the actual chart.
 */

import { useCallback, useRef, useState } from "react";
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

export function useCoachStream() {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
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
          throw new Error(`${detail.required_tier?.charAt(0).toUpperCase()}${detail.required_tier?.slice(1)} subscription required.`);
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
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: (err as Error).message },
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
  }, []);

  return { messages, streaming, sendMessage, stopStreaming, clearMessages, setChartContext };
}
