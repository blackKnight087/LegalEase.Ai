"use client";

import { useState } from "react";
import * as api from "@/lib/api";

type Entry = Record<string, unknown>;

type Props = {
  entries: Entry[];
  matterId: string;
  busy: boolean;
  onRefresh: () => void;
  onPolish: (raw: string, units: number) => Promise<string>;
};

export default function TimeEntriesTable({ entries, matterId, busy, onRefresh, onPolish }: Props) {
  const [editId, setEditId] = useState<string | null>(null);
  const [editRaw, setEditRaw] = useState("");
  const [editHours, setEditHours] = useState("");
  const [editRate, setEditRate] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [err, setErr] = useState("");

  const startEdit = (e: Entry) => {
    setEditId(String(e.record_id));
    setEditRaw(String(e.raw_activity || e.narrative_description || ""));
    setEditHours(String(e.units_logged ?? ""));
    setEditRate(String(e.rate_per_unit ?? ""));
  };

  const saveEdit = async () => {
    if (!editId) return;
    setErr("");
    try {
      const narrative = await onPolish(editRaw, parseFloat(editHours) || 1);
      await api.updateBillingEntry(editId, {
        raw_activity: editRaw,
        units_logged: parseFloat(editHours) || 1,
        rate_per_unit: parseFloat(editRate) || 1000,
        narrative_description: narrative,
      });
      setEditId(null);
      onRefresh();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Update failed");
    }
  };

  const runBulk = async () => {
    if (!matterId || !bulkText.trim()) return;
    const lines = bulkText.split("\n").filter((l) => l.trim());
    const parsed = lines.map((line) => {
      const parts = line.split("|").map((p) => p.trim());
      if (parts.length >= 3) {
        return {
          matter_id: matterId,
          raw_activity: parts[0],
          units_logged: parseFloat(parts[1]) || 1,
          rate_per_unit: parseFloat(parts[2]) || 1000,
        };
      }
      return { matter_id: matterId, raw_activity: line, units_logged: 1, rate_per_unit: 5000 };
    });
    await api.bulkImportBillingEntries(parsed);
    setBulkText("");
    onRefresh();
  };

  const fmtDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return iso?.slice(0, 10) || "—";
    }
  };

  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-navy">Time entries</h2>
        <details className="text-xs">
          <summary className="cursor-pointer text-emerald-700 font-medium">Bulk import</summary>
          <div className="mt-2 space-y-2 min-w-[16rem]">
            <textarea
              className="w-full border rounded-lg p-2 text-xs font-mono"
              rows={4}
              placeholder={"Description | hours | rate per line"}
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
            />
            <button type="button" disabled={busy} onClick={runBulk} className="px-3 py-1.5 bg-navy text-white rounded-lg">
              Import
            </button>
          </div>
        </details>
      </div>
      {err && <p className="text-red-600 text-xs px-4 py-2">{err}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 text-left text-slate-600">
              <th className="p-2 font-semibold">Date</th>
              <th className="p-2 font-semibold">Matter</th>
              <th className="p-2 font-semibold min-w-[12rem]">Description</th>
              <th className="p-2 font-semibold text-right">Hrs</th>
              <th className="p-2 font-semibold text-right">Rate</th>
              <th className="p-2 font-semibold text-right">Amount</th>
              <th className="p-2 font-semibold">Status</th>
              <th className="p-2 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={8} className="p-6 text-center text-slate-500">
                  No time entries for this matter.
                </td>
              </tr>
            )}
            {entries.map((e) => (
              <tr key={String(e.record_id)} className="border-t border-slate-100 hover:bg-slate-50/80">
                <td className="p-2 whitespace-nowrap">{fmtDate(String(e.created_at || ""))}</td>
                <td className="p-2 max-w-[8rem] truncate">{String(e.matter_name || "—")}</td>
                <td className="p-2">
                  {editId === String(e.record_id) ? (
                    <textarea className="w-full border rounded p-1 text-xs" rows={2} value={editRaw} onChange={(ev) => setEditRaw(ev.target.value)} />
                  ) : (
                    <span className="line-clamp-2">{String(e.narrative_description || e.raw_activity || "")}</span>
                  )}
                </td>
                <td className="p-2 text-right">
                  {editId === String(e.record_id) ? (
                    <input className="w-14 border rounded px-1 text-right" value={editHours} onChange={(ev) => setEditHours(ev.target.value)} />
                  ) : (
                    String(e.units_logged ?? "")
                  )}
                </td>
                <td className="p-2 text-right">
                  {editId === String(e.record_id) ? (
                    <input className="w-16 border rounded px-1 text-right" value={editRate} onChange={(ev) => setEditRate(ev.target.value)} />
                  ) : (
                    `₹${Number(e.rate_per_unit || 0).toLocaleString("en-IN")}`
                  )}
                </td>
                <td className="p-2 text-right font-medium">₹{Number(e.line_total || 0).toLocaleString("en-IN")}</td>
                <td className="p-2">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${e.invoice_status === "BILLED" ? "bg-slate-200" : "bg-amber-100 text-amber-900"}`}>
                    {String(e.invoice_status || "UNBILLED")}
                  </span>
                </td>
                <td className="p-2 whitespace-nowrap space-x-1">
                  {editId === String(e.record_id) ? (
                    <>
                      <button type="button" className="text-emerald-700 font-semibold" onClick={saveEdit}>Save</button>
                      <button type="button" className="text-slate-500" onClick={() => setEditId(null)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      {e.invoice_status === "UNBILLED" && (
                        <button type="button" className="text-navy font-medium" onClick={() => startEdit(e)}>Edit</button>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        className="text-slate-600"
                        onClick={async () => {
                          await api.duplicateBillingEntry(String(e.record_id));
                          onRefresh();
                        }}
                      >
                        Dup
                      </button>
                      {e.invoice_status === "UNBILLED" && (
                        <button
                          type="button"
                          className="text-red-600"
                          onClick={async () => {
                            await api.deleteBillingEntry(String(e.record_id));
                            onRefresh();
                          }}
                        >
                          Del
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
