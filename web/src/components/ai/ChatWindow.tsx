/** Streaming chat UI for AI coach. */

import { useRef, useEffect, useState } from "react";
import { Link } from "react-router-dom";

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

/** Parse ACTION/POSITION block from coach response. */
function parseActionBlock(text: string): {
  type: "action" | "position" | null;
  direction?: string;
  entry?: string;
  stop?: string;
  t1?: string;
  t2?: string;
  rr?: string;
  conviction?: string;
  watch?: string;
  // position fields
  status?: string;
  moveStop?: string;
  nextTarget?: string;
  exitIf?: string;
} {
  const lines = text.split("\n");
  let inBlock = false;
  let blockType: "action" | "position" | null = null;
  const data: Record<string, string> = {};

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "ACTION:") { inBlock = true; blockType = "action"; continue; }
    if (trimmed === "POSITION:") { inBlock = true; blockType = "position"; continue; }
    if (inBlock && /^[A-Z][A-Z /]+:/.test(trimmed) && !trimmed.startsWith("Entry") && !trimmed.startsWith("Stop") &&
        !trimmed.startsWith("T1") && !trimmed.startsWith("T2") && !trimmed.startsWith("R:R") &&
        !trimmed.startsWith("Direction") && !trimmed.startsWith("Conviction") && !trimmed.startsWith("Watch") &&
        !trimmed.startsWith("Status") && !trimmed.startsWith("Move") && !trimmed.startsWith("Next") &&
        !trimmed.startsWith("Exit")) {
      inBlock = false;
    }
    if (inBlock) {
      const match = trimmed.match(/^([^:]+):\s*(.+)$/);
      if (match) {
        const key = match[1].trim().toLowerCase().replace(/\s+/g, "_");
        data[key] = match[2].trim();
      }
    }
  }

  if (!blockType) return { type: null };
  return {
    type: blockType,
    direction: data["direction"],
    entry: data["entry"],
    stop: data["stop"],
    t1: data["t1"],
    t2: data["t2"],
    rr: data["r:r"] || data["rr"],
    conviction: data["conviction"],
    watch: data["watch"],
    status: data["status"],
    moveStop: data["move_stop_to"],
    nextTarget: data["next_target"],
    exitIf: data["exit_if"],
  };
}

/** Rich ACTION card for trade entries. */
function ActionCard({ block }: { block: ReturnType<typeof parseActionBlock> }) {
  if (block.type === "action" && block.direction) {
    const isLong = block.direction.toUpperCase() === "LONG";
    const isWait = block.direction.toUpperCase() === "WAIT";
    const dirColor = isWait ? "bg-yellow-500/20 text-yellow-400" : isLong ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400";
    const borderColor = isWait ? "border-yellow-500/30" : isLong ? "border-emerald-500/30" : "border-red-500/30";

    return (
      <div className={`my-2 rounded-lg border ${borderColor} bg-surface-3/50 p-3`}>
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${dirColor}`}>
            {block.direction.toUpperCase()}
          </span>
          {block.conviction && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              block.conviction.toUpperCase() === "HIGH" ? "bg-emerald-500/20 text-emerald-400" :
              block.conviction.toUpperCase() === "MEDIUM" ? "bg-yellow-500/20 text-yellow-400" :
              "bg-red-500/20 text-red-400"
            }`}>
              {block.conviction.toUpperCase()}
            </span>
          )}
          {block.rr && (
            <span className="text-xs text-text-muted font-mono">R:R {block.rr}</span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {block.entry && (
            <div><span className="text-text-muted">Entry:</span> <span className="text-text-primary font-mono">{block.entry}</span></div>
          )}
          {block.stop && (
            <div><span className="text-text-muted">Stop:</span> <span className="text-red-400 font-mono">{block.stop}</span></div>
          )}
          {block.t1 && (
            <div><span className="text-text-muted">T1:</span> <span className="text-emerald-400 font-mono">{block.t1}</span></div>
          )}
          {block.t2 && (
            <div><span className="text-text-muted">T2:</span> <span className="text-emerald-400 font-mono">{block.t2}</span></div>
          )}
        </div>
        {block.watch && (
          <div className="mt-2 text-xs text-yellow-400">
            Watch: {block.watch}
          </div>
        )}
      </div>
    );
  }

  if (block.type === "position" && block.status) {
    const isHold = block.status.toUpperCase() === "HOLD";
    const isExit = block.status.toUpperCase() === "EXIT";
    const statusColor = isExit ? "bg-red-500/20 text-red-400" : isHold ? "bg-emerald-500/20 text-emerald-400" : "bg-yellow-500/20 text-yellow-400";

    return (
      <div className="my-2 rounded-lg border border-blue-500/30 bg-surface-3/50 p-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-bold text-blue-400">POSITION MGMT</span>
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${statusColor}`}>
            {block.status.toUpperCase()}
          </span>
        </div>
        <div className="space-y-1 text-xs">
          {block.moveStop && (
            <div><span className="text-text-muted">Move stop to:</span> <span className="text-yellow-400 font-mono">{block.moveStop}</span></div>
          )}
          {block.nextTarget && (
            <div><span className="text-text-muted">Next target:</span> <span className="text-emerald-400 font-mono">{block.nextTarget}</span></div>
          )}
          {block.exitIf && (
            <div><span className="text-text-muted">Exit if:</span> <span className="text-red-400">{block.exitIf}</span></div>
          )}
        </div>
      </div>
    );
  }

  return null;
}

/** Lightweight markdown-ish renderer for coach responses. */
function CoachMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];

  // Check for ACTION/POSITION block and render as rich card
  const actionBlock = parseActionBlock(text);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Skip lines that are part of the ACTION/POSITION block (rendered as card)
    if (actionBlock.type) {
      const trimmed = line.trim();
      if (trimmed === "ACTION:" || trimmed === "POSITION:") {
        elements.push(<ActionCard key={`action-${i}`} block={actionBlock} />);
        // Skip subsequent lines that belong to the block
        while (i + 1 < lines.length) {
          const nextLine = lines[i + 1].trim();
          if (!nextLine || /^(Direction|Entry|Stop|T1|T2|R:R|Conviction|Watch|Status|Move|Next|Exit):/i.test(nextLine)) {
            i++;
          } else {
            break;
          }
        }
        continue;
      }
    }

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
              m.content.toLowerCase().includes("limit reached") || m.content.toLowerCase().includes("upgrade") ? (
                <div className="text-center py-2">
                  <p className="text-text-secondary text-sm mb-3">{m.content}</p>
                  <Link
                    to="/billing"
                    className="inline-block px-4 py-2 rounded-lg bg-accent text-white text-sm font-semibold hover:bg-accent-hover transition-colors"
                  >
                    Upgrade Plan →
                  </Link>
                </div>
              ) : (
                <CoachMarkdown text={m.content} />
              )
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
