/**
 * "Data & Jobs" — a collapsible control strip for the Today tab. Lists every runnable job
 * (from GET /intel/jobs) with how long ago it last produced its report, a stale badge, and a
 * Run button. Admin-only: the endpoint 403s for non-admins, so `jobs` is empty and the panel
 * hides itself. Running a job invalidates the Today bundle so the section refreshes in place.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { useJobs } from "../api/hooks";
import RunJobButton from "./RunJobButton";

function age(iso: string | null): { text: string; tone: string; stale: boolean } {
  if (!iso) return { text: "never run", tone: "text-rose-400", stale: true };
  const ms = Date.now() - new Date(iso).getTime();
  const h = ms / 3.6e6;
  const text =
    h < 1 ? `${Math.max(1, Math.round(ms / 6e4))}m ago` : h < 24 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)}d ago`;
  const tone = h >= 24 ? "text-rose-400" : h >= 12 ? "text-amber-400" : "text-text-faint";
  return { text, tone, stale: h >= 24 };
}

export default function JobsPanel() {
  const [open, setOpen] = useState(false);
  const { data } = useJobs();
  const jobs = data?.jobs ?? [];
  if (jobs.length === 0) return null; // non-admin or not yet loaded

  const staleCount = jobs.filter((j) => age(j.last_run).stale).length;

  return (
    <div className="rounded-xl border border-border-default bg-surface-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-[13px] font-semibold text-text-primary">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Data &amp; Jobs
          {staleCount > 0 && (
            <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-400">
              {staleCount} stale
            </span>
          )}
        </span>
        <span className="text-[11px] text-text-faint">{jobs.length} jobs · run any on demand</span>
      </button>

      {open && (
        <div className="grid grid-cols-1 gap-1.5 border-t border-border-default p-3 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.map((j) => {
            const a = age(j.last_run);
            return (
              <div
                key={j.name}
                className="flex items-center justify-between gap-2 rounded-lg border border-border-default bg-surface-2 px-2.5 py-1.5"
              >
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium text-text-primary" title={j.kind}>
                    {j.label}
                  </div>
                  <div className={`text-[10.5px] ${a.tone}`}>{j.running ? "running…" : a.text}</div>
                </div>
                <RunJobButton job={j.name} invalidateKey={["market-report"]} label="Run" className="shrink-0" />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
