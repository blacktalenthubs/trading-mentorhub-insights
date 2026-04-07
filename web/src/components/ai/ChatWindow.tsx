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

/** Lightweight markdown-ish renderer for coach responses. */
function CoachMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={i} className="border-border-subtle my-2" />);
      continue;
    }

    // ## Header
    if (line.startsWith("## ")) {
      elements.push(
        <h3 key={i} className="text-sm font-bold text-accent mt-3 mb-1">
          {formatInline(line.slice(3))}
        </h3>
      );
      continue;
    }

    // # Header
    if (line.startsWith("# ")) {
      elements.push(
        <h2 key={i} className="text-sm font-bold text-text-primary mt-2 mb-1">
          {formatInline(line.slice(2))}
        </h2>
      );
      continue;
    }

    // SECTION LABEL: (all caps followed by colon, like CHART READ:, VERDICT:)
    const sectionMatch = line.match(/^([A-Z][A-Z /]+):(.*)$/);
    if (sectionMatch) {
      elements.push(
        <div key={i} className="mt-2">
          <span className="text-xs font-bold text-accent uppercase tracking-wide">{sectionMatch[1]}</span>
          {sectionMatch[2].trim() && (
            <span className="text-text-secondary ml-1">{formatInline(sectionMatch[2].trim())}</span>
          )}
        </div>
      );
      continue;
    }

    // Bullet point
    if (/^[•\-\*]\s/.test(line.trim())) {
      const bulletText = line.trim().replace(/^[•\-\*]\s/, "");
      elements.push(
        <div key={i} className="flex gap-1.5 ml-2">
          <span className="text-accent mt-0.5">&#8226;</span>
          <span className="text-text-secondary">{formatInline(bulletText)}</span>
        </div>
      );
      continue;
    }

    // Empty line
    if (!line.trim()) {
      elements.push(<div key={i} className="h-1" />);
      continue;
    }

    // Regular text
    elements.push(
      <p key={i} className="text-text-secondary">{formatInline(line)}</p>
    );
  }

  return <div className="space-y-0.5">{elements}</div>;
}

/** Format inline markdown: **bold**, *italic*, `code`, $price */
function formatInline(text: string): React.ReactNode {
  // Split on bold, italic, code patterns
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\$\d[\d,.]+)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="text-text-primary font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={i} className="text-text-muted italic">{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="text-accent bg-accent/10 px-1 rounded text-xs font-mono">{part.slice(1, -1)}</code>;
    }
    if (/^\$\d/.test(part)) {
      return <span key={i} className="text-text-primary font-mono font-medium">{part}</span>;
    }
    return part;
  });
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
            {m.role === "assistant" ? (
              <CoachMarkdown text={m.content} />
            ) : (
              <pre className="whitespace-pre-wrap font-body">{m.content}</pre>
            )}
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
