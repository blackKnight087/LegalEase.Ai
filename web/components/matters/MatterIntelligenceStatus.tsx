"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  idle: "Waiting",
  starting: "Starting…",
  entities: "Extracting entities…",
  evidence: "Analyzing evidence…",
  timeline: "Building timeline…",
  hearings: "Extracting hearings…",
  contradictions: "Finding contradictions…",
  ready: "Ready",
  failed: "Failed",
};

export default function MatterIntelligenceStatus({ matterId }: { matterId: string }) {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const s = await api.getMatterIntelStatus(matterId);
      setStatus(s);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load status");
    }
  }, [matterId]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 4000);
    return () => clearInterval(t);
  }, [load]);

  const stage = String(status?.stage || "idle");
  const progress = (status?.progress || {}) as Record<string, number>;
  const running = ["starting", "entities", "evidence", "timeline", "hearings", "contradictions"].includes(
    stage
  );

  return (
    <div className="rounded-xl border bg-white p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-navy m-0">Matter intelligence</h3>
          <p className="text-xs text-slate-500 m-0 mt-0.5">
            {STAGE_LABELS[stage] || stage}
            {status?.message ? ` — ${String(status.message)}` : ""}
          </p>
        </div>
        <button
          type="button"
          disabled={busy || running}
          onClick={async () => {
            setBusy(true);
            setErr("");
            try {
              await api.runMatterIntelligence(matterId);
              await load();
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Pipeline failed");
            } finally {
              setBusy(false);
            }
          }}
          className="px-3 py-1.5 text-xs font-medium bg-navy text-white rounded-lg disabled:opacity-50"
        >
          {busy || running ? "Running…" : "Run full analysis"}
        </button>
      </div>
      {Object.keys(progress).length > 0 && (
        <div className="flex flex-wrap gap-2 text-[0.65rem]">
          {Object.entries(progress).map(([k, v]) => (
            <span key={k} className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
              {k}: {v}
            </span>
          ))}
        </div>
      )}
      {stage === "failed" && status?.last_error ? (
        <p className="text-xs text-red-600 m-0 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {String(status.last_error)}
        </p>
      ) : null}
      {err && (
        <p className="text-xs text-red-600 m-0">{err}</p>
      )}
    </div>
  );
}
