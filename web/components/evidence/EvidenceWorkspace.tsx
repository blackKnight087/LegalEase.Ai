"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import ThumbsFeedback from "@/components/ui/ThumbsFeedback";
import * as api from "@/lib/api";

const ACCEPT =
  ".pdf,.docx,.doc,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.xlsx,.xls,.csv,.txt,.eml,.msg,.zip";

type Tab = "upload" | "repository" | "timeline" | "contradiction" | "statutes";

function strengthColor(pct: number) {
  if (pct >= 80) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (pct >= 60) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-slate-600 bg-slate-50 border-slate-200";
}

function EntityChip({ label, items }: { label: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 12).map((x) => (
          <span key={x} className="px-2 py-0.5 rounded-full bg-navy/5 text-navy text-xs border">
            {x}
          </span>
        ))}
      </div>
    </div>
  );
}

function AnalysisPanel({ analysis }: { analysis: api.EvidenceAnalysis | null }) {
  if (!analysis) return null;
  const strength = analysis.evidence_strength;
  const pct = strength?.percent ?? Math.round((strength?.score ?? 0) * 100);
  return (
    <div className="space-y-4">
      <div className={`rounded-xl border p-4 ${strengthColor(pct)}`}>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-medium opacity-80">Evidence Strength</p>
            <p className="text-2xl font-bold">{pct}%</p>
            <p className="text-sm font-semibold">{strength?.label || "Relevance"}</p>
          </div>
          <div className="text-right text-xs">
            <p>{analysis.classification?.primary_category?.replace(/_/g, " ")}</p>
            {(strength?.tags || []).slice(0, 3).map((t) => (
              <p key={t} className="opacity-80">
                {t.replace(/_/g, " ")}
              </p>
            ))}
          </div>
        </div>
        {strength?.rationale && <p className="text-xs mt-2 opacity-90">{strength.rationale}</p>}
      </div>

      {analysis.privilege?.privileged && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
          <p className="font-semibold text-amber-900">Privilege Review Required</p>
          <p className="text-xs text-amber-800 mt-1">{analysis.privilege.recommendation}</p>
          {(analysis.privilege.flags || []).map((f) => (
            <p key={f.type} className="text-xs mt-1">
              • {f.description}
            </p>
          ))}
        </div>
      )}

      {(analysis.risks?.length ?? 0) > 0 && (
        <div className="rounded-xl border p-3">
          <p className="text-xs font-semibold text-navy mb-2">Risk Detection</p>
          <ul className="space-y-1 text-xs">
            {analysis.risks!.map((r) => (
              <li key={r.code} className="flex justify-between gap-2">
                <span>{r.description}</span>
                <span className="text-slate-500">{Math.round((r.confidence ?? 0) * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-xl border p-3 grid sm:grid-cols-2 gap-3">
        <EntityChip label="People" items={analysis.entities?.people} />
        <EntityChip label="Organizations" items={analysis.entities?.organizations} />
        <EntityChip label="Locations" items={analysis.entities?.locations} />
        <EntityChip label="Dates" items={analysis.entities?.dates} />
        <EntityChip label="Emails" items={analysis.entities?.emails} />
        <EntityChip label="Phones" items={analysis.entities?.phones} />
        <EntityChip label="Case numbers" items={analysis.entities?.case_numbers} />
        <EntityChip label="Bank / IFSC" items={[...(analysis.entities?.bank_accounts || []), ...(analysis.entities?.ifsc_codes || [])]} />
      </div>

      {(analysis.statutes?.length ?? 0) > 0 && (
        <div className="rounded-xl border p-3">
          <p className="text-xs font-semibold text-navy mb-2">Potential Statutes (BNS / BNSS)</p>
          <ul className="space-y-2 text-xs">
            {analysis.statutes!.map((s, i) => (
              <li key={i} className="border-l-2 border-navy pl-2">
                <b>{s.offence}</b> — {s.section}
                <span className="text-slate-500 block">{s.act}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(analysis.timeline?.length ?? 0) > 0 && (
        <div className="rounded-xl border p-3">
          <p className="text-xs font-semibold text-navy mb-2">Extracted Timeline</p>
          <ul className="space-y-2 text-xs border-l-2 border-slate-200 pl-3">
            {analysis.timeline!.slice(0, 8).map((ev, i) => (
              <li key={i}>
                <span className="font-semibold text-navy">{ev.date_raw}</span>
                <p className="text-slate-600 mt-0.5">{ev.event}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.metadata && (
        <div className="rounded-xl border p-3 text-xs text-slate-600 grid sm:grid-cols-2 gap-2">
          {analysis.metadata.filename != null && (
            <p>
              <span className="font-medium">File:</span> {String(analysis.metadata.filename)}
            </p>
          )}
          {analysis.metadata.author != null && String(analysis.metadata.author) !== "" && (
            <p>
              <span className="font-medium">Author:</span> {String(analysis.metadata.author)}
            </p>
          )}
          {analysis.metadata.file_type != null && (
            <p>
              <span className="font-medium">Type:</span> {String(analysis.metadata.file_type).toUpperCase()}
            </p>
          )}
          {analysis.metadata.sha256 != null && (
            <p className="truncate" title={String(analysis.metadata.sha256)}>
              <span className="font-medium">Hash:</span> {String(analysis.metadata.sha256).slice(0, 16)}…
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function EvidenceWorkspace() {
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState("");
  const [tab, setTab] = useState<Tab>("upload");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [analysis, setAnalysis] = useState<api.EvidenceAnalysis | null>(null);
  const [courtOrders, setCourtOrders] = useState<Array<Record<string, unknown>>>([]);
  const [repository, setRepository] = useState<api.EvidenceItem[]>([]);
  const [matterTimeline, setMatterTimeline] = useState<api.EvidenceAnalysis["timeline"]>([]);
  const [docA, setDocA] = useState("");
  const [docB, setDocB] = useState("");
  const [contradictions, setContradictions] = useState<Record<string, unknown> | null>(null);
  const [statuteText, setStatuteText] = useState("");
  const [statutes, setStatutes] = useState<api.EvidenceAnalysis["statutes"]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadMatters = useCallback(async () => {
    const r = await api.listMatters();
    setMatters(r.matters || []);
    if (r.matters?.[0] && !matterId) setMatterId(r.matters[0].matter_id);
  }, [matterId]);

  const loadRepository = useCallback(async () => {
    if (!matterId) return;
    try {
      const r = await api.getEvidenceRepository(matterId);
      setRepository(r.items || []);
      setMatterTimeline(r.timeline || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load repository");
    }
  }, [matterId]);

  useEffect(() => {
    loadMatters().catch(() => {});
  }, [loadMatters]);

  useEffect(() => {
    if (matterId && (tab === "repository" || tab === "timeline")) {
      loadRepository().catch(() => {});
    }
  }, [matterId, tab, loadRepository]);

  const processFiles = async (files: FileList | File[]) => {
    if (!matterId) {
      setErr("Select a matter first");
      return;
    }
    setBusy(true);
    setErr("");
    setAnalysis(null);
    setCourtOrders([]);
    try {
      const list = Array.from(files);
      let lastAnalysis: api.EvidenceAnalysis | null = null;
      let lastOrders: Array<Record<string, unknown>> = [];
      for (const file of list) {
        const res = await api.uploadEvidence(file, matterId);
        lastAnalysis = (res.analysis as api.EvidenceAnalysis) || null;
        lastOrders = (res.court_orders as Array<Record<string, unknown>>) || [];
      }
      setAnalysis(lastAnalysis);
      setCourtOrders(lastOrders);
      await loadRepository();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const runContradiction = async () => {
    setBusy(true);
    setErr("");
    try {
      setContradictions(await api.detectEvidenceContradictions({ document_a: docA, document_b: docB }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const runStatutes = async () => {
    if (!statuteText.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.findEvidenceStatutes(statuteText, matterId);
      setStatutes(r.statutes || []);
      const co = await api.matchEvidenceCourtOrders(statuteText, matterId);
      setCourtOrders(co.results || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "upload", label: "Upload Evidence" },
    { id: "repository", label: "Evidence Repository" },
    { id: "timeline", label: "Timeline" },
    { id: "contradiction", label: "Contradiction Check" },
    { id: "statutes", label: "Statute & Orders" },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Evidence Intelligence Center"
        subtitle="Upload, OCR, classify, and investigate evidence — linked to your matters"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-6xl mx-auto w-full space-y-5 sm:space-y-6 pb-8">
        {err && (
          <p className="text-red-600 text-sm bg-red-50 border px-4 py-3 rounded-lg">{err}</p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-600">Linked matter</label>
          <select
            className="border rounded-lg px-3 py-2 text-sm max-w-md flex-1 min-w-[180px]"
            value={matterId}
            onChange={(e) => setMatterId(e.target.value)}
          >
            {matters.map((m) => (
              <option key={m.matter_id} value={m.matter_id}>
                {m.matter_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-1 border-b pb-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-xs sm:text-sm rounded-t-lg border-b-2 transition-colors ${
                tab === t.id
                  ? "border-navy text-navy font-semibold bg-white"
                  : "border-transparent text-slate-500 hover:text-navy"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "upload" && (
          <div className="grid lg:grid-cols-2 gap-6">
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-navy">Evidence Upload</h2>
              <p className="text-xs text-slate-500">
                PDF, DOCX, images, Excel, email (EML/MSG), ZIP — OCR and metadata extraction run automatically.
              </p>
              <div
                role="button"
                tabIndex={0}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (e.dataTransfer.files?.length) processFiles(e.dataTransfer.files);
                }}
                onClick={() => fileRef.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  dragOver ? "border-navy bg-navy/5" : "border-slate-300 hover:border-navy/40"
                }`}
              >
                <p className="text-3xl mb-2">📁</p>
                <p className="text-sm font-medium text-navy">Drag & drop evidence files</p>
                <p className="text-xs text-slate-500 mt-1">or click to browse</p>
                <input
                  ref={fileRef}
                  type="file"
                  className="hidden"
                  accept={ACCEPT}
                  multiple
                  onChange={(e) => e.target.files && processFiles(e.target.files)}
                />
              </div>
              {busy && <p className="text-xs text-slate-500 animate-pulse">Analyzing evidence…</p>}
            </section>
            <section>
              <h2 className="text-sm font-semibold text-navy mb-3">AI Evidence Analysis</h2>
              <AnalysisPanel analysis={analysis} />
              {courtOrders.length > 0 && (
                <div className="mt-4 rounded-xl border p-3">
                  <p className="text-xs font-semibold text-navy mb-2">Similar Court Orders</p>
                  <ul className="space-y-2 text-xs">
                    {courtOrders.map((o, i) => (
                      <li key={i} className="border-l-2 border-emerald-600 pl-2">
                        <b>{String(o.case_number || o.title || "Order")}</b>
                        <p className="text-slate-600">{String(o.summary || o.snippet || "")}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "repository" && (
          <section className="space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-semibold text-navy">Evidence Repository</h2>
              <button type="button" onClick={() => loadRepository()} className="text-xs text-navy underline">
                Refresh
              </button>
            </div>
            {repository.length === 0 ? (
              <p className="text-sm text-slate-500 border rounded-xl p-6 text-center">
                No evidence uploaded for this matter yet.
              </p>
            ) : (
              <div className="space-y-3">
                {repository.map((item) => {
                  const pct = item.evidence_strength?.percent ?? Math.round((item.relevance_score ?? 0) * 100);
                  return (
                    <div key={item.item_id} className="border rounded-xl p-4 bg-white shadow-sm">
                      <div className="flex flex-wrap justify-between gap-2">
                        <div>
                          <p className="font-medium text-sm text-navy">{item.source_identifier}</p>
                          <p className="text-xs text-slate-500">{item.category?.replace(/_/g, " ")}</p>
                        </div>
                        <span className={`text-xs font-bold px-2 py-1 rounded-lg border ${strengthColor(pct)}`}>
                          {pct}% {item.evidence_strength?.label || "Relevant"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 mt-2 line-clamp-2">{item.excerpt}</p>
                      {item.item_id && (
                        <div className="mt-2">
                          <ThumbsFeedback
                            compact
                            onUp={() =>
                              api.reviewDiscoveryItem(item.item_id!, { tags: item.tags, verified: true })
                            }
                            onDown={() =>
                              api.reviewDiscoveryItem(item.item_id!, {
                                tags: ["LOW_PRIORITY"],
                                classification: "RELEVANT_LOW",
                              })
                            }
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {tab === "timeline" && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-navy">Evidence Timeline</h2>
            <p className="text-xs text-slate-500">Chronology built automatically from dates across all matter evidence.</p>
            {(matterTimeline?.length ?? 0) === 0 ? (
              <p className="text-sm text-slate-500 border rounded-xl p-6 text-center">No dated events yet.</p>
            ) : (
              <ol className="relative border-l-2 border-navy/20 ml-3 space-y-4 pl-6">
                {matterTimeline!.map((ev, i) => (
                  <li key={i} className="relative">
                    <span className="absolute -left-[1.6rem] top-1 w-3 h-3 rounded-full bg-navy" />
                    <p className="text-sm font-semibold text-navy">{ev.date_raw}</p>
                    <p className="text-xs text-slate-600 mt-1">{ev.event}</p>
                    {ev.source && <p className="text-[10px] text-slate-400 mt-0.5">{ev.source}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}

        {tab === "contradiction" && (
          <section className="space-y-4 max-w-3xl">
            <h2 className="text-sm font-semibold text-navy">Contradiction Detector</h2>
            <p className="text-xs text-slate-500">
              Compare two witness statements or documents — AI highlights conflicting claims.
            </p>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm min-h-[120px] font-mono"
              placeholder="Witness Statement A or Document A…"
              value={docA}
              onChange={(e) => setDocA(e.target.value)}
            />
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm min-h-[120px] font-mono"
              placeholder="Witness Statement B or Document B…"
              value={docB}
              onChange={(e) => setDocB(e.target.value)}
            />
            <button
              type="button"
              disabled={busy || docA.length < 20 || docB.length < 20}
              onClick={runContradiction}
              className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
            >
              Detect contradictions
            </button>
            {contradictions && (
              <div className="rounded-xl border p-4 space-y-3">
                <p className="text-sm font-medium">{String(contradictions.summary)}</p>
                {((contradictions.contradictions as Array<Record<string, string>>) || []).map((c, i) => (
                  <div key={i} className="text-xs border-l-2 border-red-400 pl-3 py-1">
                    <p className="font-semibold text-red-800">{c.type?.replace(/_/g, " ")}</p>
                    <p className="text-slate-600 mt-1">{c.note}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === "statutes" && (
          <section className="space-y-4 max-w-3xl">
            <h2 className="text-sm font-semibold text-navy">Statute Finder & Court Order Matcher</h2>
            <p className="text-xs text-slate-500">
              Paste evidence text to identify potential BNS/BNSS sections and similar orders from your knowledge base.
            </p>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm min-h-[140px]"
              value={statuteText}
              onChange={(e) => setStatuteText(e.target.value)}
              placeholder="Paste evidence excerpt…"
            />
            <button
              type="button"
              disabled={busy || statuteText.length < 20}
              onClick={runStatutes}
              className="px-4 py-2 bg-emerald-800 text-white rounded-lg text-sm disabled:opacity-50"
            >
              Find statutes & similar orders
            </button>
            {(statutes?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-4">
                <p className="text-xs font-semibold text-navy mb-2">Potential Statutes</p>
                <ul className="space-y-2 text-xs">
                  {statutes!.map((s, i) => (
                    <li key={i}>
                      <b>{s.offence}</b> — {s.section}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {courtOrders.length > 0 && (
              <div className="rounded-xl border p-4">
                <p className="text-xs font-semibold text-navy mb-2">Similar Court Orders</p>
                <ul className="space-y-2 text-xs">
                  {courtOrders.map((o, i) => (
                    <li key={i}>{String(o.summary || o.snippet || o.title || JSON.stringify(o))}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
