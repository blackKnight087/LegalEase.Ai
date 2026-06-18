"use client";

import { useEffect, useMemo, useState } from "react";
import AnalyticsPieChart, { type PieSlice } from "@/components/analytics/AnalyticsPieChart";
import PageHeader from "@/components/ui/PageHeader";
import * as api from "@/lib/api";

const MODE_COLORS: Record<string, string> = {
  knowledge_base: "#1e3a5f",
  open_law: "#2563eb",
  hybrid: "#7c3aed",
  web_search: "#059669",
  deep_case: "#d97706",
};

type AnalyticsPayload = {
  learning?: {
    modes?: Array<{
      mode: string;
      turns: number;
      positive: number;
      negative: number;
      not_found_rate: number;
    }>;
    learned_queries?: Array<{ query: string; expansion: string; success: number }>;
  };
  judicial?: {
    sample_size?: number;
    bail_grant_rate_pct?: number;
    disposition_breakdown?: Array<{ outcome: string; pct: number }>;
    data_source?: string;
  };
  deal_rooms?: Array<{ room_id: string; name: string; document_count: number }>;
  witness_sessions?: Array<{ session_id: string; witness_name: string }>;
  similar_case_clusters?: Array<{
    label: string;
    count: number;
    modes: string[];
    sample_query?: string;
  }>;
};

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [kpi, setKpi] = useState<api.ProductKpi | null>(null);
  const [err, setErr] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api
      .analyticsFull()
      .then((d) => setData(d as AnalyticsPayload))
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load"));
    api
      .productKpi()
      .then(setKpi)
      .catch(() => {});
  }, []);

  const modeTurnSlices = useMemo((): PieSlice[] => {
    const modes = data?.learning?.modes ?? [];
    return modes
      .filter((m) => m.turns > 0)
      .map((m) => ({
        label: m.mode,
        value: m.turns,
        color: MODE_COLORS[m.mode.toLowerCase()] || undefined,
      }));
  }, [data]);

  const feedbackSlices = useMemo((): PieSlice[] => {
    const modes = data?.learning?.modes ?? [];
    let pos = 0;
    let neg = 0;
    for (const m of modes) {
      pos += m.positive || 0;
      neg += m.negative || 0;
    }
    if (pos + neg === 0) return [];
    return [
      { label: "Positive feedback", value: pos, color: "#059669" },
      { label: "Negative feedback", value: neg, color: "#dc2626" },
    ];
  }, [data]);

  const clusterSlices = useMemo((): PieSlice[] => {
    return (data?.similar_case_clusters ?? [])
      .filter((c) => c.count > 0)
      .map((c) => ({
        label: c.label.length > 40 ? `${c.label.slice(0, 38)}…` : c.label,
        value: c.count,
      }));
  }, [data]);

  const judicialSlices = useMemo((): PieSlice[] => {
    const rows = data?.judicial?.disposition_breakdown ?? [];
    return rows
      .filter((d) => d.pct > 0)
      .map((d) => ({
        label: d.outcome,
        value: d.pct,
      }));
  }, [data]);

  const runExport = async () => {
    setExporting(true);
    try {
      const r = await api.tuningExport();
      alert(`Export: ${r.status} - ${r.record_count} records\n${r.path || ""}`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Analytics & Learning"
        subtitle="Adaptive learning metrics, judicial disposition data, and workspace activity"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-5xl mx-auto w-full space-y-6 sm:space-y-8">
        {kpi && (
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
            {[
              { label: "MAU", value: kpi.mau },
              { label: "DAU", value: kpi.dau },
              { label: "Users", value: kpi.users_total },
              { label: "Retention proxy", value: `${kpi.retention_proxy_pct}%` },
              { label: "Chat turns (7d)", value: kpi.chat_turns_7d },
              { label: "Matters", value: kpi.matters_total },
              { label: "KB hit rate", value: `${kpi.ai.hit_rate_pct}%` },
              { label: "NOT_FOUND rate", value: `${kpi.ai.not_found_rate_pct}%` },
            ].map((card) => (
              <div
                key={card.label}
                className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <p className="text-xs text-slate-500 dark:text-slate-400">{card.label}</p>
                <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{card.value}</p>
              </div>
            ))}
          </section>
        )}
        {err && (
          <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        {!data && !err && <p className="text-slate-500 text-sm">Loading…</p>}

        {data?.learning?.modes && data.learning.modes.length > 0 && (
          <section className="space-y-4">
            <h2 className="font-serif text-lg font-bold text-navy">Chat mode learning</h2>
            <div className="grid lg:grid-cols-2 gap-4">
              {modeTurnSlices.length > 0 && (
                <AnalyticsPieChart
                  title="Turns by chat mode"
                  slices={modeTurnSlices}
                  minShare={0.03}
                />
              )}
              {feedbackSlices.length > 0 && (
                <AnalyticsPieChart
                  title="User feedback (all modes)"
                  slices={feedbackSlices}
                />
              )}
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {data.learning.modes.map((m) => (
                <div key={m.mode} className="border rounded-xl p-4 bg-white">
                  <p className="text-xs font-bold uppercase text-slate-500">{m.mode}</p>
                  <p className="text-2xl font-bold text-navy mt-1">{m.turns}</p>
                  <p className="text-xs text-slate-600">turns</p>
                  <div className="mt-2 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500"
                      style={{
                        width: `${Math.round((1 - (m.not_found_rate || 0)) * 100)}%`,
                      }}
                    />
                  </div>
                  <p className="text-[0.65rem] text-slate-500 mt-1">
                    hit rate ~{Math.round((1 - (m.not_found_rate || 0)) * 100)}%
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        {(data?.similar_case_clusters?.length ?? 0) > 0 && (
          <section className="space-y-4">
            <h2 className="font-serif text-lg font-bold text-navy">Research cluster map</h2>
            {clusterSlices.length >= 2 && (
              <AnalyticsPieChart
                title="Top research topics (query volume)"
                slices={clusterSlices}
                maxSlices={7}
                minShare={0.05}
              />
            )}
            <div className="grid sm:grid-cols-2 gap-3">
              {data!.similar_case_clusters!.map((c) => (
                <div key={c.label} className="border rounded-xl p-4 bg-white">
                  <p className="text-sm font-semibold text-navy">{c.label}</p>
                  <p className="text-2xl font-bold mt-1">{c.count}</p>
                  <p className="text-xs text-slate-500">queries · {c.modes.join(", ")}</p>
                  {c.sample_query ? (
                    <p className="text-[0.7rem] text-slate-600 mt-2 truncate" title={c.sample_query}>
                      e.g. {c.sample_query}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        )}

        {data?.judicial && (
          <section className="space-y-4">
            <h2 className="font-serif text-lg font-bold text-navy">Judicial analytics (DB)</h2>
            <div className="grid lg:grid-cols-2 gap-4">
              {judicialSlices.length >= 2 && (
                <AnalyticsPieChart
                  title="Case disposition mix"
                  slices={judicialSlices}
                />
              )}
              <div className="border rounded-xl p-4 bg-white">
                <p className="text-sm">
                  Sample size: <b>{data.judicial.sample_size}</b> · Bail grant rate:{" "}
                  <b>{data.judicial.bail_grant_rate_pct}%</b>
                </p>
                <p className="text-xs text-slate-500 mt-1">Source: {data.judicial.data_source}</p>
                <ul className="mt-3 space-y-1">
                  {(data.judicial.disposition_breakdown || []).map((d, i) => (
                    <li key={i} className="flex justify-between text-sm">
                      <span>{d.outcome}</span>
                      <span className="font-medium">{d.pct}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        )}

        <section className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={exporting}
            onClick={runExport}
            className="px-4 py-2 bg-navy text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {exporting ? "Exporting…" : "Export tuning JSONL (Stage 3)"}
          </button>
        </section>

        {(data?.deal_rooms?.length ?? 0) > 0 && (
          <section>
            <h2 className="font-serif text-lg font-bold text-navy mb-2">Deal rooms</h2>
            <ul className="text-sm space-y-1">
              {(data?.deal_rooms ?? []).map((r) => (
                <li key={r.room_id}>
                  {r.name} — {r.document_count} docs
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
