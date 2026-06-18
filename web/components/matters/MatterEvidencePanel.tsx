"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

const IMPORTANCE_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-900 border-red-200",
  high: "bg-orange-100 text-orange-900 border-orange-200",
  strong: "bg-emerald-100 text-emerald-900 border-emerald-200",
  medium: "bg-slate-100 text-slate-700 border-slate-200",
  weak: "bg-amber-100 text-amber-800 border-amber-200",
};

export default function MatterEvidencePanel({ matterId }: { matterId: string }) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.listMatterEvidence(matterId);
      setItems(r.evidence || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load evidence");
      setItems([]);
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await api.getMatterIntelStatus(matterId);
        const stage = String(s.stage || "idle");
        if (stage === "ready" || stage === "failed") await load();
      } catch {
        /* ignore */
      }
    };
    void poll();
    const t = setInterval(() => void poll(), 5000);
    return () => clearInterval(t);
  }, [matterId, load]);

  const extract = async () => {
    setBusy(true);
    setErr("");
    setSuccess("");
    try {
      const r = await api.extractMatterEvidence(matterId);
      setItems(r.evidence || []);
      setSuccess(`Extracted ${r.count ?? items.length} evidence item(s).`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Evidence extraction failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void extract()}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Extracting evidence…" : "Extract evidence from documents"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          Refresh
        </button>
      </div>
      {success && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 m-0">
          {success}
        </p>
      )}
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}
      <div className="grid md:grid-cols-2 gap-3">
        {items.map((ev, i) => {
          const imp = String(ev.importance || ev.strength || "medium").toLowerCase();
          const desc = String(ev.description || ev.notes || "");
          return (
            <article
              key={String(ev.evidence_id)}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-2"
            >
              <div className="flex justify-between gap-2 items-start">
                <div>
                  <p className="text-[0.65rem] uppercase text-slate-500 m-0">Evidence {i + 1}</p>
                  <h3 className="font-semibold text-navy m-0 text-sm">{String(ev.title)}</h3>
                </div>
                <span
                  className={`text-[0.65rem] uppercase font-bold px-2 py-0.5 rounded-full border ${
                    IMPORTANCE_STYLES[imp] || IMPORTANCE_STYLES.medium
                  }`}
                >
                  {imp}
                </span>
              </div>
              <p className="text-xs text-slate-600 m-0 capitalize">
                <span className="font-semibold">Type:</span>{" "}
                {String(ev.type || ev.category || "document")}
              </p>
              {ev.source_document || ev.tags ? (
                <p className="text-xs text-slate-500 m-0">
                  <span className="font-semibold">Source:</span>{" "}
                  {String(ev.source_document || ev.tags)}
                  {ev.page_number ? ` · p.${String(ev.page_number)}` : ""}
                </p>
              ) : null}
              {ev.person_related ? (
                <p className="text-xs text-slate-600 m-0">
                  <span className="font-semibold">Related:</span> {String(ev.person_related)}
                </p>
              ) : null}
              {desc ? (
                <p className="text-sm text-slate-700 m-0">
                  <span className="font-semibold">Description:</span> {desc}
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
      {!items.length && !busy && !err && (
        <p className="text-sm text-slate-500 m-0">
          No evidence yet. Upload court documents, then extract — or wait for automatic analysis after
          upload.
        </p>
      )}
    </div>
  );
}
