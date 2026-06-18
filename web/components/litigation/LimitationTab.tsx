"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

export default function LimitationTab() {
  const [presets, setPresets] = useState<api.LimitationPreset[]>([]);
  const [matters, setMatters] = useState<Array<{ matter_id: string; matter_name: string }>>([]);
  const [presetId, setPresetId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [matterId, setMatterId] = useState("");
  const [calc, setCalc] = useState<Record<string, unknown> | null>(null);
  const [deadlines, setDeadlines] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    void api.fetchLimitationPresets().then((r) => {
      const p = r.presets || [];
      setPresets(p);
      if (p[0]) setPresetId(p[0].id);
    });
    void api.listMatters().then((r) => {
      setMatters(
        (r.matters || []).map((m: { matter_id?: string; matter_name?: string }) => ({
          matter_id: String(m.matter_id || ""),
          matter_name: String(m.matter_name || ""),
        }))
      );
    });
    void api.fetchLitigationLimitationDeadlines().then((r) => setDeadlines(r.deadlines || []));
  }, []);

  const runCalc = useCallback(async () => {
    if (!presetId || !startDate) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.calculateLimitation(presetId, startDate);
      setCalc(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Calculation failed");
    } finally {
      setBusy(false);
    }
  }, [presetId, startDate]);

  const addToMatter = async () => {
    if (!matterId || !presetId || !startDate) {
      setErr("Select a matter, preset, and start date");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.addLimitationToMatter(matterId, presetId, startDate);
      setMsg("Deadline added to matter workflow.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add deadline");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</p>
      )}
      {msg && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">{msg}</p>
      )}

      <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-navy m-0 mb-3">Firm limitation deadlines</h2>
        {deadlines.length === 0 ? (
          <p className="text-xs text-slate-500 m-0">No matter deadlines on file.</p>
        ) : (
          <ul className="space-y-2 m-0 p-0 list-none text-sm">
            {deadlines.map((d) => (
              <li key={String(d.deadline_id)} className="flex flex-wrap justify-between gap-2 border border-slate-100 rounded-lg px-3 py-2">
                <div>
                  <p className="font-medium text-navy m-0">{String(d.title)}</p>
                  <p className="text-xs text-slate-500 m-0">{String(d.matter_name)} · {String(d.due_date || "").slice(0, 10)}</p>
                </div>
                <span className={`text-xs font-semibold tabular-nums ${Number(d.days_remaining) < 0 ? "text-red-600" : Number(d.days_remaining) <= 7 ? "text-amber-700" : "text-emerald-700"}`}>
                  {d.days_remaining == null ? "—" : `${d.days_remaining}d`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
        <h2 className="text-sm font-semibold text-navy m-0">Limitation & prescription</h2>
        <p className="text-xs text-slate-500 m-0">
          Indian limitation presets — calculate due dates and push to matter deadlines.
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="text-xs text-slate-600">
            Preset
            <select
              className="le-input mt-1 w-full"
              value={presetId}
              onChange={(e) => setPresetId(e.target.value)}
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            Start date (YYYY-MM-DD)
            <input
              type="date"
              className="le-input mt-1 w-full"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          disabled={busy}
          className="le-interactive px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          onClick={() => void runCalc()}
        >
          Calculate
        </button>
        {calc && (
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 text-sm">
            <p className="font-semibold text-navy m-0">{String(calc.label || "Due date")}</p>
            <p className="text-2xl font-bold text-navy mt-1 m-0">{String(calc.due_date || "—")}</p>
            <p className="text-xs text-slate-600 mt-2 m-0">{String(calc.description || "")}</p>
          </div>
        )}
        <div className="border-t border-slate-100 pt-4">
          <label className="text-xs text-slate-600 block mb-2">
            Add to matter
            <select
              className="le-input mt-1 w-full"
              value={matterId}
              onChange={(e) => setMatterId(e.target.value)}
            >
              <option value="">— Select matter —</option>
              {matters.map((m) => (
                <option key={m.matter_id} value={m.matter_id}>
                  {m.matter_name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !matterId}
            className="le-interactive mt-2 px-4 py-2 border border-navy text-navy rounded-lg text-sm font-medium disabled:opacity-50"
            onClick={() => void addToMatter()}
          >
            Save as matter deadline
          </button>
          {matterId && (
            <Link href={`/matters/${matterId}/tasks`} className="block text-xs text-blue-600 mt-2 hover:underline">
              View matter tasks →
            </Link>
          )}
        </div>
      </section>
    </div>
  );
}
