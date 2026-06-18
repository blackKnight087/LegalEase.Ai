"use client";

import { useState } from "react";

export type RetrievalChunkDebug = {
  index?: number;
  score?: number;
  source?: string;
  section?: string;
  excerpt?: string;
};

export type PipelineStage = {
  stage?: string;
  ok?: boolean;
  elapsed_ms?: number;
  [key: string]: unknown;
};

export type RetrievalDebugPayload = {
  original_query?: string;
  expanded_query?: string;
  retrieval_mode?: string;
  follow_up_detected?: boolean;
  memory_used?: boolean;
  active_topic?: string;
  active_section?: string;
  active_document?: string;
  query_class?: string;
  context_reset?: boolean;
  embedding_model?: string;
  embedding_ready?: boolean;
  chunk_count?: number;
  context_passed_to_llm?: boolean;
  prompt_token_estimate?: number;
  stage_failures?: string[];
  retrieved_chunks?: RetrievalChunkDebug[];
  pipeline_trace?: { stages?: PipelineStage[]; index_stats?: Record<string, unknown> };
  index_stats?: Record<string, unknown>;
  rejections?: Array<{ source?: string; score?: number; reason?: string; excerpt?: string }>;
  retrieval_candidates?: RetrievalChunkDebug[];
  threshold_used?: number;
  top_score?: number;
};

function failClass(failed: boolean) {
  return failed
    ? "text-red-700 bg-red-50 border-red-200"
    : "text-emerald-800 bg-emerald-50 border-emerald-200";
}

export default function RetrievalDebugPanel({
  debug,
  onRunDebug,
  busy,
}: {
  debug: RetrievalDebugPayload | null;
  onRunDebug?: () => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!debug && !onRunDebug) return null;

  const failures = debug?.stage_failures || [];
  const hasFailure = failures.length > 0 || (debug?.chunk_count ?? 0) === 0;
  const stages = debug?.pipeline_trace?.stages || [];
  const indexStats = debug?.index_stats || debug?.pipeline_trace?.index_stats;

  return (
    <div className="mx-2 sm:mx-6 mb-2">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={`text-xs font-medium px-3 py-1.5 rounded-lg border ${
            hasFailure
              ? "border-red-300 bg-red-50 text-red-800"
              : "border-slate-300 bg-white text-slate-700"
          }`}
        >
          {open ? "Hide" : "Debug Retrieval"}
          {hasFailure ? ` (${failures.length || 1} issue${(failures.length || 1) > 1 ? "s" : ""})` : ""}
        </button>
        {onRunDebug && (
          <button
            type="button"
            disabled={busy}
            onClick={onRunDebug}
            className="text-xs px-3 py-1.5 rounded-lg border border-violet-300 bg-violet-50 text-violet-900 disabled:opacity-50"
          >
            Re-run diagnostics
          </button>
        )}
      </div>
      {open && debug && (
        <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs space-y-3 max-h-[480px] overflow-y-auto">
          {indexStats && (
            <div className="rounded-lg border border-slate-200 bg-white p-2 space-y-1">
              <div className="font-semibold text-slate-800">Vector index</div>
              <div>Documents (unlinked): {String(indexStats.unlinked_documents ?? indexStats.documents_indexed ?? "—")}</div>
              <div>Chunks / vectors: {String(indexStats.chunks_indexed ?? indexStats.vectors_indexed ?? "—")}</div>
              {indexStats.mismatch ? (
                <div className="text-red-700 font-medium">Index mismatch — re-index recommended</div>
              ) : null}
            </div>
          )}

          {stages.length > 0 && (
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">Pipeline stages</div>
              {stages.map((st) => (
                <div
                  key={st.stage}
                  className={`rounded border px-2 py-1 ${failClass(!st.ok)}`}
                >
                  <span className="font-medium">{st.stage}</span>
                  {" — "}
                  {st.ok ? "OK" : "FAIL"}
                  {st.elapsed_ms != null ? ` (${st.elapsed_ms}ms)` : ""}
                  {st.chunks_raw != null ? ` · raw=${String(st.chunks_raw)}` : ""}
                  {st.count != null ? ` · count=${String(st.count)}` : ""}
                  {st.rejected != null ? ` · rejected=${String(st.rejected)}` : ""}
                </div>
              ))}
            </div>
          )}

          <Row label="Original query" value={debug.original_query} always />
          <Row label="Expanded query" value={debug.expanded_query} always />
          <Row label="Query class" value={debug.query_class || "—"} always />
          <Row label="Active topic" value={debug.active_topic || "—"} always />
          <Row
            label="Context reset"
            value={debug.context_reset ? "YES (fresh topic)" : "No"}
            always
          />
          {debug.embedding_model ? (
            <Row
              label="Embedding model"
              value={`${debug.embedding_model}${debug.embedding_ready ? " · ready" : ""}`}
              always
            />
          ) : null}
          <Row label="Retrieval mode" value={debug.retrieval_mode || "KB"} always />
          <Row label="Follow-up detected" value={debug.follow_up_detected ? "TRUE" : "FALSE"} always />
          <Row
            label="Memory used"
            value={debug.memory_used ? "Active" : "No"}
            fail={debug.follow_up_detected && !debug.memory_used}
            always
          />
          <Row
            label="Context passed to LLM"
            value={debug.context_passed_to_llm ? "YES" : "NO"}
            fail={!debug.context_passed_to_llm}
            always
          />
          <Row
            label="Chunk count"
            value={String(debug.chunk_count ?? 0)}
            fail={(debug.chunk_count ?? 0) === 0}
            always
          />
          {debug.threshold_used != null ? (
            <Row label="Min accept threshold" value={String(debug.threshold_used)} always />
          ) : null}
          {debug.top_score != null ? (
            <Row
              label="Top retrieval score"
              value={String(debug.top_score)}
              fail={(debug.top_score ?? 0) < (debug.threshold_used ?? 0.5)}
              always
            />
          ) : null}
          {(debug.retrieval_candidates || []).length > 0 && (
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">Retrieval candidates (pre-filter)</div>
              {(debug.retrieval_candidates || []).slice(0, 6).map((ch, i) => (
                <div key={i} className="rounded-lg border border-slate-200 bg-white p-2">
                  <div>Score: {ch.score ?? "—"}</div>
                  <div>Source: {ch.source || "—"}</div>
                  {ch.excerpt ? (
                    <p className="text-slate-600 mt-1 line-clamp-2">{ch.excerpt}</p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
          <Row
            label="Prompt tokens (est.)"
            value={String(debug.prompt_token_estimate ?? 0)}
            fail={(debug.prompt_token_estimate ?? 0) === 0}
            always
          />

          {(debug.retrieved_chunks || []).map((ch) => (
            <div key={ch.index} className="rounded-lg border border-slate-200 bg-white p-2">
              <div className="font-semibold text-slate-800">Retrieved Chunk {ch.index}</div>
              <div>Score: {ch.score ?? "—"}</div>
              <div>Source: {ch.source || "—"}</div>
              {ch.excerpt ? (
                <p className="text-slate-600 mt-1 line-clamp-3">{ch.excerpt}</p>
              ) : null}
            </div>
          ))}

          {(debug.rejections || []).length > 0 && (
            <div className={`rounded-lg border p-2 ${failClass(true)}`}>
              <div className="font-semibold">Rejected chunks</div>
              {(debug.rejections || []).map((r, i) => (
                <div key={i} className="mt-1 border-t border-red-100 pt-1">
                  <div>Source: {r.source || "—"} · Score: {r.score ?? "—"}</div>
                  <div>Reason: {r.reason}</div>
                </div>
              ))}
            </div>
          )}

          {failures.length > 0 && (
            <div className={`rounded-lg border p-2 ${failClass(true)}`}>
              <div className="font-semibold">Stage failures</div>
              <ul className="list-disc pl-4 mt-1">
                {failures.map((f) => (
                  <li key={f}>{f.replace(/_/g, " ")}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  fail,
  always,
}: {
  label: string;
  value?: string;
  fail?: boolean;
  always?: boolean;
}) {
  if (!always && !value) return null;
  return (
    <div className={`rounded-lg border px-2 py-1.5 ${failClass(!!fail)}`}>
      <span className="font-semibold">{label}: </span>
      <span className="break-words">{value ?? "—"}</span>
    </div>
  );
}
