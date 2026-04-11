/** Pattern Education Panel — teaches WHY a setup works. */

import { CheckCircle, XCircle, BookOpen } from "lucide-react";

interface EducationData {
  what: string | null;
  why: string | null;
  confirm_items: string[];
  invalidation: string | null;
  risk: string | null;
  setup_type: string;
}

function Section({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h4 className={`text-[10px] font-bold uppercase tracking-wider ${color}`}>{title}</h4>
      <div className="text-[13px] text-text-secondary leading-relaxed">{children}</div>
    </div>
  );
}

export default function PatternEducation({ data }: { data: EducationData }) {
  if (!data.what && !data.why) {
    return null;
  }

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-bold text-text-primary">
          Learn: {data.setup_type}
        </h3>
      </div>

      {data.what && (
        <Section title="What Is It?" color="text-accent">
          <p>{data.what}</p>
        </Section>
      )}

      {data.why && (
        <Section title="Why It Works" color="text-yellow-400">
          <p className="whitespace-pre-line">{data.why}</p>
        </Section>
      )}

      {(data.confirm_items.length > 0 || data.invalidation) && (
        <Section title="How to Confirm" color="text-emerald-400">
          <div className="space-y-1">
            {data.confirm_items.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />
                <span>{item}</span>
              </div>
            ))}
            {data.invalidation && (
              <div className="flex items-start gap-2 mt-2">
                <XCircle className="h-3.5 w-3.5 text-red-400 mt-0.5 shrink-0" />
                <span className="text-red-400">{data.invalidation}</span>
              </div>
            )}
          </div>
        </Section>
      )}

      {data.risk && (
        <Section title="Risk Management" color="text-blue-400">
          <p className="whitespace-pre-line font-mono text-xs">{data.risk}</p>
        </Section>
      )}
    </div>
  );
}
