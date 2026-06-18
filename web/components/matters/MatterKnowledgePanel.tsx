"use client";

import { useCallback, useState } from "react";
import * as api from "@/lib/api";
import MatterDocumentUpload from "@/components/matters/MatterDocumentUpload";

type SmokeResult = {
  ok?: boolean;
  pass?: boolean;
  tests?: Array<{
    name?: string;
    pass?: boolean;
    detail?: string;
    sources?: string[];
    query?: string;
  }>;
  vector_count?: number;
  chunk_count?: number;
  retrieval_pass_count?: number;
  ai_confidence?: number;
};

export default function MatterKnowledgePanel({
  matterId,
  onChanged,
}: {
  matterId: string;
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");
  const [smoke, setSmoke] = useState<SmokeResult | null>(null);

  const runSmoke = useCallback(async () => {
    setBusy(true);
    setErr("");
    setSuccess("");
    try {
      const result = await api.runMatterSmokeTest(matterId);
      setSmoke(result as SmokeResult);
      if (result.pass || result.ok) {
        setSuccess(
          `Smoke test passed (${result.retrieval_pass_count ?? 0}/5 queries, ${result.vector_count ?? 0} vectors).`
        );
      } else {
        setErr(
          `Smoke test failed (${result.retrieval_pass_count ?? 0}/5 queries passed). Re-index documents or check matter PDF text.`
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Smoke test failed";
      setErr(msg.includes("Internal Server") ? `${msg} — restart the backend after updating code.` : msg);
      setSmoke(null);
    } finally {
      setBusy(false);
    }
  }, [matterId]);

  return (
    <div className="space-y-4 text-sm max-w-3xl">
      <p className="text-slate-600 m-0">
        Matter-scoped knowledge base — vectors and retrieval apply only to documents linked to this
        case.
      </p>
      <MatterDocumentUpload matterId={matterId} onComplete={() => onChanged?.()} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr("");
            setSuccess("");
            try {
              const r = await api.reindexDocuments(false, matterId);
              setSuccess(r.message || "Re-index started in background.");
              onChanged?.();
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Re-index failed");
            } finally {
              setBusy(false);
            }
          }}
          className="px-3 py-2 border rounded-lg bg-white hover:bg-slate-50 disabled:opacity-50"
        >
          Re-index matter
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void runSmoke()}
          className="px-3 py-2 bg-navy text-white rounded-lg disabled:opacity-50"
        >
          {busy ? "Running smoke test…" : "Run smoke test"}
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
      {smoke && (
        <div className="rounded-xl border bg-white p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`text-xs font-bold uppercase px-2 py-1 rounded-full ${
                smoke.pass || smoke.ok
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-red-100 text-red-800"
              }`}
            >
              {smoke.pass || smoke.ok ? "PASS" : "FAIL"}
            </span>
            <span className="text-xs text-slate-600">
              Vectors: {smoke.vector_count ?? "—"} · Chunks: {smoke.chunk_count ?? "—"} · RAG
              queries passed: {smoke.retrieval_pass_count ?? 0}/5
            </span>
          </div>
          <ul className="space-y-2 m-0 p-0 list-none">
            {(smoke.tests || []).map((t) => (
              <li
                key={String(t.name)}
                className={`text-xs p-2 rounded-lg border ${
                  t.pass ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
                }`}
              >
                <div className="font-semibold text-navy">
                  {t.pass ? "✓" : "✗"} {String(t.name)}
                </div>
                {t.query && <div className="text-slate-500 mt-0.5">Q: {t.query}</div>}
                <div className="text-slate-700 mt-1">{String(t.detail || "").slice(0, 200)}</div>
                {t.sources && t.sources.length > 0 && (
                  <div className="text-slate-400 mt-1">
                    Sources: {t.sources.filter(Boolean).join(", ") || "retrieved chunks"}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
