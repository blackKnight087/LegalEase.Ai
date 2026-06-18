"use client";

import { useEffect, useState } from "react";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import MarkdownBox from "@/components/ui/MarkdownBox";
import * as api from "@/lib/api";
import {
  CONFUSED_MAPPINGS,
  exportBulkCsv,
  IPC_SECTION_RE,
  type MappingRecord,
} from "@/lib/legalToolsWorkspace";

type RunFn = (fn: () => Promise<Record<string, unknown> | null>) => void;

export function BulkConversionModule({
  run,
  busy,
  onRows,
}: {
  run: RunFn;
  busy: boolean;
  onRows: (rows: MappingRecord[]) => void;
}) {
  const [bulk, setBulk] = useState("302\n420\n376\n498A\n304B");

  const convert = () => {
    const sections = bulk
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    run(async () => {
      try {
        const r = await api.ipcBnsV3Bulk(sections);
        const rows = (r.results as MappingRecord[]) || [];
        onRows(rows.map((x) => api.normalizeIpcBnsConversion(x)));
        return r as Record<string, unknown>;
      } catch {
        const legacy = await api.ipcBulk(sections);
        const rows = (legacy.results || []).map((x) => api.normalizeIpcBnsConversion(x));
        onRows(rows);
        return { results: rows } as Record<string, unknown>;
      }
    });
  };

  return (
    <div className="legal-tools-v2__research-card p-6 space-y-4">
      <h2 className="font-serif text-xl font-bold text-slate-900 m-0">Bulk conversion</h2>
      <p className="text-sm text-slate-500 m-0">Official IPC↔BNS dataset — one section per line or comma-separated.</p>
      <VoiceTextarea rows={5} value={bulk} onChange={setBulk} className="w-full" />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={convert}
          className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold disabled:opacity-50"
        >
          Convert all
        </button>
      </div>
    </div>
  );
}

export function CitationValidatorModule({
  run,
  busy,
  onReplacements,
}: {
  run: RunFn;
  busy: boolean;
  onReplacements: (items: Array<{ from: string; to: string; ipc: string; bns: string }>) => void;
}) {
  const [text, setText] = useState("The accused is charged under Section 302 IPC and Section 420 IPC.");

  const scan = () => {
    run(async () => {
      const found = new Map<string, string>();
      let m: RegExpExecArray | null;
      const re = new RegExp(IPC_SECTION_RE.source, IPC_SECTION_RE.flags);
      while ((m = re.exec(text)) !== null) {
        found.set(m[1].toUpperCase(), m[0]);
      }
      const items: Array<{ from: string; to: string; ipc: string; bns: string }> = [];
      for (const ipc of found.keys()) {
        const r = await api.legalConversionConvert(ipc, "forward");
        if (r.found) {
          items.push({
            from: found.get(ipc) || `Section ${ipc} IPC`,
            to: `BNS ${String(r.new_section || r.bns_key)}`,
            ipc,
            bns: String(r.new_section || r.bns_key),
          });
        }
      }
      onReplacements(items);
      return { count: items.length, items };
    });
  };

  return (
    <div className="legal-tools-v2__research-card p-6 space-y-4">
      <h2 className="font-serif text-xl font-bold m-0">Smart citation validator</h2>
      <p className="text-sm text-slate-500 m-0">Detects deprecated IPC references and suggests official BNS equivalents.</p>
      <VoiceTextarea rows={8} value={text} onChange={setText} className="w-full" />
      <button
        type="button"
        disabled={busy}
        onClick={scan}
        className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold"
      >
        Scan & suggest replacements
      </button>
    </div>
  );
}

export function ConfusedMappingsModule({ onPick }: { onPick: (ipc: string) => void }) {
  return (
    <div className="space-y-4">
      <div className="legal-tools-v2__research-card p-5">
        <h2 className="font-serif text-xl font-bold m-0 mb-1">Most confused mappings</h2>
        <p className="text-sm text-slate-500 m-0">Curated from official mapping tables — high-risk renumbering.</p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {CONFUSED_MAPPINGS.map((c) => (
          <button
            key={c.ipc}
            type="button"
            onClick={() => onPick(c.ipc)}
            className="legal-tools-v2__research-card p-4 text-left hover:border-slate-400 transition-colors"
          >
            <p className="text-xs text-slate-500 m-0 mb-2">IPC {c.ipc} → BNS {c.bns}</p>
            <p className="font-semibold text-slate-900 m-0 text-sm">{c.ipcTitle}</p>
            <p className="text-xs text-slate-600 mt-1 m-0">{c.bnsTitle}</p>
            {c.note && <p className="text-xs text-amber-800 mt-2 m-0">{c.note}</p>}
          </button>
        ))}
      </div>
    </div>
  );
}

export function LegislativeTrackerModule() {
  const items = [
    { type: "REPEALED", label: "Decriminalised / omitted", example: "IPC 309 (attempted suicide)" },
    { type: "MODIFIED", label: "Renumbered offences", example: "IPC 302 → BNS 103" },
    { type: "NEW", label: "New BNS provisions", example: "Mob violence / new offences (verify in official text)" },
    { type: "REPEALED", label: "Removed archaic sections", example: "IPC 124A — no direct BNS equivalent in dataset" },
  ];
  return (
    <div className="space-y-4">
      <div className="legal-tools-v2__research-card p-6">
        <h2 className="font-serif text-xl font-bold m-0">Legislative change tracker</h2>
        <p className="text-sm text-slate-500 mt-2 m-0">
          Timeline view derived from official mapping status fields — not AI-generated commentary.
        </p>
        <div className="mt-6 space-y-4 border-l-2 border-slate-200 pl-4">
          {items.map((it, i) => (
            <div key={i} className="relative">
              <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-slate-400" />
              <span className={`legal-tools-v2__badge legal-tools-v2__badge--${it.type.toLowerCase()}`}>
                {it.type}
              </span>
              <p className="font-semibold text-sm text-slate-900 m-0 mt-1">{it.label}</p>
              <p className="text-xs text-slate-600 m-0">{it.example}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LimitationModuleV2({
  presets,
  matters,
  run,
  busy,
}: {
  presets: api.LimitationPreset[];
  matters: api.Matter[];
  run: RunFn;
  busy: boolean;
}) {
  const [presetId, setPresetId] = useState(presets[0]?.id || "");
  const [startDate, setStartDate] = useState("");
  const [matterType, setMatterType] = useState("");
  const [courtType, setCourtType] = useState("District Court");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!presetId && presets[0]) setPresetId(presets[0].id);
  }, [presets, presetId]);

  const calc = () => {
    run(async () => {
      const r = await api.calculateLimitation(presetId, startDate);
      setResult(r);
      return r;
    });
  };

  const preset = presets.find((p) => p.id === presetId);

  return (
    <div className="legal-tools-v2__research-card p-6 space-y-4 max-w-2xl">
      <h2 className="font-serif text-xl font-bold m-0">Limitation calculator</h2>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-xs text-slate-500 block">
          Matter type
          <input
            className="le-input w-full mt-1"
            value={matterType}
            onChange={(e) => setMatterType(e.target.value)}
            placeholder="e.g. Money recovery"
          />
        </label>
        <label className="text-xs text-slate-500 block">
          Court type
          <select className="le-input w-full mt-1" value={courtType} onChange={(e) => setCourtType(e.target.value)}>
            {["District Court", "High Court", "Supreme Court", "Tribunal"].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="text-xs text-slate-500 block">
        Limitation preset
        <select className="le-input w-full mt-1" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label} ({p.days} days)
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-500 block">
        Cause of action date
        <input type="date" className="le-input w-full mt-1" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
      </label>
      {preset && (
        <p className="text-xs text-slate-600 m-0 bg-slate-50 rounded-lg p-3 border">
          Reference: Limitation Act — {preset.label}. Period: {preset.days} days.
        </p>
      )}
      <button type="button" disabled={busy || !presetId || !startDate} onClick={calc} className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold">
        Compute limitation
      </button>
      {result?.ok === true ? (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm">
          <p className="m-0 font-semibold">{String(result.label)}</p>
          <p className="m-0 mt-1">Due date: <b>{String(result.due_date)}</b></p>
          <p className="text-slate-600 m-0 mt-1">{String(result.description)}</p>
        </div>
      ) : null}
    </div>
  );
}

export function CourtFeeModuleV2({
  regions,
  run,
  busy,
}: {
  regions: string[];
  run: RunFn;
  busy: boolean;
}) {
  const [v, setV] = useState(100000);
  const [region, setRegion] = useState(regions[0] || "Delhi");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (regions[0]) setRegion(regions[0]);
  }, [regions]);

  return (
    <div className="legal-tools-v2__research-card p-6 space-y-4 max-w-2xl">
      <h2 className="font-serif text-xl font-bold m-0">Court fee calculator</h2>
      <label className="text-xs text-slate-500 block">
        Jurisdiction
        <select className="le-input w-full mt-1" value={region} onChange={(e) => setRegion(e.target.value)}>
          {regions.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-500 block">
        Suit value (₹)
        <input type="number" className="le-input w-full mt-1" value={v} onChange={(e) => setV(+e.target.value)} />
      </label>
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          run(async () => {
            const r = await api.courtFeeCalc({
              suit_value: v,
              region,
              suit_type: "civil",
              court_level: "district",
            });
            setResult(r);
            return r;
          })
        }
        className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold"
      >
        Calculate
      </button>
      {result?.final_fee != null && (
        <div className="space-y-3">
          <p className="text-3xl font-bold text-amber-600 m-0">₹{Number(result.final_fee).toLocaleString()}</p>
          <p className="text-sm text-slate-500 m-0">Estimated court fee · {region}</p>
          <pre className="text-xs bg-slate-50 rounded-lg p-3 overflow-auto border m-0">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export function ContractReviewModuleV2({ run, busy }: { run: RunFn; busy: boolean }) {
  const [analysis, setAnalysis] = useState("");

  const flags = [
    "Termination",
    "Confidentiality",
    "Arbitration",
    "Jurisdiction",
    "Force majeure",
    "Indemnity",
    "Liability cap",
  ];

  return (
    <div className="space-y-4">
      <div className="legal-tools-v2__research-card p-6">
        <h2 className="font-serif text-xl font-bold m-0">Contract review</h2>
        <p className="text-sm text-slate-500 mt-1 m-0">Upload PDF for clause-level risk scan.</p>
        <input
          type="file"
          accept=".pdf"
          className="mt-4 text-sm w-full"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f)
              run(async () => {
                const r = await api.contractReview(f);
                setAnalysis(String(r.analysis || ""));
                return r;
              });
            e.target.value = "";
          }}
        />
      </div>
      {analysis && (
        <>
          <div className="legal-tools-v2__stat-grid">
            <div className="legal-tools-v2__stat">
              <p className="text-[10px] uppercase text-slate-500 m-0">Risk score</p>
              <p className="text-2xl font-bold text-amber-600 m-0">Review</p>
            </div>
            <div className="legal-tools-v2__stat">
              <p className="text-[10px] uppercase text-slate-500 m-0">Clause coverage</p>
              <p className="text-2xl font-bold m-0">AI scan</p>
            </div>
            <div className="legal-tools-v2__stat">
              <p className="text-[10px] uppercase text-slate-500 m-0">Red flags</p>
              <p className="text-2xl font-bold text-red-600 m-0">
                {flags.filter((f) => analysis.toLowerCase().includes(f.toLowerCase())).length}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {flags.map((f) => (
              <span
                key={f}
                className={`text-xs px-2 py-1 rounded-lg border ${
                  analysis.toLowerCase().includes(f.toLowerCase())
                    ? "bg-red-50 border-red-200 text-red-800"
                    : "bg-slate-50 border-slate-200 text-slate-500"
                }`}
              >
                {f}
              </span>
            ))}
          </div>
          <div className="legal-tools-v2__research-card p-5">
            <MarkdownBox content={analysis} />
          </div>
        </>
      )}
    </div>
  );
}

export function CaseAssessmentModule({ run, busy }: { run: RunFn; busy: boolean }) {
  const [details, setDetails] = useState("");
  return (
    <div className="legal-tools-v2__research-card p-6 space-y-4 max-w-2xl">
      <h2 className="font-serif text-xl font-bold m-0">Case assessment assistant</h2>
      <p className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-lg p-3 m-0">
        Not legal advice. Informational assessment only — verify with qualified counsel and court records.
      </p>
      <VoiceTextarea rows={6} value={details} onChange={setDetails} placeholder="Summarize facts, evidence, and procedural posture…" />
      <button
        type="button"
        disabled={busy || !details.trim()}
        onClick={() => run(() => api.casePrediction({ case_details: details, court_type: "District Court" }))}
        className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold"
      >
        Run assessment
      </button>
    </div>
  );
}

export function BulkResultsTable({
  rows,
  onExport,
}: {
  rows: MappingRecord[];
  onExport: () => void;
}) {
  if (!rows.length) return null;
  return (
    <div className="legal-tools-v2__research-card overflow-hidden mt-4">
      <div className="px-4 py-3 border-b flex justify-between items-center bg-slate-50">
        <span className="text-sm font-semibold">Bulk results ({rows.length})</span>
        <button type="button" onClick={onExport} className="text-xs font-semibold px-3 py-1.5 rounded-lg border bg-white">
          Export CSV
        </button>
      </div>
      <div className="overflow-x-auto le-scroll">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="p-3">IPC</th>
              <th className="p-3">Title</th>
              <th className="p-3">BNS</th>
              <th className="p-3">BNS title</th>
              <th className="p-3">Mapping</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t">
                <td className="p-3 font-medium">{String(r.old_section || r.ipc_key)}</td>
                <td className="p-3 text-slate-600">{String(r.old_title || r.offence_title)}</td>
                <td className="p-3">{r.found ? String(r.new_section || r.bns_key) : "—"}</td>
                <td className="p-3 text-slate-600">{String(r.new_title || r.short_description || "—")}</td>
                <td className="p-3 text-xs">{String(r.mapping_type || r.mapping_status || "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
