"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import PageShell from "@/components/ui/PageShell";
import Alert from "@/components/ui/Alert";
import { ButtonLink } from "@/components/ui/Button";
import IntakePortalCard from "@/components/intake/IntakePortalCard";
import * as api from "@/lib/api";
import { formatApiError } from "@/components/crm/crmUtils";

function formatInr(n: number) {
  const v = Number(n);
  if (!Number.isFinite(v) || v < 0) return "₹0";
  if (v >= 100_000) return `₹${(v / 100_000).toFixed(1)}L`;
  if (v >= 1000) return `₹${Math.round(v / 1000)}k`;
  return `₹${Math.round(v)}`;
}

function timeAgo(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return d.toLocaleDateString();
}

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 animate-pulse">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-20 rounded-2xl bg-slate-100 border border-slate-200" />
      ))}
    </div>
  );
}

export default function IntakeCommandCenter() {
  const [data, setData] = useState<api.CrmCommandCenter | null>(null);
  const [perms, setPerms] = useState<api.CrmPermissions | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [copyErr, setCopyErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cc, p] = await Promise.all([api.fetchCrmCommandCenter(), api.fetchCrmPermissions()]);
      setData(cc);
      setPerms(p);
      setErr("");
    } catch (e) {
      setErr(formatApiError(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const kpis = data?.kpis || {};
  const portal = data?.public_portal || {};
  const labels = data?.stage_labels || {};
  const hasLeads = !!data?.has_leads;

  const kpiItems = [
    { label: "Today's inquiries", value: kpis.new_today ?? 0, accent: "from-blue-500 to-indigo-600" },
    { label: "Urgent leads", value: kpis.urgent_count ?? 0, accent: "from-red-500 to-orange-500" },
    { label: "Consultations", value: kpis.pending_consultations ?? 0, accent: "from-sky-500 to-blue-500" },
    { label: "Qualified", value: kpis.qualified ?? 0, accent: "from-emerald-500 to-teal-500" },
    { label: "Converted", value: kpis.converted ?? 0, accent: "from-green-600 to-emerald-600" },
    {
      label: "Conversion rate",
      value: `${kpis.conversion_rate_pct ?? 0}%`,
      accent: "from-violet-500 to-purple-600",
      isText: true,
    },
    {
      label: "Pipeline value",
      value: formatInr(data?.pipeline_value?.active_pipeline_inr ?? 0),
      accent: "from-amber-500 to-yellow-600",
      isText: true,
    },
    {
      label: "Follow-ups overdue",
      value: data?.follow_ups?.overdue_count ?? 0,
      accent: "from-rose-500 to-pink-600",
    },
  ];

  return (
    <div className="flex flex-col h-full min-h-0 animate-fade-in">
      <PageHeader
        eyebrow="Practice"
        title="Intake Command Center"
        subtitle="Qualify inquiries, act on AI insights, and convert leads into matters."
      >
        <button
          type="button"
          disabled={loading}
          onClick={() => void load()}
          className="text-sm px-3 py-2 min-h-[40px] border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        {perms?.create !== false && (
          <ButtonLink href="/intake/new" size="md">
            + New lead
          </ButtonLink>
        )}
        <ButtonLink href="/intake/board" variant="secondary" size="md">
          Kanban
        </ButtonLink>
        {perms?.analytics && (
          <ButtonLink href="/intake/analytics" variant="ghost" size="md">
            Analytics
          </ButtonLink>
        )}
      </PageHeader>

      <PageShell maxWidth="7xl" className="space-y-6 pb-10">
        {err && (
          <Alert variant="error">
            {err}
            <button
              type="button"
              className="ml-2 text-sm underline"
              onClick={() => void load()}
            >
              Retry
            </button>
          </Alert>
        )}
        {copyErr && <Alert variant="error">{copyErr}</Alert>}

        {loading && !data ? <KpiSkeleton /> : null}

        {!loading || data ? (
          <section className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
            {kpiItems.map((k) => (
              <div key={k.label} className="le-metric-card relative overflow-hidden min-h-[88px]">
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${k.accent}`} />
                <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500 m-0 leading-snug">
                  {k.label}
                </p>
                <p className="text-lg sm:text-2xl font-bold text-slate-900 m-0 mt-1 tabular-nums">
                  {k.value}
                </p>
              </div>
            ))}
          </section>
        ) : null}

        {/* Portal always visible — primary CTA for new firms */}
        {!loading && (
          <IntakePortalCard
            portal={portal}
            onCopyError={setCopyErr}
            compact={!hasLeads}
          />
        )}

        {!loading && !hasLeads ? (
          <section className="rounded-2xl border-2 border-dashed border-slate-200 bg-gradient-to-br from-slate-50 to-blue-50/40 p-6 sm:p-10 text-center">
            <h2 className="font-serif text-xl sm:text-2xl text-navy m-0">Start your intake pipeline</h2>
            <p className="text-sm text-slate-600 mt-2 max-w-lg mx-auto">
              Share the portal link above, or add a lead manually to see AI analysis and pipeline value here.
            </p>
            <ol className="text-left text-sm text-slate-700 max-w-md mx-auto mt-6 space-y-2 list-decimal list-inside">
              <li>Client submits via your public link</li>
              <li>AI classifies case type, urgency, and documents</li>
              <li>Review on this dashboard or Kanban board</li>
              <li>Convert qualified leads to matters in one click</li>
            </ol>
            <div className="flex flex-wrap justify-center gap-3 mt-8">
              {perms?.create !== false && (
                <ButtonLink href="/intake/new">Add first lead manually</ButtonLink>
              )}
              <ButtonLink href="/intake/board" variant="secondary">
                Open pipeline board
              </ButtonLink>
            </div>
          </section>
        ) : null}

        {!loading && (
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div className="xl:col-span-2 space-y-6 min-w-0">
              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <h2 className="text-sm font-semibold text-navy m-0">Urgent leads</h2>
                  <span className="text-xs text-red-700 bg-red-50 px-2 py-0.5 rounded-full">
                    Needs attention
                  </span>
                </div>
                {(data?.urgent_leads || []).length === 0 ? (
                  <p className="text-sm text-slate-500 m-0">
                    {hasLeads
                      ? "No urgent leads right now — check the pipeline board for all inquiries."
                      : "Urgent leads appear here once clients submit inquiries."}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {(data?.urgent_leads || []).map((lead) => (
                      <div
                        key={String(lead.lead_id)}
                        className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3 p-4 rounded-xl border border-slate-100 bg-slate-50/60 hover:border-blue-200 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <Link
                            href={`/intake/${lead.lead_id}`}
                            className="font-semibold text-navy hover:underline break-words"
                          >
                            {String(lead.prospect_name)}
                          </Link>
                          <p className="text-xs text-slate-600 m-0 mt-0.5">
                            {String(lead.case_type)} · Risk {String(lead.risk_score)}/100 ·{" "}
                            {String(lead.days_waiting)}d waiting
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-medium px-2 py-1 rounded-full bg-amber-100 text-amber-900 capitalize">
                            {String(lead.urgency || "high")}
                          </span>
                          {lead.contact_phone ? (
                            <a
                              href={`tel:${encodeURIComponent(String(lead.contact_phone))}`}
                              className="text-xs px-3 py-2 min-h-[36px] inline-flex items-center border rounded-lg hover:bg-white"
                            >
                              Call
                            </a>
                          ) : null}
                          {lead.contact_email ? (
                            <a
                              href={`mailto:${encodeURIComponent(String(lead.contact_email))}`}
                              className="text-xs px-3 py-2 min-h-[36px] inline-flex items-center border rounded-lg hover:bg-white"
                            >
                              Email
                            </a>
                          ) : null}
                          <Link
                            href={`/intake/${lead.lead_id}`}
                            className="text-xs px-3 py-2 min-h-[36px] inline-flex items-center bg-navy text-white rounded-lg"
                          >
                            Open
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0 mb-4">Recent activity</h2>
                {(data?.recent_activity || []).length === 0 ? (
                  <p className="text-sm text-slate-500 m-0">Activity appears when leads are created or updated.</p>
                ) : (
                  <ul className="space-y-2 m-0 p-0 list-none">
                    {(data?.recent_activity || []).slice(0, 12).map((ev, i) => (
                      <li
                        key={`${String(ev.lead_id)}-${String(ev.created_at)}-${i}`}
                        className="flex flex-col xs:flex-row xs:items-start gap-1 sm:gap-3 text-sm py-2 border-b border-slate-50 last:border-0"
                      >
                        <div className="flex gap-2 flex-1 min-w-0">
                          <span className="text-emerald-600 shrink-0">✓</span>
                          <div className="min-w-0 flex-1">
                            <p className="m-0 text-slate-800 break-words">
                              <span className="font-medium">{String(ev.label)}</span>
                              {ev.prospect_name && ev.lead_id ? (
                                <>
                                  {" — "}
                                  <Link
                                    href={`/intake/${ev.lead_id}`}
                                    className="text-blue-700 hover:underline"
                                  >
                                    {String(ev.prospect_name)}
                                  </Link>
                                </>
                              ) : null}
                            </p>
                            {ev.detail ? (
                              <p className="text-xs text-slate-500 m-0 truncate">{String(ev.detail)}</p>
                            ) : null}
                          </div>
                        </div>
                        <span className="text-xs text-slate-400 shrink-0 pl-6 xs:pl-0">
                          {timeAgo(String(ev.created_at))}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm overflow-hidden">
                <div className="flex items-center justify-between mb-4 gap-2">
                  <h2 className="text-sm font-semibold text-navy m-0">Pipeline board</h2>
                  <Link href="/intake/board" className="text-xs text-blue-700 hover:underline shrink-0">
                    Full Kanban →
                  </Link>
                </div>
                <div className="flex gap-3 overflow-x-auto pb-2 le-scroll touch-scroll-x snap-x-child -mx-1 px-1">
                  {(data?.kanban_preview?.stages || [])
                    .filter((s) => !["REJECTED", "CLOSED"].includes(s))
                    .map((stage) => {
                      const count = data?.kanban_preview?.columns?.[stage] ?? 0;
                      const samples = data?.kanban_preview?.samples?.[stage] || [];
                      return (
                        <div
                          key={stage}
                          className="min-w-[min(85vw,220px)] max-w-[240px] flex-shrink-0 snap-start rounded-xl border border-slate-200 bg-slate-50/80 p-3"
                        >
                          <div className="flex justify-between items-center gap-2 mb-2">
                            <p className="text-xs font-bold uppercase text-slate-700 m-0 truncate">
                              {labels[stage] || stage}
                            </p>
                            <span className="text-xs bg-white border px-2 rounded-full shrink-0">{count}</span>
                          </div>
                          <div className="space-y-2">
                            {samples.map((card) => (
                              <Link
                                key={String(card.lead_id)}
                                href={`/intake/${card.lead_id}`}
                                className="block p-2 rounded-lg bg-white border border-slate-100 text-xs hover:border-blue-300"
                              >
                                <p className="font-medium text-slate-900 m-0 truncate">
                                  {String(card.prospect_name)}
                                </p>
                                <p className="text-slate-500 m-0 mt-0.5 truncate">
                                  {String(card.case_type)} · {String(card.lead_score ?? 0)}
                                </p>
                              </Link>
                            ))}
                            {!samples.length && (
                              <p className="text-[0.65rem] text-slate-400 m-0 py-2 text-center">Empty</p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </section>
            </div>

            <div className="space-y-6 min-w-0">
              <section className="le-card rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 to-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0">Latest AI analysis</h2>
                {data?.latest_ai ? (
                  <div className="mt-3 space-y-2 text-sm">
                    <p className="m-0 break-words">
                      <span className="text-slate-500">Client:</span>{" "}
                      <Link
                        href={`/intake/${data.latest_ai.lead_id}`}
                        className="font-medium text-blue-700 hover:underline"
                      >
                        {String(data.latest_ai.prospect_name)}
                      </Link>
                    </p>
                    <p className="m-0">
                      <span className="text-slate-500">Case type:</span> {String(data.latest_ai.case_type)}
                    </p>
                    <p className="m-0 capitalize">
                      <span className="text-slate-500">Urgency:</span>{" "}
                      <span className="font-medium text-amber-800">{String(data.latest_ai.urgency)}</span>
                    </p>
                    {Array.isArray(data.latest_ai.sections) && data.latest_ai.sections.length > 0 ? (
                      <p className="m-0 text-xs text-slate-600 break-words">
                        Sections: {(data.latest_ai.sections as string[]).join(", ")}
                      </p>
                    ) : null}
                    <p className="m-0">
                      <span className="text-slate-500">Risk score:</span> {String(data.latest_ai.risk_score)}/100
                    </p>
                    <p className="text-xs text-slate-700 bg-white/80 rounded-lg p-2 border m-0 break-words">
                      {String(data.latest_ai.recommended_action)}
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 mt-2 m-0">
                    {hasLeads
                      ? "Open a lead and run AI analysis to see insights here."
                      : "AI analysis appears after your first intake submission."}
                  </p>
                )}
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0 mb-3">AI recommendations</h2>
                <ul className="space-y-3 m-0 p-0 list-none">
                  {(data?.ai_recommendations || []).map((rec, i) => (
                    <li key={`rec-${i}`} className="text-sm border-l-2 border-indigo-400 pl-3">
                      <p className="font-medium text-slate-900 m-0">{rec.title}</p>
                      <p className="text-xs text-slate-600 m-0 mt-0.5 break-words">{rec.body}</p>
                      {rec.lead_id ? (
                        <Link href={`/intake/${rec.lead_id}`} className="text-xs text-blue-700 hover:underline">
                          View lead →
                        </Link>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0 mb-3">Follow-up center</h2>
                {(data?.follow_ups?.overdue_count ?? 0) > 0 && (
                  <p className="text-xs text-red-700 bg-red-50 rounded-lg px-2 py-1 mb-2 m-0">
                    Overdue: {data?.follow_ups?.overdue_count}
                  </p>
                )}
                <p className="text-xs font-semibold text-slate-500 uppercase m-0 mb-1">Due today</p>
                {(data?.follow_ups?.due_today || []).length === 0 ? (
                  <p className="text-xs text-slate-400 m-0 mb-3">None scheduled</p>
                ) : (
                  <ul className="text-sm space-y-1 mb-3 m-0 p-0 list-none">
                    {(data?.follow_ups?.due_today || []).map((f, i) => (
                      <li key={`today-${i}`}>
                        <Link href={`/intake/${f.lead_id}`} className="text-blue-700 hover:underline">
                          {String(f.prospect_name)}
                        </Link>
                        <span className="text-slate-500"> — {String(f.due_label)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-xs font-semibold text-slate-500 uppercase m-0 mb-1">Overdue</p>
                <ul className="text-sm space-y-1 m-0 p-0 list-none">
                  {(data?.follow_ups?.overdue || []).slice(0, 5).map((f, i) => (
                    <li key={`od-${i}`} className="text-red-800">
                      <Link href={`/intake/${f.lead_id}`} className="hover:underline">
                        {String(f.prospect_name)}
                      </Link>
                    </li>
                  ))}
                  {!(data?.follow_ups?.overdue || []).length && (
                    <li className="text-xs text-slate-400 list-none">None</li>
                  )}
                </ul>
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0">Pipeline value</h2>
                <p className="text-2xl font-bold text-navy m-0 mt-2 tabular-nums">
                  {formatInr(data?.pipeline_value?.total_inr ?? 0)}
                </p>
                <p className="text-xs text-slate-500 m-0">Estimated from stage averages (INR)</p>
                <ul className="mt-3 space-y-2 m-0 p-0 list-none text-sm">
                  {(data?.pipeline_value?.by_stage || []).map((row) => (
                    <li key={row.stage} className="flex justify-between gap-2">
                      <span className="text-slate-700 truncate">{row.label}</span>
                      <span className="text-slate-900 font-medium shrink-0 tabular-nums">
                        {formatInr(row.value_inr)} ({row.count})
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">
                <h2 className="text-sm font-semibold text-navy m-0 mb-3">Lead sources</h2>
                {(data?.lead_sources || []).length === 0 ? (
                  <p className="text-xs text-slate-500 m-0">
                    Set referral source when creating leads or on the client form.
                  </p>
                ) : (
                  <ul className="space-y-2 m-0 p-0 list-none text-sm">
                    {(data?.lead_sources || []).map((s) => (
                      <li key={s.source} className="flex justify-between gap-2">
                        <span className="text-slate-700 truncate">{s.source}</span>
                        <span className="font-semibold tabular-nums shrink-0">{s.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </div>
        )}
      </PageShell>
    </div>
  );
}
