"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import PageShell from "@/components/ui/PageShell";
import Alert from "@/components/ui/Alert";
import * as api from "@/lib/api";

type MappingRecord = Record<string, unknown>;
type Tab = "search" | "compare" | "bulk" | "document" | "matter";

const QUICK = ["302", "304A", "420", "376", "498A"];

export default function IpcBnsIntelEngine() {
  const [tab, setTab] = useState<Tab>("search");
  const [direction, setDirection] = useState<"forward" | "reverse">("forward");
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<MappingRecord | null>(null);
  const [compare, setCompare] = useState<MappingRecord | null>(null);
  const [searchHits, setSearchHits] = useState<MappingRecord[]>([]);
  const [bulkIn, setBulkIn] = useState("302, 420, 376");
  const [bulkOut, setBulkOut] = useState<MappingRecord | null>(null);
  const [docResult, setDocResult] = useState<MappingRecord | null>(null);
  const [caseName, setCaseName] = useState("");
  const [matterId, setMatterId] = useState("");
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterReport, setMatterReport] = useState<MappingRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.legalConversionMeta().then(setMeta).catch(() => api.ipcBnsV3Meta().then(setMeta).catch(() => {}));
    api.listMatters().then((d) => setMatters(d.matters || [])).catch(() => {});
  }, []);

  const loadDetail = useCallback(
    async (section: string, dir: "forward" | "reverse" = direction) => {
      setBusy(true);
      setErr("");
      try {
        const r = await api.legalConversionConvert(section, dir, matterId);
        setDetail(r);
        setDirection(dir);
        if (r.found && dir === "forward") {
          const c = await api.ipcBnsV3Compare(String(r.old_section || section));
          setCompare(c);
        } else {
          setCompare(null);
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Lookup failed");
        setDetail(null);
      } finally {
        setBusy(false);
      }
    },
    [matterId, direction]
  );

  const runSearch = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.legalConversionSearch(query.trim());
      const hits = (r.results as MappingRecord[]) || [];
      setSearchHits(hits);
      if (hits.length === 1) {
        setDetail(hits[0]);
        setCompare(null);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  const runBulk = async () => {
    const sections = bulkIn
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy(true);
    setErr("");
    try {
      setBulkOut(await api.ipcBnsV3Bulk(sections, matterId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Bulk failed");
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (file: File) => {
    setBusy(true);
    setErr("");
    try {
      setDocResult(await api.ipcBnsV3UploadDocument(file, caseName, matterId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const exportReport = async (fmt: "pdf" | "docx") => {
    const conversions =
      (bulkOut?.results as MappingRecord[]) ||
      (docResult?.results as MappingRecord[]) ||
      (detail ? [detail] : []);
    if (!conversions.length) {
      setErr("No conversions to export");
      return;
    }
    setBusy(true);
    try {
      const blob = await api.ipcBnsV3ExportReport({
        case_name: caseName || "IPC-BNS Migration",
        conversions,
        format: fmt,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ipc-bns-report.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "search", label: "Search" },
    { id: "compare", label: "Change analysis" },
    { id: "bulk", label: "Bulk convert" },
    { id: "document", label: "Document upload" },
    { id: "matter", label: "Matter migration" },
  ];

  const pairCfg = {
    forward: String(meta?.forward_label ?? meta?.source_code ?? "IPC"),
    reverse: String(meta?.reverse_label ?? meta?.target_code ?? "BNS"),
  };

  return (
    <div className="flex flex-col h-full min-h-0 drafting-studio animate-fade-in">
      <PageHeader
        eyebrow="Legal Tools"
        title="IPC ↔ BNS Intelligence"
        subtitle="Official IPC–BNS mapping dataset only — no AI guessing"
      >
        <Link href="/tools" className="text-sm px-3 py-2 border rounded-xl bg-white no-underline text-slate-700">
          All tools
        </Link>
      </PageHeader>

      <PageShell maxWidth="7xl" className="space-y-5 pb-10">
        <div className="le-card rounded-2xl p-4 flex flex-wrap gap-4 items-center justify-between">
          <div className="text-xs text-slate-600 space-y-1">
            <p className="m-0">
              <span className="font-semibold text-slate-800">Dataset {String(meta?.dataset_version || "official")}</span>
              {" · "}
              {Number(meta?.record_count) || "—"} official IPC↔BNS mappings
            </p>
            <p className="m-0">Source: ipc_bns_official.json</p>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
            No AI mapping
          </span>
        </div>

        {err && <Alert variant="error">{err}</Alert>}

        <div className="drafting-view-tabs w-full sm:w-auto">
          {tabs.map((t) => (
            <button key={t.id} type="button" className={tab === t.id ? "is-active" : ""} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "search" && (
          <div className="grid lg:grid-cols-3 gap-5">
            <div className="lg:col-span-1 space-y-4">
              <section className="le-card rounded-2xl p-5">
                <h2 className="le-section-title m-0 mb-3">Section converter</h2>
                <div className="flex gap-2 mb-3">
                  <button
                    type="button"
                    className={`flex-1 text-xs py-2 rounded-lg border font-semibold ${direction === "forward" ? "bg-slate-900 text-white" : ""}`}
                    onClick={() => setDirection("forward")}
                  >
                    {pairCfg.forward} → {pairCfg.reverse}
                  </button>
                  <button
                    type="button"
                    className={`flex-1 text-xs py-2 rounded-lg border font-semibold ${direction === "reverse" ? "bg-slate-900 text-white" : ""}`}
                    onClick={() => setDirection("reverse")}
                  >
                    {pairCfg.reverse} → {pairCfg.forward}
                  </button>
                </div>
                <input
                  className="le-input mb-3"
                  placeholder={`${direction === "forward" ? pairCfg.forward : pairCfg.reverse} section number…`}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (query.trim() ? loadDetail(query.trim(), direction) : runSearch())}
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => (query.trim() ? loadDetail(query.trim(), direction) : runSearch())}
                  className="w-full py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold disabled:opacity-50"
                >
                  Convert section
                </button>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {QUICK.map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="text-xs px-2 py-1 rounded-lg border bg-slate-50 hover:bg-white"
                      onClick={() => {
                        setQuery(q);
                        loadDetail(q, direction);
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </section>
              {searchHits.length > 1 && (
                <ul className="le-card rounded-2xl p-3 space-y-1 max-h-64 overflow-y-auto le-scroll">
                  {searchHits.map((h, i) => (
                    <li key={i}>
                      <button
                        type="button"
                        className="w-full text-left text-sm px-2 py-2 rounded-lg hover:bg-slate-50"
                        onClick={() => {
                          setDetail(h);
                          loadDetail(String(h.old_section || h.ipc_key || ""), "forward");
                        }}
                      >
                        {String(h.old_section_label || h.ipc_section)} → {String(h.new_section_label || h.bns_section || "—")}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="lg:col-span-2">
              <SectionDetailPanel
                detail={detail}
                compare={compare}
                pairCfg={pairCfg}
                onReverse={(s) => loadDetail(s, direction === "forward" ? "reverse" : "forward")}
              />
            </div>
          </div>
        )}

        {tab === "compare" && (
          <div className="grid lg:grid-cols-3 gap-5">
            <section className="le-card rounded-2xl p-5 lg:col-span-1">
              <h2 className="le-section-title m-0 mb-3">IPC section</h2>
              <input
                className="le-input mb-3"
                placeholder="e.g. 420"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => loadDetail(query)}
                className="w-full py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold"
              >
                Analyze changes
              </button>
            </section>
            <div className="lg:col-span-2">
              <ChangeAnalysisPanel compare={compare} detail={detail} />
            </div>
          </div>
        )}

        {tab === "bulk" && (
          <div className="space-y-4">
            <section className="le-card rounded-2xl p-5 max-w-2xl">
              <h2 className="le-section-title m-0 mb-2">Bulk IPC conversion</h2>
              <textarea
                className="le-input le-textarea w-full font-mono text-sm"
                rows={4}
                value={bulkIn}
                onChange={(e) => setBulkIn(e.target.value)}
                placeholder="302, 420, 376 — comma or newline separated"
              />
              <button
                type="button"
                disabled={busy}
                onClick={runBulk}
                className="mt-3 px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold"
              >
                Convert all
              </button>
            </section>
            <ConversionTable data={bulkOut} />
            <ExportBar caseName={caseName} setCaseName={setCaseName} onExport={exportReport} busy={busy} />
          </div>
        )}

        {tab === "document" && (
          <div className="space-y-4">
            <section className="le-card rounded-2xl p-5">
              <h2 className="le-section-title m-0 mb-2">FIR / charge sheet / filing</h2>
              <p className="le-section-desc m-0 mb-4">PDF, DOCX, or TXT — sections extracted by pattern (no AI)</p>
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                className="text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onFile(f);
                }}
              />
            </section>
            <ConversionTable data={docResult} />
            <ExportBar caseName={caseName} setCaseName={setCaseName} onExport={exportReport} busy={busy} />
          </div>
        )}

        {tab === "matter" && (
          <div className="space-y-4 max-w-3xl">
            <section className="le-card rounded-2xl p-5">
              <h2 className="le-section-title m-0 mb-3">Matter migration impact</h2>
              <select
                className="le-input w-full mb-3"
                value={matterId}
                onChange={(e) => setMatterId(e.target.value)}
              >
                <option value="">Select matter</option>
                {matters.map((m) => (
                  <option key={m.matter_id} value={m.matter_id}>
                    {m.matter_name || m.client_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={busy || !matterId}
                onClick={async () => {
                  setBusy(true);
                  try {
                    setMatterReport(await api.ipcBnsV3MatterMigration(matterId));
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : "Failed");
                  } finally {
                    setBusy(false);
                  }
                }}
                className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold disabled:opacity-50"
              >
                Generate migration memo
              </button>
            </section>
            {matterReport && (
              <pre className="le-card rounded-2xl p-5 text-xs whitespace-pre-wrap text-slate-700 max-h-96 overflow-y-auto le-scroll">
                {String(matterReport.migration_memo)}
              </pre>
            )}
          </div>
        )}
      </PageShell>
    </div>
  );
}

function SectionDetailPanel({
  detail,
  compare,
  pairCfg,
  onReverse,
}: {
  detail: MappingRecord | null;
  compare: MappingRecord | null;
  pairCfg: { forward: string; reverse: string };
  onReverse: (s: string) => void;
}) {
  if (!detail) {
    return (
      <div className="le-empty le-card rounded-2xl min-h-[320px]">
        <p className="font-serif text-lg text-slate-800 m-0">Section converter</p>
        <p className="text-sm text-slate-500 mt-2 m-0">
          Enter a {pairCfg.forward} or {pairCfg.reverse} section for an official mapping lookup.
        </p>
      </div>
    );
  }
  const found = Boolean(detail.found);
  const oldLabel = String(detail.old_section_label || detail.ipc_section || "");
  const newLabel = String(detail.new_section_label || detail.bns_section || "—");
  const oldTitle = String(detail.old_title || detail.offence_title || "");
  const newTitle = String(detail.new_title || detail.short_description || "");
  const alts = (detail.alternate_mappings || detail.equivalents) as MappingRecord[] | undefined;

  return (
    <article className="le-card rounded-2xl overflow-hidden">
      <div className={`px-6 py-4 border-b ${found ? "bg-slate-900 text-white" : "bg-amber-50 text-amber-950"}`}>
        <p className="text-[10px] uppercase tracking-widest opacity-80 m-0">
          {found ? "Official mapping" : String(detail.status || "Not in dataset")}
        </p>
        <h2 className="font-serif text-2xl font-bold m-0 mt-1">{oldTitle || oldLabel}</h2>
        {!found && <p className="text-sm m-0 mt-2">{String(detail.message)}</p>}
      </div>
      {found && (
        <div className="p-6 grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-xs font-bold uppercase text-slate-500 m-0 mb-2">IPC</h3>
            <p className="text-xl font-bold text-slate-900 m-0">{oldLabel}</p>
            <p className="text-sm text-slate-600 mt-2 m-0">Title: {oldTitle}</p>
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase text-slate-500 m-0 mb-2">BNS</h3>
            <p className="text-xl font-bold text-slate-900 m-0">{newLabel}</p>
            <p className="text-sm text-slate-600 mt-2 m-0">Title: {newTitle}</p>
            {detail.new_section != null && String(detail.new_section) !== "" ? (
              <button
                type="button"
                className="text-xs text-blue-700 mt-2 underline"
                onClick={() => onReverse(String(detail.new_section || detail.bns_key || ""))}
              >
                Reverse lookup
              </button>
            ) : null}
          </div>
          <dl className="md:col-span-2 grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            {[
              ["Status", detail.status_label || "Active"],
              ["Mapping type", detail.mapping_type || detail.mapping_status],
              ["Punishment", detail.punishment],
              ["Cognizable", detail.cognizable],
              ["Bailable", detail.bailable],
              ["Court", detail.court_type || detail.court_jurisdiction],
            ]
              .filter(([, v]) => v != null && String(v) !== "")
              .map(([k, v]) => (
                <div key={String(k)} className="rounded-xl border p-3 bg-slate-50/50">
                  <dt className="text-[10px] font-bold uppercase text-slate-500">{String(k)}</dt>
                  <dd className="m-0 mt-1 text-slate-800">{String(v)}</dd>
                </div>
              ))}
          </dl>
          {detail.notes ? (
            <div className="md:col-span-2 rounded-xl border border-amber-200 bg-amber-50/50 p-4 text-sm text-amber-950">
              <p className="text-[10px] font-bold uppercase m-0 mb-1">Notes</p>
              <p className="m-0">{String(detail.notes)}</p>
            </div>
          ) : null}
          {alts && alts.length > 0 && (
            <div className="md:col-span-2 text-sm text-slate-600">
              <p className="font-semibold text-slate-800 m-0 mb-1">Additional mappings</p>
              <ul className="m-0 pl-4">
                {alts.map((a, i) => (
                  <li key={i}>
                    {String(a.section)} — {String(a.title)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <SourceBlock detail={detail} />
        </div>
      )}
      {!found && (
        <div className="p-6">
          <SourceBlock detail={detail} />
        </div>
      )}
    </article>
  );
}

function ChangeAnalysisPanel({
  compare,
  detail,
}: {
  compare: MappingRecord | null;
  detail: MappingRecord | null;
}) {
  if (!compare?.comparison) {
    return (
      <div className="le-empty le-card rounded-2xl min-h-[280px]">
        <p className="m-0 text-slate-600">Enter an IPC section to see side-by-side change analysis.</p>
      </div>
    );
  }
  const c = compare.comparison as MappingRecord;
  const rows = [
    ["What changed", c.what_changed],
    ["What stayed same", c.what_same],
    ["Punishment", c.punishment_changed],
    ["Procedure", c.procedure_changed],
    ["New definitions", c.new_definitions],
    ["Removed definitions", c.removed_definitions],
    ["Expanded scope", c.scope_expanded],
    ["Reduced scope", c.scope_reduced],
  ];
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="le-card rounded-2xl p-5 border-l-4 border-slate-400">
        <h3 className="le-section-title m-0 text-slate-500">IPC</h3>
        <p className="text-lg font-bold m-0 mt-2">{String(detail?.ipc_section)}</p>
        <p className="text-sm text-slate-600 mt-2 m-0">{String(detail?.short_description)}</p>
      </div>
      <div className="le-card rounded-2xl p-5 border-l-4 border-blue-600">
        <h3 className="le-section-title m-0 text-blue-800">BNS</h3>
        <p className="text-lg font-bold m-0 mt-2">{String(detail?.bns_section)}</p>
        <p className="text-sm text-slate-600 mt-2 m-0">{String(detail?.change_notes)}</p>
      </div>
      <div className="md:col-span-2 le-card rounded-2xl p-5">
        <h3 className="le-section-title m-0 mb-4">Legislative change summary</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          {rows.map(([label, val]) =>
            val ? (
              <div key={String(label)} className="rounded-xl bg-slate-50 border p-3">
                <p className="text-[10px] font-bold uppercase text-slate-500 m-0">{String(label)}</p>
                <p className="text-sm text-slate-800 m-0 mt-1">{String(val)}</p>
              </div>
            ) : null
          )}
        </div>
        <div className="mt-4">
          <SourceBlock detail={detail || {}} />
        </div>
      </div>
    </div>
  );
}

function SourceBlock({ detail }: { detail: MappingRecord }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-xs text-slate-600 space-y-1">
      <p className="m-0 font-semibold text-slate-800">Source validation</p>
      <p className="m-0">Source: {String(detail.source || "Official mapping dataset")}</p>
      <p className="m-0">File: {String(detail.source_file || detail.official_source || "—")}</p>
      <p className="m-0">Dataset version: {String(detail.dataset_version)} · Updated: {String(detail.last_updated)}</p>
      <p className="m-0 text-emerald-800">Confidence: {detail.found ? "100% (database match)" : "0% — not in dataset"}</p>
    </div>
  );
}

function ConversionTable({ data }: { data: MappingRecord | null }) {
  const rows = (data?.results as MappingRecord[]) || [];
  if (!rows.length) return null;
  return (
    <div className="le-card rounded-2xl overflow-hidden">
      <div className="px-5 py-3 border-b flex justify-between text-sm">
        <span className="font-semibold text-slate-800">Conversion report</span>
        <span className="text-slate-500">
          {Number(data?.mapped_count)}/{Number(data?.total)} mapped · dataset v{String(data?.dataset_version)}
        </span>
      </div>
      <div className="overflow-x-auto le-scroll">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="p-3">IPC</th>
              <th className="p-3">BNS</th>
              <th className="p-3">Offence</th>
              <th className="p-3">Confidence</th>
              <th className="p-3">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t">
                <td className="p-3 font-medium">{String(r.ipc_section || r.ipc_key)}</td>
                <td className="p-3">{r.found ? String(r.bns_section) : "—"}</td>
                <td className="p-3 text-slate-600">{String(r.offence_title || r.short_description || "—")}</td>
                <td className="p-3">{r.found ? "100%" : "0%"}</td>
                <td className="p-3 text-slate-600 text-xs max-w-xs">
                  {r.found ? String(r.change_notes) : String(r.message)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExportBar({
  caseName,
  setCaseName,
  onExport,
  busy,
}: {
  caseName: string;
  setCaseName: (v: string) => void;
  onExport: (fmt: "pdf" | "docx") => void;
  busy: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-3 items-end">
      <div className="flex-1 min-w-[200px]">
        <label className="text-xs text-slate-500 font-medium">Case name (report header)</label>
        <input className="le-input w-full mt-1" value={caseName} onChange={(e) => setCaseName(e.target.value)} />
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={() => onExport("pdf")}
        className="px-4 py-2.5 rounded-xl border font-semibold text-sm"
      >
        Export PDF
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => onExport("docx")}
        className="px-4 py-2.5 rounded-xl border font-semibold text-sm"
      >
        Export Word
      </button>
    </div>
  );
}
