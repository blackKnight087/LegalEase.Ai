"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

type TabHref =
  | "hearings"
  | "calendar"
  | "court-sync"
  | "tasks"
  | "orders"
  | "evidence"
  | "limitation"
  | "watchlist"
  | "analytics"
  | "war-room";

function Kpi({
  label,
  value,
  tone = "slate",
  href,
}: {
  label: string;
  value: number | string;
  tone?: string;
  href?: TabHref;
}) {
  const bg: Record<string, string> = {
    navy: "bg-slate-900 text-white border-slate-800",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-900",
    amber: "bg-amber-50 border-amber-200 text-amber-900",
    rose: "bg-rose-50 border-rose-200 text-rose-900",
    slate: "bg-white border-slate-200 text-navy",
  };
  const inner = (
    <>
      <p className={`text-[10px] font-medium uppercase tracking-wide ${tone === "navy" ? "text-slate-300" : "text-slate-500"}`}>
        {label}
      </p>
      <p className="text-xl font-bold tabular-nums mt-0.5">{value}</p>
    </>
  );
  if (href) {
    return (
      <Link
        href={`/litigation?tab=${href}`}
        className={`rounded-lg border p-3 block hover:ring-2 hover:ring-emerald-300 transition-shadow ${bg[tone] || bg.slate}`}
      >
        {inner}
      </Link>
    );
  }
  return <div className={`rounded-lg border p-3 ${bg[tone] || bg.slate}`}>{inner}</div>;
}

function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="border border-slate-200 rounded-xl bg-white overflow-hidden h-full flex flex-col">
      <div className="px-3 py-2 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-navy m-0">{title}</h3>
        {action}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  );
}

function EmptyHint({ text, href, linkLabel }: { text: string; href: string; linkLabel: string }) {
  return (
    <p className="text-xs text-slate-500 p-3 m-0">
      {text}{" "}
      <Link href={href} className="text-emerald-700 font-medium hover:underline">
        {linkLabel}
      </Link>
    </p>
  );
}

export default function MissionControlTab() {
  const [dash, setDash] = useState<api.LitigationDashboard | null>(null);
  const [diag, setDiag] = useState<api.LitigationDiagnostics | null>(null);
  const [showDiag, setShowDiag] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setDash(await api.fetchLitigationDashboard());
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load dashboard");
    }
  }, []);

  const loadDiag = useCallback(async () => {
    try {
      setDiag(await api.fetchLitigationDiagnostics());
    } catch {
      setDiag(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (showDiag) void loadDiag();
  }, [showDiag, loadDiag]);

  if (err) {
    return (
      <div className="p-4 sm:p-6 space-y-3">
        <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">{err}</p>
        <button type="button" onClick={load} className="text-sm text-emerald-700 font-medium underline">
          Retry
        </button>
      </div>
    );
  }
  if (!dash) {
    return <p className="text-slate-500 text-sm p-6">Loading Mission Control…</p>;
  }

  const alerts = dash.urgent_alerts || [];
  const todayBoard = dash.today_board || [];
  const tomorrowBoard = (dash.tomorrow_board || []) as Array<Record<string, string>>;
  const timeline = dash.upcoming_timeline || [];
  const tasks = dash.today_tasks || [];
  const orders = dash.recent_orders || [];
  const workload = dash.lawyer_workload || [];
  const vip = dash.vip_client_matters || [];
  const health = dash.matter_health || [];

  return (
    <div className="p-3 sm:p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-navy">Litigation Command Center</h2>
          <p className="text-xs text-slate-500">Live metrics from your matters, hearings, tasks, and deadlines</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowDiag((v) => !v)}
            className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50"
          >
            {showDiag ? "Hide diagnostics" : "Diagnostics"}
          </button>
          <button type="button" onClick={load} className="text-xs px-3 py-1.5 text-emerald-700 font-medium">
            Refresh
          </button>
        </div>
      </div>

      {showDiag && diag && (
        <section className="border border-slate-200 rounded-xl bg-slate-50 p-4 text-xs space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold text-navy m-0">System diagnostics</p>
            {diag.overall_status && (
              <span className="px-2 py-0.5 rounded-full bg-white border text-[10px] font-semibold uppercase">
                {diag.overall_status}
              </span>
            )}
          </div>
          <div className="grid sm:grid-cols-4 gap-2">
            {Object.entries(diag.table_counts || {}).map(([k, v]) => (
              <div key={k} className="bg-white border rounded-lg px-2 py-1.5">
                <span className="text-slate-500">{k}:</span> <strong>{v}</strong>
              </div>
            ))}
          </div>
          <ul className="grid sm:grid-cols-2 gap-1 m-0 p-0 list-none">
            {(diag.modules || []).map((m) => (
              <li key={m.id} className="flex gap-2 items-center">
                <span
                  className={`w-2 h-2 rounded-full ${
                    m.status === "ok"
                      ? "bg-emerald-500"
                      : m.status === "partial"
                        ? "bg-amber-500"
                        : m.status === "error"
                          ? "bg-red-500"
                          : "bg-slate-300"
                  }`}
                />
                {m.label} — {m.status} ({m.records ?? 0})
              </li>
            ))}
          </ul>
          {diag.routes && Object.keys(diag.routes).length > 0 && (
            <p className="text-slate-600 m-0">
              Routes:{" "}
              {Object.entries(diag.routes)
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </p>
          )}
          {(diag.warnings || []).map((w) => (
            <p key={w} className="text-amber-800 m-0">
              • {w}
            </p>
          ))}
          {(diag.issues || []).map((issue) => (
            <p key={issue} className="text-red-700 m-0">
              • {issue}
            </p>
          ))}
        </section>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-8 gap-2">
        <Kpi label="Today" value={dash.today_hearings} tone="navy" href="hearings" />
        <Kpi label="Tomorrow" value={dash.tomorrow_hearings ?? 0} tone="navy" href="hearings" />
        <Kpi label="This week" value={dash.this_week_hearings} tone="emerald" href="calendar" />
        <Kpi label="Urgent" value={dash.urgent_matters} tone="amber" href="watchlist" />
        <Kpi label="High risk" value={dash.high_risk_matters ?? 0} tone="amber" href="watchlist" />
        <Kpi label="Limitation" value={dash.limitation_deadlines} tone="rose" href="limitation" />
        <Kpi label="Critical lim." value={dash.limitation_critical} tone="rose" href="limitation" />
        <Kpi label="Tasks" value={dash.pending_tasks} href="tasks" />
        <Kpi label="Orders review" value={dash.orders_awaiting_review ?? 0} href="orders" />
        <Kpi label="Evidence records" value={dash.evidence_records ?? dash.evidence_pending ?? 0} href="evidence" />
        <Kpi label="Evidence review" value={dash.evidence_pending_review ?? 0} href="evidence" />
        <Kpi label="Drafts" value={dash.drafts_pending} href="tasks" />
        <Kpi label="VIP clients" value={dash.vip_clients} href="watchlist" />
        <Kpi label="Active matters" value={dash.active_matters} href="war-room" />
        <Kpi label="Upcoming" value={dash.upcoming_hearings} href="calendar" />
      </div>

      {vip.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center text-xs border border-amber-200 bg-amber-50 rounded-lg px-3 py-2">
          <span className="font-semibold text-amber-900">VIP:</span>
          {vip.map((m) => (
            <Link
              key={m.matter_id}
              href={`/litigation?tab=war-room&matter=${m.matter_id}`}
              className="px-2 py-0.5 bg-white border border-amber-200 rounded-full text-amber-900 hover:bg-amber-100"
            >
              {m.matter_name}
            </Link>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2 grid sm:grid-cols-2 gap-3">
          <Panel title="Today's hearings" action={<Link href="/litigation?tab=hearings" className="text-[10px] text-emerald-700">All →</Link>}>
            <ul className="divide-y divide-slate-100 max-h-48 overflow-y-auto">
              {todayBoard.length === 0 ? (
                <EmptyHint text="No hearings today." href="/litigation?tab=court-sync" linkLabel="Import cause list →" />
              ) : (
                todayBoard.map((h, i) => (
                  <li key={`${h.hearing_id}-${i}`} className="px-3 py-2 text-xs flex flex-wrap gap-1 items-center">
                    <span className="font-semibold text-navy">{h.matter_name}</span>
                    <span className="text-slate-500">{h.court_name}</span>
                    {h.matter_id && (
                      <Link href={`/litigation?tab=war-room&matter=${h.matter_id}`} className="ml-auto text-emerald-700">
                        Open →
                      </Link>
                    )}
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Tomorrow">
            <ul className="divide-y divide-slate-100 max-h-48 overflow-y-auto">
              {tomorrowBoard.length === 0 ? (
                <EmptyHint text="Nothing tomorrow yet." href="/litigation?tab=court-sync" linkLabel="Sync court data →" />
              ) : (
                tomorrowBoard.map((h, i) => (
                  <li key={`tm-${i}`} className="px-3 py-2 text-xs">
                    <span className="font-semibold text-navy">{h.matter_name}</span>
                    <span className="text-slate-500 ml-1">{h.court_name}</span>
                    <p className="text-slate-400 m-0">{h.purpose}</p>
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Upcoming timeline (14 days)" action={<Link href="/litigation?tab=calendar" className="text-[10px] text-emerald-700">Calendar →</Link>}>
            <ul className="divide-y divide-slate-100 max-h-52 overflow-y-auto sm:col-span-2">
              {timeline.length === 0 ? (
                <EmptyHint text="No upcoming hearings." href="/litigation?tab=court-sync" linkLabel="Court Sync →" />
              ) : (
                timeline.map((h, i) => (
                  <li key={`tl-${i}`} className="px-3 py-1.5 text-xs flex gap-2">
                    <span className="text-slate-400 tabular-nums w-20 shrink-0">{String(h.hearing_date || "").slice(0, 10)}</span>
                    <span className="font-medium text-navy truncate">{String(h.matter_name)}</span>
                    <span className="text-slate-500 truncate hidden sm:inline">{String(h.court_name || "")}</span>
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Matter health (lowest scores)">
            <ul className="divide-y divide-slate-100 max-h-52 overflow-y-auto">
              {health.length === 0 ? (
                <p className="text-xs text-slate-500 p-3 m-0">No matters to score.</p>
              ) : (
                health.map((m) => (
                  <li key={m.matter_id} className="px-3 py-2 text-xs flex items-center gap-2">
                    <span
                      className={`font-bold tabular-nums w-8 ${
                        m.score < 50 ? "text-red-600" : m.score < 75 ? "text-amber-600" : "text-emerald-600"
                      }`}
                    >
                      {m.score}
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium text-navy m-0 truncate">{m.matter_name}</p>
                      <p className="text-slate-400 m-0 truncate">{m.factors.join(" · ")}</p>
                    </div>
                  </li>
                ))
              )}
            </ul>
          </Panel>
        </div>

        <div className="space-y-3">
          <Panel title="Urgent alerts">
            <ul className="divide-y divide-slate-100 max-h-36 overflow-y-auto">
              {alerts.length === 0 ? (
                <p className="text-xs text-slate-500 p-3 m-0">No urgent alerts.</p>
              ) : (
                alerts.map((a, i) => (
                  <li key={i} className="px-3 py-2 text-xs">
                    <Link href={`/litigation?tab=${a.href_tab}${a.matter_id ? `&matter=${a.matter_id}` : ""}`} className="text-amber-800 hover:underline">
                      {a.message}
                    </Link>
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Today's tasks" action={<Link href="/litigation?tab=tasks" className="text-[10px] text-emerald-700">Tasks →</Link>}>
            <ul className="divide-y divide-slate-100 max-h-36 overflow-y-auto">
              {tasks.length === 0 ? (
                <EmptyHint text="No due/overdue tasks." href="/litigation?tab=tasks" linkLabel="Add task →" />
              ) : (
                tasks.map((t) => (
                  <li key={String(t.task_id)} className="px-3 py-1.5 text-xs">
                    <span className="font-medium text-navy">{String(t.title)}</span>
                    <span className="text-slate-400 ml-1">{String(t.due_date)}</span>
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Recent orders" action={<Link href="/litigation?tab=orders" className="text-[10px] text-emerald-700">Orders →</Link>}>
            <ul className="divide-y divide-slate-100 max-h-36 overflow-y-auto">
              {orders.length === 0 ? (
                <EmptyHint text="No orders stored." href="/litigation?tab=court-sync" linkLabel="Sync from eCourts →" />
              ) : (
                orders.map((o) => (
                  <li key={String(o.order_id)} className="px-3 py-1.5 text-xs">
                    <p className="font-medium text-navy m-0 truncate">{String(o.title)}</p>
                    <p className="text-slate-400 m-0">{String(o.matter_name)} · {String(o.order_date || "—")}</p>
                  </li>
                ))
              )}
            </ul>
          </Panel>

          <Panel title="Lawyer workload">
            <ul className="divide-y divide-slate-100">
              {workload.length === 0 ? (
                <p className="text-xs text-slate-500 p-3 m-0">No open tasks assigned.</p>
              ) : (
                workload.map((w) => (
                  <li key={w.lawyer} className="px-3 py-1.5 text-xs flex justify-between">
                    <span className="text-navy truncate">{w.lawyer}</span>
                    <span className="font-semibold tabular-nums">{w.open_tasks}</span>
                  </li>
                ))
              )}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
