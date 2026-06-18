"use client";



import type { KbSmokeTestResult, fetchKbHealth } from "@/lib/api";



type KbHealth = Awaited<ReturnType<typeof fetchKbHealth>>;



export default function KbHealthPanel({

  kb,

  loading,

  onAutoReindex,

  onSmokeTest,

  busy,

  smokeResult,

}: {

  kb: KbHealth;

  loading?: boolean;

  onAutoReindex?: () => void;

  onSmokeTest?: () => void;

  busy?: boolean;

  smokeResult?: KbSmokeTestResult | null;

}) {

  const embLoading = Boolean(

    (kb.embeddings as { loading?: boolean } | undefined)?.loading

  );

  const embOk = kb.embeddings_ok ?? kb.embeddings?.ready ?? false;

  const vectors = kb.faiss_chunks ?? kb.index_vectors ?? 0;

  const totalVectors = kb.faiss_chunks_total ?? vectors;

  const healthy =
    !loading &&
    (kb.healthy ??
      ((embOk || embLoading) && (kb.documents === 0 || totalVectors > 0)));

  const issues = kb.issues ?? [];



  return (

    <div

      className={`mb-4 p-4 rounded-xl border text-sm max-w-3xl ${

        healthy

          ? "bg-emerald-50 border-emerald-200"

          : embLoading

            ? "bg-sky-50 border-sky-200"

            : "bg-amber-50 border-amber-300"

      }`}

    >

      <div className="flex flex-wrap items-start justify-between gap-3">

        <div>

          <p className="font-semibold text-navy">

            {loading

              ? "⏳ Loading KB status…"

              : healthy

                ? "✅ KB Ready"

                : embLoading

                  ? "⏳ KB loading embeddings…"

                  : "⚠️ KB Needs Attention"}

          </p>

          <p className="text-slate-600 mt-1">

            Scope: <strong>{kb.index_scope_label || kb.index_scope || "unlinked"}</strong>

            {" · "}

            {kb.documents ?? 0} docs · {totalVectors} FAISS vectors

            {kb.chunks != null ? ` · ${kb.chunks} DB chunks` : ""}

          </p>

        </div>

        <div className="flex flex-wrap gap-2 shrink-0">

          {onSmokeTest && vectors > 0 && (

            <button

              type="button"

              disabled={busy}

              onClick={onSmokeTest}

              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-300 bg-white text-navy hover:bg-slate-50 disabled:opacity-50"

            >

              {busy ? "Running smoke test…" : "Run smoke test"}

            </button>

          )}

          {!healthy && onAutoReindex && (

            <button

              type="button"

              disabled={busy}

              onClick={onAutoReindex}

              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-navy text-white hover:bg-navy/90 disabled:opacity-50"

            >

              Auto-fix index

            </button>

          )}

        </div>

      </div>



      {smokeResult && (

        <div

          className={`mt-3 p-3 rounded-lg border text-xs ${

            smokeResult.skipped

              ? "bg-amber-50 border-amber-200"

              : smokeResult.ok

                ? "bg-white border-emerald-200"

                : "bg-red-50 border-red-200"

          }`}

        >

          <p className="font-semibold text-navy mb-2">

            {smokeResult.skipped

              ? "⏸ Smoke test deferred"

              : smokeResult.ok

                ? `✅ KB PASS — ${smokeResult.passed ?? 0}/${(smokeResult.queries?.length ?? 0)} queries`

                : `❌ KB FAIL — ${smokeResult.failed ?? 0} failed, ${smokeResult.passed ?? 0} passed`}

            {smokeResult.total_latency_ms != null && (

              <span className="font-normal text-slate-500">

                {" "}

                · {smokeResult.total_latency_ms}ms

              </span>

            )}

          </p>

          {smokeResult.skipped && (

            <p className="text-amber-800 mb-2">

              {smokeResult.reason === "scheduler_busy" || smokeResult.reason === "heavy_lock_busy"

                ? "System busy with chat or training — try again in a moment."

                : String(smokeResult.reason || "Deferred")}

            </p>

          )}

          {smokeResult.error && (

            <p className="text-red-700 mb-2">{smokeResult.error}</p>

          )}

          <div className="grid sm:grid-cols-3 gap-2 mb-2">

            <div className="p-2 rounded bg-slate-50 border border-slate-100">

              <span className="font-medium">Vectors</span>

              <p>{smokeResult.faiss_vectors ?? "—"}</p>

            </div>

            <div className="p-2 rounded bg-slate-50 border border-slate-100">

              <span className="font-medium">Training</span>

              <p>

                {smokeResult.training_pass === true

                  ? "OK"

                  : smokeResult.training_pass === false

                    ? "Error"

                    : "—"}

              </p>

            </div>

            <div className="p-2 rounded bg-slate-50 border border-slate-100">

              <span className="font-medium">RAM</span>

              <p>

                {smokeResult.scheduler?.memory?.percent != null

                  ? `${Math.round(smokeResult.scheduler.memory.percent)}%`

                  : "—"}

              </p>

            </div>

          </div>

          {smokeResult.queries && smokeResult.queries.length > 0 && (

            <ul className="space-y-1 max-h-48 overflow-y-auto le-scroll">

              {smokeResult.queries.map((q) => (

                <li

                  key={q.id}

                  className={`flex justify-between gap-2 py-1 border-b border-slate-100 last:border-0 ${

                    q.status === "pass"

                      ? "text-emerald-800"

                      : q.status === "error"

                        ? "text-red-800"

                        : "text-red-700"

                  }`}

                >

                  <span className="truncate" title={q.query}>

                    {q.status === "pass" ? "✓" : "✗"} {q.query}

                  </span>

                  <span className="shrink-0 text-slate-500">

                    {q.chunk_count != null ? `${q.chunk_count} chunks` : ""}

                    {q.latency_ms != null ? ` · ${q.latency_ms}ms` : ""}

                  </span>

                </li>

              ))}

            </ul>

          )}

        </div>

      )}



      <div className="mt-3 grid sm:grid-cols-3 gap-2 text-xs">

        <div className={`p-2 rounded-lg border ${embOk ? "bg-white border-emerald-200" : "bg-red-50 border-red-200"}`}>

          <span className="font-semibold">Embeddings</span>

          <p className={embOk ? "text-emerald-700" : embLoading ? "text-amber-700" : "text-red-700"}>

            {embOk ? "Loaded" : embLoading ? "Loading…" : "Offline"}

          </p>

          {kb.embeddings?.model && (

            <p className="text-slate-500 truncate" title={kb.embeddings.model}>

              {kb.embeddings.model.split(/[/\\]/).pop()}

            </p>

          )}

          {!embOk && kb.embeddings?.error && (

            <p className="text-red-600 mt-1">{kb.embeddings.error.slice(0, 120)}</p>

          )}

        </div>

        <div className={`p-2 rounded-lg border ${vectors > 0 ? "bg-white border-emerald-200" : "bg-red-50 border-red-200"}`}>

          <span className="font-semibold">Active index</span>

          <p className={vectors > 0 ? "text-emerald-700" : "text-red-700"}>

            {vectors} vectors

          </p>

          <p className="text-slate-500">{kb.index_exists ? "On disk" : "Missing"}</p>

        </div>

        <div className="p-2 rounded-lg border bg-white border-slate-200">

          <span className="font-semibold">Query ready</span>

          <p className={kb.ready_for_kb_query ? "text-emerald-700" : "text-amber-700"}>

            {kb.ready_for_kb_query ? "Yes" : "Not yet"}

          </p>

        </div>

      </div>



      {issues.length > 0 && (

        <ul className="mt-3 space-y-2 text-xs">

          {issues.map((issue, i) => (

            <li

              key={i}

              className={`p-2 rounded-lg ${

                issue.severity === "error"

                  ? "bg-red-100 text-red-800"

                  : "bg-amber-100 text-amber-900"

              }`}

            >

              <strong>{issue.code || issue.severity}:</strong> {issue.message}

              {issue.fix && <span className="block mt-1 opacity-90">Fix: {issue.fix}</span>}

            </li>

          ))}

        </ul>

      )}



      {kb.recommended_actions && kb.recommended_actions.length > 0 && (

        <p className="mt-2 text-xs text-slate-600">

          <strong>Recommended:</strong> {kb.recommended_actions.join(" · ")}

        </p>

      )}

    </div>

  );

}


