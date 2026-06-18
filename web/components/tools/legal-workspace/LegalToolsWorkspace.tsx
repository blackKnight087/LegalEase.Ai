"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Alert from "@/components/ui/Alert";
import MarkdownBox from "@/components/ui/MarkdownBox";
import * as api from "@/lib/api";
import {
  legislativeChangeAnalysis,
  inferCategory,
  loadJson,
  pushRecent,
  parseSectionQuery,
  saveJson,
  STORAGE_KEYS,
  RELATED_SECTIONS,
  exportBulkCsv,
  type MappingRecord,
  type WorkspaceModule,
} from "@/lib/legalToolsWorkspace";
import {
  BulkConversionModule,
  BulkResultsTable,
  CaseAssessmentModule,
  CitationValidatorModule,
  ConfusedMappingsModule,
  ContractReviewModuleV2,
  CourtFeeModuleV2,
  LegislativeTrackerModule,
  LimitationModuleV2,
} from "./LegalToolsModules";

const NAV: Array<{ id: WorkspaceModule; label: string; disabled?: boolean }> = [
  { id: "ipc-bns", label: "IPC ↔ BNS" },
  { id: "crpc-bnss", label: "CrPC ↔ BNSS" },
  { id: "limitation", label: "Limitation calculator" },
  { id: "court-fee", label: "Court fee calculator" },
  { id: "contract", label: "Contract review" },
  { id: "citation", label: "Citation validator" },
  { id: "legislative", label: "Legislative changes" },
  { id: "confused", label: "Most confused sections" },
  { id: "bulk", label: "Bulk conversion" },
  { id: "case-assessment", label: "Case assessment" },
  { id: "saved", label: "Saved research" },
  { id: "recent", label: "Recent searches" },
];

type IntelTab = "overview" | "notes" | "cases" | "related" | "history" | "bookmarks";

function ChangeBadge({ badge }: { badge: string }) {
  const k = badge.toLowerCase();
  const cls =
    k === "new"
      ? "legal-tools-v2__badge--new"
      : k === "unchanged"
        ? "legal-tools-v2__badge--unchanged"
        : k === "repealed"
          ? "legal-tools-v2__badge--repealed"
          : "legal-tools-v2__badge--modified";
  return <span className={`legal-tools-v2__badge ${cls}`}>{badge}</span>;
}

function ResearchSkeleton() {
  return (
    <div className="space-y-4">
      <div className="legal-tools-v2__skeleton h-32" />
      <div className="legal-tools-v2__skeleton h-48" />
      <div className="legal-tools-v2__skeleton h-64" />
    </div>
  );
}

function MappingResearchView({ record, pairLabel }: { record: MappingRecord; pairLabel: string }) {
  const change = legislativeChangeAnalysis(record);
  const ipcSec = String(record.old_section || record.ipc_key || "—");
  const bnsSec = record.found ? String(record.new_section || record.bns_key || "—") : "—";
  const oldAct = pairLabel.startsWith("CrPC") ? "Code of Criminal Procedure, 1973" : "Indian Penal Code, 1860";
  const newAct = pairLabel.startsWith("CrPC")
    ? "Bharatiya Nagarik Suraksha Sanhita, 2023"
    : "Bharatiya Nyaya Sanhita, 2023";

  return (
    <div className="space-y-5">
      <article className="legal-tools-v2__research-card">
        <div className="legal-tools-v2__research-hero">
          <p className="text-[10px] uppercase tracking-widest opacity-75 m-0">Official mapping · {pairLabel}</p>
          <h1 className="font-serif text-3xl font-bold m-0 mt-2">
            Section {ipcSec}
          </h1>
          <p className="text-sm opacity-90 m-0 mt-2">{String(record.old_title || record.offence_title)}</p>
        </div>
        <div className="p-6 legal-tools-v2__stat-grid">
          {[
            ["Category", inferCategory(String(record.old_title || ""))],
            ["Punishment", record.punishment],
            ["Cognizable", record.cognizable],
            ["Bailable", record.bailable],
            ["Court", record.court_type || record.court_jurisdiction],
            ["Status", record.found ? "Replaced under new code" : "Verify manually"],
          ]
            .filter(([, v]) => v != null && String(v) !== "")
            .map(([k, v]) => (
              <div key={String(k)} className="legal-tools-v2__stat">
                <p className="text-[10px] uppercase text-slate-500 m-0">{String(k)}</p>
                <p className="text-sm font-semibold text-slate-900 m-0 mt-1">{String(v)}</p>
              </div>
            ))}
        </div>
      </article>

      <article className="legal-tools-v2__research-card">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-serif text-lg font-bold m-0">Mapping comparison</h2>
          <ChangeBadge badge={change.badge} />
        </div>
        <div className="legal-tools-v2__mapping-grid">
          <div className="legal-tools-v2__mapping-card">
            <p className="text-[10px] font-bold uppercase text-slate-500 m-0">{pairLabel.split("↔")[0].trim()}</p>
            <p className="text-2xl font-bold text-slate-900 m-0 mt-2">§ {ipcSec}</p>
            <p className="text-sm text-slate-600 m-0 mt-2">{String(record.old_title || record.offence_title)}</p>
            <p className="text-xs text-slate-500 m-0 mt-3">{oldAct}</p>
          </div>
          <div className="legal-tools-v2__mapping-arrow">↓</div>
          <div className="legal-tools-v2__mapping-card border-blue-100 bg-blue-50/30">
            <p className="text-[10px] font-bold uppercase text-blue-800 m-0">{pairLabel.split("↔")[1]?.trim()}</p>
            <p className="text-2xl font-bold text-slate-900 m-0 mt-2">§ {bnsSec}</p>
            <p className="text-sm text-slate-600 m-0 mt-2">{String(record.new_title || record.short_description || "—")}</p>
            <p className="text-xs text-slate-500 m-0 mt-3">{newAct}</p>
          </div>
        </div>
      </article>

      <article className="legal-tools-v2__research-card p-6">
        <h2 className="font-serif text-lg font-bold m-0 mb-4">Legislative change analysis</h2>
        <p className="text-sm text-slate-600 m-0 mb-4">{change.summary}</p>
        <div className="grid sm:grid-cols-2 gap-4 text-sm">
          {[
            ["Added", change.added],
            ["Removed", change.removed],
            ["Modified", change.modified],
            ["Penalty changes", change.penaltyChanges],
            ["Terminology", change.terminologyChanges],
            ["Procedure", change.proceduralChanges],
          ].map(([title, items]) =>
            (items as string[]).length ? (
              <div key={String(title)} className="rounded-xl border border-slate-100 p-3 bg-slate-50/50">
                <p className="text-[10px] font-bold uppercase text-slate-500 m-0 mb-2">{title}</p>
                <ul className="m-0 pl-4 space-y-1 text-slate-700">
                  {(items as string[]).map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null
          )}
        </div>
        <p className="text-[11px] text-slate-500 mt-4 m-0 border-t pt-3">
          Source: official JSON mapping only · Dataset {String(record.dataset_version || "—")}
        </p>
      </article>
    </div>
  );
}

function IntelligencePanel({
  record,
  intelTab,
  setIntelTab,
  related,
  onRelated,
  notes,
  setNotes,
  bookmarks,
  onBookmark,
}: {
  record: MappingRecord | null;
  intelTab: IntelTab;
  setIntelTab: (t: IntelTab) => void;
  related: string[];
  onRelated: (s: string) => void;
  notes: string;
  setNotes: (n: string) => void;
  bookmarks: string[];
  onBookmark: () => void;
}) {
  const tabs: { id: IntelTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "notes", label: "Notes" },
    { id: "cases", label: "Cases" },
    { id: "related", label: "Related" },
    { id: "history", label: "History" },
    { id: "bookmarks", label: "Bookmarks" },
  ];

  return (
    <aside className="legal-tools-v2__intel">
      <div className="legal-tools-v2__intel-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={intelTab === t.id ? "is-active" : ""}
            onClick={() => setIntelTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto le-scroll p-4 text-sm">
        {intelTab === "overview" && (
          <div className="space-y-3">
            {record?.found ? (
              <>
                <p className="m-0 font-semibold text-slate-900">Mapped · 100% dataset match</p>
                <p className="text-slate-600 m-0 text-xs">Deterministic lookup — no AI section guessing.</p>
                <p className="m-0">
                  <span className="text-slate-500">Type:</span> {String(record.mapping_type || record.mapping_status)}
                </p>
              </>
            ) : (
              <p className="text-amber-800 m-0">Search a section to view intelligence.</p>
            )}
            <button type="button" onClick={onBookmark} className="w-full py-2 rounded-lg border text-xs font-semibold">
              {bookmarks.includes(String(record?.old_section)) ? "Bookmarked" : "Bookmark section"}
            </button>
          </div>
        )}
        {intelTab === "notes" && (
          <textarea
            className="le-input le-textarea w-full text-xs min-h-[200px]"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Research notes for this section…"
          />
        )}
        {intelTab === "cases" && (
          <p className="text-slate-500 m-0 text-xs">
            Link judgments from Matters or research — case citations coming from your matter corpus.
          </p>
        )}
        {intelTab === "related" && (
          <ul className="m-0 p-0 list-none space-y-1">
            {related.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  className="w-full text-left px-2 py-2 rounded-lg hover:bg-slate-50 font-medium text-blue-800"
                  onClick={() => onRelated(s)}
                >
                  § {s}
                </button>
              </li>
            ))}
            {!related.length && <li className="text-slate-500 text-xs">No related sections curated for this entry.</li>}
          </ul>
        )}
        {intelTab === "history" && (
          <p className="text-xs text-slate-500 m-0">
            BNS 2023 replaced IPC for substantive criminal law; BNSS replaced CrPC for procedure. Verify every citation
            against official mapping tables before filing.
          </p>
        )}
        {intelTab === "bookmarks" && (
          <ul className="m-0 p-0 list-none space-y-1">
            {bookmarks.map((b) => (
              <li key={b}>
                <button type="button" className="text-blue-800 font-medium" onClick={() => onRelated(b)}>
                  IPC {b}
                </button>
              </li>
            ))}
            {!bookmarks.length && <li className="text-slate-500 text-xs">No bookmarks yet.</li>}
          </ul>
        )}
      </div>
    </aside>
  );
}

export default function LegalToolsWorkspace() {
  const [module, setModule] = useState<WorkspaceModule>("ipc-bns");
  const [search, setSearch] = useState("");
  const [record, setRecord] = useState<MappingRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [intelTab, setIntelTab] = useState<IntelTab>("overview");
  const [bulkRows, setBulkRows] = useState<MappingRecord[]>([]);
  const [citations, setCitations] = useState<Array<{ from: string; to: string; ipc: string; bns: string }>>([]);
  const [miscResult, setMiscResult] = useState<Record<string, unknown> | null>(null);
  const [bookmarks, setBookmarks] = useState<string[]>([]);
  const [recent, setRecent] = useState<Array<{ q: string; module: WorkspaceModule; at: string }>>([]);
  const [notes, setNotes] = useState("");
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [regions, setRegions] = useState<string[]>([]);
  const [limitPresets, setLimitPresets] = useState<api.LimitationPreset[]>([]);
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);

  const pairForModule = (m: WorkspaceModule): "ipc_bns" | "crpc_bnss" =>
    m === "crpc-bnss" ? "crpc_bnss" : "ipc_bns";

  const pairLabel = module === "crpc-bnss" ? "CrPC ↔ BNSS" : "IPC ↔ BNS";

  useEffect(() => {
    setBookmarks(loadJson(STORAGE_KEYS.bookmarks, []));
    setRecent(loadJson(STORAGE_KEYS.recent, []));
    api.legalConversionMeta().then(setMeta).catch(() => {});
    api.courtFeeRegions().then((d) => setRegions(d.regions || [])).catch(() => {});
    api.fetchLimitationPresets().then((d) => setLimitPresets(d.presets || [])).catch(() => {});
    api.listMatters().then((d) => setMatters(d.matters || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (record?.old_section) {
      const key = `legalease.tools.note.${record.old_section}`;
      setNotes(loadJson(key, ""));
    }
  }, [record?.old_section]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const runLookup = useCallback(
    async (q: string, mod: WorkspaceModule = module) => {
      const parsed = parseSectionQuery(q);
      if (!parsed && mod !== "citation") {
        setErr("Enter a section number or offence keyword (e.g. IPC 302, Murder).");
        return;
      }
      setLoading(true);
      setErr("");
      try {
        let rec: MappingRecord;
        if (parsed?.act === "keyword" || (!parsed && q)) {
          const sr = await api.legalConversionSearch(q, pairForModule(mod));
          const hit = sr.results?.[0];
          if (!hit) throw new Error("No official mapping for this search.");
          rec = hit as MappingRecord;
        } else if (parsed) {
          const pair = pairForModule(mod === "crpc-bnss" ? "crpc-bnss" : "ipc-bns");
          const direction =
            parsed.act === "bns" || parsed.act === "bnss" ? "reverse" : "forward";
          rec = await api.legalConversionConvert(parsed.section, direction, "", pair);
        } else {
          throw new Error("Invalid query");
        }
        setRecord(rec);
        setModule(mod === "bulk" || mod === "citation" ? "ipc-bns" : mod);
        setRecent(pushRecent(q, mod));
      } catch (e) {
        setRecord(null);
        setErr(e instanceof Error ? e.message : "Lookup failed");
      } finally {
        setLoading(false);
      }
    },
    [module]
  );

  const run = async (fn: () => Promise<Record<string, unknown> | null>) => {
    setBusy(true);
    try {
      setMiscResult(await fn());
    } catch (e) {
      setMiscResult({ error: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  };

  const saveNote = () => {
    if (!record?.old_section) return;
    saveJson(`legalease.tools.note.${record.old_section}`, notes);
  };

  useEffect(() => {
    saveNote();
  }, [notes, record?.old_section]);

  const toggleBookmark = () => {
    const sec = String(record?.old_section || "");
    if (!sec) return;
    const next = bookmarks.includes(sec) ? bookmarks.filter((b) => b !== sec) : [...bookmarks, sec];
    setBookmarks(next);
    saveJson(STORAGE_KEYS.bookmarks, next);
  };

  const centerContent = () => {
    if (loading) return <ResearchSkeleton />;
    if (module === "limitation")
      return <LimitationModuleV2 presets={limitPresets} matters={matters} run={run} busy={busy} />;
    if (module === "court-fee") return <CourtFeeModuleV2 regions={regions} run={run} busy={busy} />;
    if (module === "contract") return <ContractReviewModuleV2 run={run} busy={busy} />;
    if (module === "case-assessment") return <CaseAssessmentModule run={run} busy={busy} />;
    if (module === "bulk")
      return (
        <>
          <BulkConversionModule run={run} busy={busy} onRows={setBulkRows} />
          <BulkResultsTable rows={bulkRows} onExport={() => exportBulkCsv(bulkRows)} />
        </>
      );
    if (module === "citation")
      return (
        <>
          <CitationValidatorModule run={run} busy={busy} onReplacements={setCitations} />
          {citations.length > 0 && (
            <div className="legal-tools-v2__research-card p-5 mt-4 space-y-2">
              <h3 className="font-semibold m-0 text-sm">Suggested replacements</h3>
              {citations.map((c, i) => (
                <div key={i} className="flex justify-between text-sm border-b py-2">
                  <span className="text-red-700 line-through">{c.from}</span>
                  <span className="text-emerald-800 font-medium">→ {c.to}</span>
                </div>
              ))}
            </div>
          )}
        </>
      );
    if (module === "confused") return <ConfusedMappingsModule onPick={(ipc) => runLookup(ipc, "ipc-bns")} />;
    if (module === "legislative") return <LegislativeTrackerModule />;
    if (module === "recent")
      return (
        <div className="legal-tools-v2__research-card p-5 space-y-2">
          <h2 className="font-serif text-lg font-bold m-0">Recent searches</h2>
          {recent.map((r, i) => (
            <button
              key={i}
              type="button"
              className="block w-full text-left px-3 py-2 rounded-lg hover:bg-slate-50 text-sm"
              onClick={() => {
                setSearch(r.q);
                runLookup(r.q, r.module);
              }}
            >
              {r.q} <span className="text-slate-400 text-xs">· {new Date(r.at).toLocaleString()}</span>
            </button>
          ))}
          {!recent.length && <p className="text-slate-500 text-sm m-0">No recent searches.</p>}
        </div>
      );
    if (module === "saved")
      return (
        <div className="legal-tools-v2__research-card p-5">
          <h2 className="font-serif text-lg font-bold m-0 mb-3">Bookmarks</h2>
          {bookmarks.map((b) => (
            <button
              key={b}
              type="button"
              className="block text-blue-800 font-medium mb-2"
              onClick={() => runLookup(`IPC ${b}`, "ipc-bns")}
            >
              IPC {b}
            </button>
          ))}
          {!bookmarks.length && <p className="text-slate-500 text-sm m-0">Pin sections from the intelligence panel.</p>}
        </div>
      );
    if (record?.found || (record && !record.found)) {
      if (!record.found) {
        return (
          <div className="legal-tools-v2__research-card p-6 border-amber-200 bg-amber-50">
            <p className="font-semibold text-amber-950 m-0">Not in official dataset</p>
            <p className="text-sm m-0 mt-2">{String(record.message)}</p>
          </div>
        );
      }
      return <MappingResearchView record={record} pairLabel={pairLabel} />;
    }
    return (
      <div className="le-empty legal-tools-v2__research-card min-h-[360px] flex flex-col items-center justify-center p-8 text-center">
        <p className="font-serif text-xl text-slate-800 m-0">Legal research workspace</p>
        <p className="text-sm text-slate-500 mt-2 m-0 max-w-md">
          Search IPC 302, BNS 103, offence keywords, or pick a tool from the sidebar. Official mapping data only.
        </p>
        <p className="text-[11px] text-slate-400 mt-4 m-0">
          {Number(meta?.record_count) || "—"} mappings · Ctrl+K to focus search
        </p>
      </div>
    );
  };

  return (
    <div className="legal-tools-v2 flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Legal intelligence"
        title="Legal Tools"
        subtitle="Research · compare · validate · convert — official datasets only"
      />
      {err && (
        <div className="px-4 pt-2">
          <Alert variant="error">{err}</Alert>
        </div>
      )}
      <div className="legal-tools-v2__shell flex-1 min-h-0">
        <nav className="legal-tools-v2__sidebar">
          <div className="px-3 py-3 border-b border-slate-100">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 m-0">Workspace</p>
          </div>
          <div className="legal-tools-v2__sidebar-nav">
            {NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={item.disabled}
                className={`legal-tools-v2__nav-btn ${module === item.id ? "is-active" : ""} ${item.disabled ? "is-disabled" : ""}`}
                onClick={() => {
                  if (item.disabled) return;
                  setModule(item.id);
                  setErr("");
                  if (item.id === "ipc-bns" || item.id === "crpc-bnss") setRecord(null);
                }}
              >
                {item.label}
                {item.disabled && <span className="block text-[10px] opacity-70 font-normal">Coming soon</span>}
              </button>
            ))}
          </div>
        </nav>

        <div className="legal-tools-v2__main">
          <div className="legal-tools-v2__search-bar">
            <input
              ref={searchRef}
              className="legal-tools-v2__search-input"
              placeholder="Search: IPC 302, BNS 103, Murder, Cheating, CrPC 154… (Ctrl+K)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search.trim() && runLookup(search.trim())}
            />
          </div>
          <div className="legal-tools-v2__body">
            <div className="legal-tools-v2__center">{centerContent()}</div>
            <IntelligencePanel
              record={record}
              intelTab={intelTab}
              setIntelTab={setIntelTab}
              related={record ? RELATED_SECTIONS[String(record.old_section)] || [] : []}
              onRelated={(s) => runLookup(`IPC ${s}`, "ipc-bns")}
              notes={notes}
              setNotes={setNotes}
              bookmarks={bookmarks}
              onBookmark={toggleBookmark}
            />
          </div>
        </div>
      </div>
      {miscResult?.prediction != null && String(miscResult.prediction) !== "" ? (
        <div className="px-4 pb-4 max-w-3xl">
          <div className="legal-tools-v2__research-card p-5">
            <MarkdownBox content={String(miscResult.prediction)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
