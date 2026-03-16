/** Streaming chat UI for AI coach. */

import { useRef, useEffect, useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  messages: Message[];
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onClear: () => void;
}

export default function ChatWindow({ messages, streaming, onSend, onStop, onClear }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    onSend(text);
  }

  return (
    <div className="flex h-[calc(100dvh-14rem)] max-h-[600px] min-h-[300px] flex-col rounded-lg border border-border-subtle bg-surface-2">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-sm text-text-faint">
            Ask your AI trade coach anything — open positions, market context, trade reviews...
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              m.role === "user"
                ? "ml-auto bg-accent-muted text-text-primary"
                : "bg-surface-3 text-text-secondary"
            }`}
          >
            <pre className="whitespace-pre-wrap font-body">{m.content}</pre>
          </div>
        ))}
        {streaming && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
            Thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border-subtle p-3">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the coach..."
            className="flex-1 rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              className="rounded bg-bearish px-4 py-2 text-sm font-medium text-white hover:opacity-80"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
            >
              Send
            </button>
          )}
          <button
            type="button"
            onClick={onClear}
            className="rounded bg-surface-4 px-3 py-2 text-xs text-text-muted hover:text-text-secondary"
          >
            Clear
          </button>
        </form>
      </div>
    </div>
  );
}
