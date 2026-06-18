"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

export default function HearingDigestPanel() {
  const [data, setData] = useState<{
    today: api.HearingDigestItem[];
    this_week: api.HearingDigestItem[];
    upcoming: api.HearingDigestItem[];
    total: number;
  } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setErr("");
    try {
      const d = await api.fetchHearingDigest(14);
      setData({
        today: d.today || [],
        this_week: d.this_week || [],
        upcoming: d.upcoming || [],
        total:
          (d.today?.length || 0) +
          (d.this_week?.length || 0) +
          (d.upcoming?.length || 0),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load hearing digest");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const renderList = (items: api.HearingDigestItem[], empty: string) => {
    if (!items.length) {
      return <p className="text-xs text-slate-500 m-0">{empty}</p>;
    }
    return (
      <ul className="space-y-2 m-0 p-0 list-none">
        {items.slice(0, 6).map((h, i) => (
          <li key={`${h.matter_id}-${h.hearing_date}-${i}`}>
            <Link
              href={`/matters/${h.matter_id}/hearings`}
              className="block rounded-lg border border-slate-200 bg-white px-3 py-2 hover:border-blue-300 no-underline"
            >
              <p className="text-sm font-semibold text-navy m-0">{h.hearing_date}</p>
              <p className="text-xs text-slate-600 m-0 truncate">
                {h.matter_name}
                {h.court_name ? ` · ${h.court_name}` : ""}
              </p>
              {h.purpose && (
                <p className="text-[0.65rem] text-slate-500 m-0 mt-0.5">{h.purpose}</p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <section className="rounded-xl sm:rounded-2xl border border-slate-200 bg-white p-3 sm:p-5 shadow-sm">
      <div className="flex items-center justify-between gap-2 mb-2 sm:mb-4">
        <div className="min-w-0">
          <h2 className="text-xs sm:text-sm font-semibold text-navy m-0">Hearings</h2>
          <p className="text-[10px] sm:text-xs text-slate-500 m-0 mt-0.5 truncate">
            <Link href="/litigation" className="text-blue-600 hover:underline">
              Litigation Desk →
            </Link>
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            void load();
          }}
          className="text-xs px-2 py-1 border rounded-lg hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="text-sm text-slate-500">Loading digest…</p>}
      {err && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          {err}
        </p>
      )}
      {!loading && data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
          <div>
            <h3 className="text-[0.65rem] uppercase font-bold text-amber-800 mb-2">
              Today ({data.today.length})
            </h3>
            {renderList(data.today, "No hearings today")}
          </div>
          <div>
            <h3 className="text-[0.65rem] uppercase font-bold text-blue-800 mb-2">
              This week ({data.this_week.length})
            </h3>
            {renderList(data.this_week, "None this week")}
          </div>
          <div>
            <h3 className="text-[0.65rem] uppercase font-bold text-slate-600 mb-2">
              Next 14 days ({data.upcoming.length})
            </h3>
            {renderList(data.upcoming, "No upcoming hearings")}
          </div>
        </div>
      )}
    </section>
  );
}
