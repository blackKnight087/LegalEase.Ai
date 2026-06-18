"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

const BUCKET_LABELS: Record<string, string> = {
  urgent_hearings: "Urgent hearings",
  high_risk: "High risk",
  vip_clients: "VIP clients",
  critical_deadlines: "Critical deadlines",
};

export default function WatchlistTab() {
  const [items, setItems] = useState<api.LegalWatch[]>([]);
  const [buckets, setBuckets] = useState<Record<string, Array<Record<string, unknown>>>>({});
  const [watchType, setWatchType] = useState("hearing");
  const [label, setLabel] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [w, dash] = await Promise.all([api.fetchWatchlist(), api.fetchLitigationWatchlistDashboard()]);
      setItems(w.items || []);
      setBuckets((dash.buckets as Record<string, Array<Record<string, unknown>>>) || {});
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load watchlist");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async () => {
    if (!label.trim() || !query.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await api.addWatchlistItem({ watch_type: watchType, label: label.trim(), query: query.trim() });
      setLabel("");
      setQuery("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Add failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</p>
      )}

      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {Object.entries(BUCKET_LABELS).map(([key, title]) => {
          const entries = buckets[key] || [];
          return (
            <div key={key} className="border rounded-xl p-3 bg-white shadow-sm">
              <h3 className="text-xs font-semibold text-navy m-0 mb-2">{title}</h3>
              {entries.length === 0 ? (
                <p className="text-xs text-slate-400 m-0">None</p>
              ) : (
                <ul className="space-y-1 m-0 p-0 list-none text-xs">
                  {entries.slice(0, 5).map((e, i) => (
                    <li key={i} className="truncate">
                      {e.matter_id ? (
                        <Link href={`/litigation?tab=war-room&matter=${e.matter_id}`} className="text-emerald-700 hover:underline">
                          {String(e.matter_name || e.label || e.title || "Item")}
                        </Link>
                      ) : (
                        String(e.label || e.title || "Item")
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[10px] text-slate-400 mt-2 m-0">{entries.length} item(s)</p>
            </div>
          );
        })}
      </section>

      <section className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
        <h2 className="text-sm font-semibold text-navy m-0">Legal watchlist</h2>
        <p className="text-xs text-slate-500 m-0">
          Monitor hearings, gazette updates, statutory sections, or custom queries across your practice.
        </p>
        <div className="grid sm:grid-cols-3 gap-3">
          <select className="le-input text-sm" value={watchType} onChange={(e) => setWatchType(e.target.value)}>
            <option value="hearing">Hearing</option>
            <option value="gazette">Gazette</option>
            <option value="section">Section</option>
            <option value="custom">Custom</option>
          </select>
          <input className="le-input text-sm" placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} />
          <input className="le-input text-sm" placeholder="Search query" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <button type="button" disabled={busy} className="le-interactive px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50" onClick={() => void add()}>
          Add watch
        </button>
      </section>

      <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-navy m-0 mb-3">Active watches ({items.length})</h3>
        {items.length === 0 ? (
          <p className="text-sm text-slate-500 m-0">No watches yet.</p>
        ) : (
          <ul className="space-y-2 m-0 p-0 list-none">
            {items.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-2 text-sm">
                <div>
                  <span className="font-medium text-navy">{w.label}</span>
                  <span className="text-xs text-slate-500 ml-2">{w.watch_type}</span>
                  <p className="text-xs text-slate-600 m-0 mt-0.5">{w.query}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => void api.checkWatchlistItem(w.id).then(() => load())}>
                    Check
                  </button>
                  <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => void api.removeWatchlistItem(w.id).then(() => load())}>
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

