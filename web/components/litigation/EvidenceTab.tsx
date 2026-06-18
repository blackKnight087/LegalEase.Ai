"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

export default function EvidenceTab() {
  const [data, setData] = useState<api.EvidenceDeskResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [matterFilter, setMatterFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const load = useCallback(async () => {
    setErr("");
    setLoading(true);
    try {
      const d = await api.fetchEvidenceDesk();
      setData(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load evidence desk");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const matterOptions = useMemo(() => {
    const ids = new Map<string, string>();
    for (const c of data?.contradictions || []) {
      if (c.matter_id) ids.set(c.matter_id, c.matter_name);
    }
    for (const b of data?.blind_spots || []) {
      if (b.matter_id) ids.set(b.matter_id, b.matter_name);
    }
    return [...ids.entries()].map(([id, name]) => ({ id, name }));
  }, [data]);

  const typeOptions = useMemo(() => {
    const types = new Set<string>();
    for (const c of data?.contradictions || []) {
      if (c.contradiction_type) types.add(c.contradiction_type);
    }
    return [...types].sort();
  }, [data]);

  const filteredContradictions = useMemo(() => {
    let list = data?.contradictions || [];
    if (matterFilter) list = list.filter((c) => c.matter_id === matterFilter);
    if (typeFilter) list = list.filter((c) => c.contradiction_type === typeFilter);
    return list;
  }, [data, matterFilter, typeFilter]);

  const scanAll = async (full = false) => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = full ? await api.scanEvidenceDeskAll() : await api.scanEvidenceDesk(25);
      const scanned = r.scanned?.length ?? 0;
      const cap = r.scan_cap ?? 8;
      const total = r.candidates_total ?? scanned;
      setMsg(
        `Scanned ${scanned} of ${total} matter(s) with documents (cap: ${cap}).` +
          (r.errors?.length ? ` ${r.errors.length} error(s).` : "")
      );
      if (r.desk) setData(r.desk);
      else await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  };

  const summary = data?.summary;

  return (
    <div className="space-y-6">
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {err}
        </p>
      )}
      {msg && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          {msg}
        </p>
      )}

      <div className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-4 flex flex-wrap gap-3 items-center">
        <button
          type="button"
          disabled={busy || loading}
          className="le-interactive px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          onClick={() => void scanAll(true)}
        >
          {busy ? "Scanning…" : "Scan all matters"}
        </button>
        <button
          type="button"
          disabled={busy || loading}
          className="le-interactive px-4 py-2 border border-slate-300 text-navy rounded-lg text-sm disabled:opacity-50"
          onClick={() => void scanAll(false)}
        >
          Quick scan (25)
        </button>
        <button
          type="button"
          disabled={busy || loading}
          className="le-interactive px-4 py-2 border border-blue-300 text-blue-800 rounded-lg text-sm disabled:opacity-50"
          onClick={() => void api.downloadEvidenceDeskReport()}
        >
          Export report (.md)
        </button>
        <button
          type="button"
          disabled={busy || loading}
          className="le-interactive px-3 py-2 border rounded-lg text-sm disabled:opacity-50"
          onClick={() => void load()}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        <p className="text-xs text-slate-500 m-0 w-full sm:w-auto">
          Full firm scan + export. Verify with counsel before trial use.
        </p>
      </div>

      {(matterOptions.length > 0 || typeOptions.length > 0) && (
        <div className="flex flex-wrap gap-3 items-end">
          {matterOptions.length > 0 && (
            <label className="text-xs text-slate-600">
              Matter
              <select
                className="block mt-1 border rounded-lg px-2 py-1.5 text-sm min-w-[160px]"
                value={matterFilter}
                onChange={(e) => setMatterFilter(e.target.value)}
              >
                <option value="">All matters</option>
                {matterOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {typeOptions.length > 0 && (
            <label className="text-xs text-slate-600">
              Type
              <select
                className="block mt-1 border rounded-lg px-2 py-1.5 text-sm min-w-[140px]"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
              >
                <option value="">All types</option>
                {typeOptions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {summary && (
        <div className="grid sm:grid-cols-4 gap-3">
          {[
            ["Matters", summary.total_matters],
            ["With contradictions", summary.matters_with_contradictions],
            ["Total pairs", summary.contradiction_count],
            ["Need scan", summary.blind_spot_count],
          ].map(([label, val]) => (
            <div key={String(label)} className="rounded-xl border bg-white p-4 shadow-sm">
              <p className="text-xs text-slate-500 m-0">{label}</p>
              <p className="text-2xl font-bold text-navy m-0 mt-1">{val}</p>
            </div>
          ))}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-navy m-0">Contradictions</h2>
        {loading && <p className="text-sm text-slate-500 m-0">Loading…</p>}
        {!loading && !filteredContradictions.length && (
          <p className="text-sm text-slate-500">
            No contradictions yet. Upload witness statements to matters and run scan, or open a
            matter&apos;s{" "}
            <Link href="/matters" className="text-blue-600">
              Contradictions
            </Link>{" "}
            tab.
          </p>
        )}
        {filteredContradictions.map((c) => (
          <div
            key={c.contradiction_id || `${c.matter_id}-${c.topic}`}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="flex flex-wrap justify-between gap-2 mb-2">
              <Link
                href={`/matters/${c.matter_id}/contradictions`}
                className="text-sm font-semibold text-navy hover:underline"
              >
                {c.matter_name}
              </Link>
              <span className="text-[0.65rem] text-slate-500">
                {c.contradiction_type} · conf {(c.confidence ?? 0).toFixed(2)}
              </span>
            </div>
            <p className="text-sm font-medium text-slate-800 m-0">{c.topic}</p>
            <p className="text-xs text-slate-600 mt-2 m-0">
              <span className="font-semibold">A:</span> {c.statement_a}
            </p>
            <p className="text-xs text-slate-600 mt-1 m-0">
              <span className="font-semibold">B:</span> {c.statement_b}
            </p>
          </div>
        ))}
      </section>

      {(data?.blind_spots?.length ?? 0) > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-amber-800 m-0">Blind spots</h2>
          <p className="text-xs text-slate-500 m-0">
            Matters with documents but no contradiction scan yet.
          </p>
          <ul className="m-0 p-0 list-none space-y-2">
            {data?.blind_spots?.map((b) => (
              <li
                key={b.matter_id}
                className="flex justify-between items-center rounded-lg border px-3 py-2 bg-amber-50/50"
              >
                <Link
                  href={`/matters/${b.matter_id}/contradictions`}
                  className="text-sm text-navy font-medium hover:underline"
                >
                  {b.matter_name}
                </Link>
                <span className="text-xs text-slate-500">{b.document_count} docs</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
