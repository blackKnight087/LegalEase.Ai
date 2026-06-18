"use client";

import { useState } from "react";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import * as api from "@/lib/api";

type ToolResult = Record<string, unknown> | null;

const QUICK_FORWARD = ["302", "304A", "420", "376", "498A"];
const QUICK_REVERSE = ["103", "105", "420", "376", "85"];

export default function IpcBnsConvertPanel({
  direction,
  run,
  busy,
  showBulk = false,
}: {
  direction: "forward" | "reverse";
  run: (fn: () => Promise<ToolResult>) => void;
  busy: boolean;
  showBulk?: boolean;
}) {
  const [section, setSection] = useState("");
  const [bulk, setBulk] = useState("302, 420, 376");
  const isForward = direction === "forward";
  const sourceLabel = isForward ? "IPC" : "BNS";
  const targetLabel = isForward ? "BNS" : "IPC";
  const quick = isForward ? QUICK_FORWARD : QUICK_REVERSE;

  const convert = () => {
    const s = section.trim();
    if (!s) return;
    run(() => api.legalConversionConvert(s, direction));
  };

  return (
    <div className="space-y-5">
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <h3 className="font-semibold text-sm mb-1 text-slate-900 m-0">
          {sourceLabel} → {targetLabel}
        </h3>
        <p className="text-xs text-slate-500 m-0 mb-4">
          Official mapping dataset only — deterministic lookup, no AI guessing.
        </p>
        <label className="block text-xs text-slate-500 font-medium mb-1">{sourceLabel} section</label>
        <input
          className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm mb-3"
          placeholder={isForward ? "e.g. 302" : "e.g. 103"}
          value={section}
          onChange={(e) => setSection(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && convert()}
        />
        <button
          type="button"
          disabled={busy || !section.trim()}
          onClick={convert}
          className="px-5 py-2.5 bg-slate-900 text-white rounded-lg text-sm font-semibold disabled:opacity-50"
        >
          Convert to {targetLabel}
        </button>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {quick.map((q) => (
            <button
              key={q}
              type="button"
              className="text-xs px-2.5 py-1 rounded-lg border border-slate-200 bg-slate-50 hover:bg-white"
              onClick={() => {
                setSection(q);
                run(() => api.legalConversionConvert(q, direction));
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {showBulk && isForward && (
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="font-semibold text-sm mb-2 text-slate-900 m-0">Bulk IPC → BNS</h3>
          <VoiceTextarea
            className="mb-3"
            rows={3}
            placeholder="302, 420, 376 — comma separated"
            value={bulk}
            onChange={setBulk}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const sections = bulk
                  .split(/[,\n]+/)
                  .map((s) => s.trim())
                  .filter(Boolean);
                try {
                  return (await api.ipcBnsV3Bulk(sections)) as ToolResult;
                } catch {
                  const legacy = await api.ipcBulk(sections);
                  const rows = (legacy.results || []).map((r) => api.normalizeIpcBnsConversion(r));
                  const mapped = rows.filter((r) => r.found).length;
                  return {
                    results: rows,
                    total: rows.length,
                    mapped_count: mapped,
                    unmapped_count: rows.length - mapped,
                  } as ToolResult;
                }
              })
            }
            className="px-5 py-2.5 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50 disabled:opacity-50"
          >
            Convert all
          </button>
        </div>
      )}
    </div>
  );
}

export function IpcBnsConversionResult({
  result,
  direction,
}: {
  result: ToolResult;
  direction: "forward" | "reverse";
}) {
  if (!result) return null;
  if (result.error) {
    const err = String(result.error);
    const hint =
      err.toLowerCase().includes("not found") || err.includes("404")
        ? " Service temporarily unavailable — try again in a moment."
        : "";
    return (
      <p className="mt-6 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3 m-0">
        {err}
        {hint}
      </p>
    );
  }

  const bulkResults = result.results as Array<Record<string, unknown>> | undefined;
  if (bulkResults) {
    return (
      <div className="mt-6 le-card rounded-xl border overflow-hidden">
        <div className="px-4 py-3 border-b bg-slate-50 text-sm font-semibold text-slate-800">
          Bulk conversion — {Number(result.mapped_count)}/{Number(result.total)} mapped
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50/80 text-left">
              <tr>
                <th className="p-3">IPC</th>
                <th className="p-3">BNS</th>
                <th className="p-3">Title</th>
                <th className="p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {bulkResults.map((r, i) => (
                <tr key={i} className="border-t">
                  <td className="p-3 font-medium">{String(r.ipc_section || r.ipc_key || "—")}</td>
                  <td className="p-3">{r.found ? String(r.bns_section || r.bns_key) : "—"}</td>
                  <td className="p-3 text-slate-600">{String(r.offence_title || r.short_description || "—")}</td>
                  <td className="p-3 text-xs">{r.found ? "Mapped" : String(r.message || "Not found")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (!result.found) {
    return (
      <div className="mt-6 p-4 bg-amber-50 rounded-xl text-sm border border-amber-200">
        <p className="font-semibold text-amber-950 m-0">Not in official dataset</p>
        <p className="text-amber-900 mt-2 m-0">{String(result.message)}</p>
      </div>
    );
  }

  const oldLabel = String(result.old_section_label || result.ipc_section || "");
  const newLabel = String(result.new_section_label || result.bns_section || "—");
  const oldTitle = String(result.old_title || result.offence_title || "");
  const newTitle = String(result.new_title || result.short_description || "");

  return (
    <div className="mt-6 p-5 bg-white rounded-xl border border-emerald-200 shadow-sm space-y-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-800 m-0">Official mapping</p>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-lg bg-slate-50 p-4 border border-slate-100">
          <p className="text-[10px] font-bold uppercase text-slate-500 m-0 mb-1">
            {direction === "forward" ? "IPC" : "IPC (equivalent)"}
          </p>
          <p className="text-lg font-bold text-slate-900 m-0">{oldLabel}</p>
          <p className="text-sm text-slate-600 mt-1 m-0">{oldTitle}</p>
        </div>
        <div className="rounded-lg bg-blue-50/50 p-4 border border-blue-100">
          <p className="text-[10px] font-bold uppercase text-blue-800 m-0 mb-1">
            {direction === "forward" ? "BNS" : "BNS (query)"}
          </p>
          <p className="text-lg font-bold text-slate-900 m-0">{newLabel}</p>
          <p className="text-sm text-slate-600 mt-1 m-0">{newTitle}</p>
        </div>
      </div>
      <dl className="grid sm:grid-cols-2 gap-2 text-sm">
        {[
          ["Mapping type", result.mapping_type || result.mapping_status],
          ["Status", result.status_label || "Active"],
          ["Punishment", result.punishment],
          ["Cognizable", result.cognizable],
          ["Bailable", result.bailable],
          ["Court", result.court_type || result.court_jurisdiction],
        ]
          .filter(([, v]) => v != null && String(v) !== "")
          .map(([k, v]) => (
            <div key={String(k)} className="flex justify-between gap-2 border-b border-slate-100 py-1.5">
              <dt className="text-slate-500 m-0">{String(k)}</dt>
              <dd className="font-medium text-slate-800 m-0 text-right">{String(v)}</dd>
            </div>
          ))}
      </dl>
      <p className="text-[11px] text-slate-500 m-0">Source: ipc_bns_official.json · Dataset {String(result.dataset_version)}</p>
    </div>
  );
}
