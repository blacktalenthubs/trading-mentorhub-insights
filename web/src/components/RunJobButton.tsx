/**
 * Run a scheduled scan on demand (admin). POSTs to /intel/jobs/<name>/run, then polls the job
 * status until it finishes and invalidates the query that renders its report so the UI refreshes.
 * A job already running isn't double-started. Non-admins just get a 403 toast.
 */
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { useJobs, useRunJob } from "../api/hooks";
import { toast } from "./Toast";

export default function RunJobButton({ job, invalidateKey, label = "Run now", className = "" }: {
  job: string;
  invalidateKey: string[];   // react-query key prefix to invalidate when the job lands
  label?: string;
  className?: string;
}) {
  const qc = useQueryClient();
  const run = useRunJob();
  const [active, setActive] = useState(false);
  const startedRef = useRef(false);
  const { data } = useJobs({ poll: active });

  useEffect(() => {
    if (!active || !data) return;
    const j = data.jobs.find((x) => x.name === job);
    // Wait until we've seen it running at least once, then for it to flip back to idle.
    if (j?.running) { startedRef.current = true; return; }
    if (startedRef.current && j && !j.running) {
      setActive(false);
      startedRef.current = false;
      qc.invalidateQueries({ queryKey: invalidateKey });
      if (j.ok === false) toast.error(`${j.label} run failed${j.error ? ` (${j.error})` : ""}`);
      else toast.success(`${j.label} refreshed`);
    }
  }, [data, active, job, qc, invalidateKey]);

  const busy = active || run.isPending;
  const onClick = () => {
    run.mutate(job, {
      onSuccess: (d) => {
        setActive(true);
        toast.info(d.already_running ? `${label} already running…` : `${label}…`);
      },
      onError: () => toast.error("Couldn't start — admin only"),
    });
  };
  return (
    <button onClick={onClick} disabled={busy} title="Run this scan now"
      className={`inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-1 px-2.5 py-1.5 text-[11.5px] font-semibold text-text-secondary hover:border-accent hover:text-text-primary disabled:opacity-60 ${className}`}>
      <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
      {busy ? "Running…" : label}
    </button>
  );
}
