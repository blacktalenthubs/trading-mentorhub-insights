/** SSE hook for AI coach streaming responses. */

import { useCallback, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "../stores/auth";

const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
  : "";

interface CoachMessage {
  role: "user" | "assistant";
  content: string;
}

export function useCoachStream() {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    const token = useAuthStore.getState().accessToken;
    if (!token) return;

    const userMsg: CoachMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    const body = {
      messages: [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      })),
    };

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
        throw new Error(err.detail || "Coach request failed");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let assistantText = "";

      // Add placeholder assistant message
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // Parse SSE events
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
              // skip non-JSON lines (event: done, etc.)
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${(err as Error).message}` },
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

  return { messages, streaming, sendMessage, stopStreaming, clearMessages };
}
