"use client";

import { useCallback, useEffect, useState } from "react";
import MarkdownBox from "@/components/ui/MarkdownBox";
import * as api from "@/lib/api";

export default function ContradictionPanel({ matterId }: { matterId: string }) {
  const [data, setData] = useState<{
    summary?: string;
    pairs?: Array<Record<string, unknown>>;
    sources?: Array<Record<string, string>>;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.fetchContradictions(matterId);
      setData(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load contradictions");
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 m-0">
        Finds inconsistencies between witness statements and documents in this matter only.
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr("");
            try {
              setData(await api.extractMatterContradictions(matterId));
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Analysis failed");
            } finally {
              setBusy(false);
            }
          }}
          className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Analyzing…" : "Analyze contradictions"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="px-4 py-2 border rounded-lg text-sm"
        >
          Refresh
        </button>
      </div>
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}

      {data?.pairs && data.pairs.length > 0 && (
        <div className="grid lg:grid-cols-2 gap-3">
          {data.pairs.map((pair, i) => (
            <div key={String(pair.contradiction_id || i)} className="rounded-xl border bg-white p-4 space-y-2 text-sm">
              <h3 className="font-semibold text-navy m-0">{String(pair.topic ?? "")}</h3>
              <div className="bg-red-50 border border-red-100 rounded-lg p-2">
                <span className="text-[0.65rem] font-semibold text-red-800">Statement A</span>
                <p className="m-0 text-slate-800">{String(pair.statement_a ?? "")}</p>
              </div>
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-2">
                <span className="text-[0.65rem] font-semibold text-blue-800">Statement B</span>
                <p className="m-0 text-slate-800">{String(pair.statement_b ?? "")}</p>
              </div>
              {pair.note ? (
                <p className="text-xs text-slate-600 m-0">{String(pair.note)}</p>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {data?.summary && (
        <div className="rounded-xl border bg-white p-4">
          <MarkdownBox content={data.summary} />
        </div>
      )}

      {!data?.pairs?.length && !busy && !err && (
        <p className="text-sm text-slate-500">
          No contradictions stored yet. Run analysis after documents are indexed.
        </p>
      )}
    </div>
  );
}
