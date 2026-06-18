"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

export default function EvidenceAlertsPanel() {
  const [summary, setSummary] = useState<api.EvidenceDeskResponse["summary"] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const d = await api.fetchEvidenceDesk();
      setSummary(d.summary || null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load evidence summary");
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cx = summary?.contradiction_count ?? 0;
  const blind = summary?.blind_spot_count ?? 0;

  return (
    <section className="rounded-xl sm:rounded-2xl border border-violet-200 bg-violet-50/40 p-3 sm:p-5 shadow-sm">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="text-sm font-semibold text-navy m-0">Evidence alerts</h2>
          <p className="text-xs text-slate-500 m-0 mt-0.5">
            Contradictions and blind spots across matters
          </p>
        </div>
        <Link
          href="/litigation?tab=evidence"
          className="text-xs font-medium text-violet-700 hover:underline shrink-0"
        >
          Open Evidence →
        </Link>
      </div>
      {err && <p className="text-xs text-red-600 m-0">{err}</p>}
      {summary && !err && (
        <div className="flex flex-wrap gap-4 text-sm">
          <p className="m-0">
            <span className="font-bold text-navy">{cx}</span>
            <span className="text-slate-600"> contradiction{cx === 1 ? "" : "s"}</span>
          </p>
          {blind > 0 && (
            <p className="m-0 text-amber-800">
              <span className="font-bold">{blind}</span> matter{blind === 1 ? "" : "s"} need scan
            </p>
          )}
          {cx === 0 && blind === 0 && (
            <p className="text-xs text-slate-500 m-0">No issues flagged — upload docs and scan in Evidence tab.</p>
          )}
        </div>
      )}
    </section>
  );
}
