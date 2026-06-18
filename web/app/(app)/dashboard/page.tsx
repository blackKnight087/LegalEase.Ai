"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AnalyticsPieChart, { type PieSlice } from "@/components/analytics/AnalyticsPieChart";
import PracticeModuleCards from "@/components/dashboard/PracticeModuleCards";
import QuickActionGrid, { type QuickAction } from "@/components/dashboard/QuickActionGrid";
import RecentActivityPanel from "@/components/dashboard/RecentActivityPanel";
import StatCard from "@/components/dashboard/StatCard";
import HearingDigestPanel from "@/components/dashboard/HearingDigestPanel";
import EvidenceAlertsPanel from "@/components/dashboard/EvidenceAlertsPanel";
import SystemHealthStrip from "@/components/dashboard/SystemHealthStrip";
import MobileCollapsible from "@/components/layout/MobileCollapsible";
import UsageLimitsCard from "@/components/saas/UsageLimitsCard";
import { useApiConnection } from "@/components/providers/ApiConnectionProvider";
import { useAuth } from "@/components/providers/AuthProvider";
import PageHeader from "@/components/ui/PageHeader";
import PageShell from "@/components/ui/PageShell";
import Alert from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { ButtonLink } from "@/components/ui/Button";
import { useLearnerMode } from "@/hooks/useLearnerMode";
import { dashboardFull, type DashboardFull } from "@/lib/api";

const PIPELINE_COLORS = [
  "#1e3a5f",
  "#2563eb",
  "#059669",
  "#7c3aed",
  "#d97706",
  "#dc2626",
  "#0891b2",
];

const QUICK_ACTIONS: QuickAction[] = [
  {
    href: "/",
    title: "AI Assistant",
    description: "Research, draft, and query your knowledge base",
    icon: "💬",
    accent: "bg-blue-50 text-blue-700",
  },
  {
    href: "/documents",
    title: "Documents",
    description: "Upload PDFs and manage your firm library",
    icon: "📂",
    accent: "bg-slate-100 text-slate-700",
  },
  {
    href: "/matters",
    title: "Matters",
    description: "Timeline, hearings, tasks, and deadlines",
    icon: "📁",
    accent: "bg-indigo-50 text-indigo-700",
  },
  {
    href: "/litigation",
    title: "Litigation Desk",
    description: "Cause lists, hearings, firm-wide contradictions",
    icon: "⚖️",
    accent: "bg-sky-50 text-sky-800",
    lawyerOnly: true,
  },
  {
    href: "/billing",
    title: "Billing",
    description: "Time entries, narratives, and invoices",
    icon: "💰",
    accent: "bg-amber-50 text-amber-800",
  },
  {
    href: "/intake",
    title: "Intake CRM",
    description: "Leads, pipeline stages, and follow-ups",
    icon: "📥",
    accent: "bg-emerald-50 text-emerald-700",
  },
  {
    href: "/drafting",
    title: "Drafting Studio",
    description: "Templates, clauses, and document assembly",
    icon: "📝",
    accent: "bg-violet-50 text-violet-700",
  },
];

function greetingForHour(h: number) {
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { learnerMode } = useLearnerMode();
  const { apiOnline, llmOnline } = useApiConnection();
  const [data, setData] = useState<DashboardFull | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    setErr("");
    try {
      const d = await dashboardFull();
      setData(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const greeting = useMemo(() => {
    const name = user?.username || data?.username || "Counsel";
    return `${greetingForHour(new Date().getHours())}, ${name}`;
  }, [user?.username, data?.username]);

  const pipelineSlices = useMemo((): PieSlice[] => {
    const stages = data?.practice?.crm?.pipeline_stages || {};
    return Object.entries(stages)
      .filter(([, n]) => n > 0)
      .map(([label, value], i) => ({
        label: label.replace(/_/g, " "),
        value,
        color: PIPELINE_COLORS[i % PIPELINE_COLORS.length],
      }));
  }, [data]);

  const feedbackSlices = useMemo((): PieSlice[] => {
    const pos = data?.learning?.total_positive ?? 0;
    const neg = data?.learning?.total_negative ?? 0;
    if (pos + neg === 0) return [];
    return [
      { label: "Positive", value: pos, color: "#059669" },
      { label: "Negative", value: neg, color: "#dc2626" },
    ];
  }, [data]);

  const quickActions = useMemo(() => {
    return QUICK_ACTIONS.filter(
      (a) => !("lawyerOnly" in a && a.lawyerOnly) || !learnerMode
    );
  }, [learnerMode]);

  const kbLabel =
    data?.kb_status === "ready"
      ? "Indexed"
      : (data?.kb_status || "empty").replace(/_/g, " ");

  const healthPills = [
    {
      label: "API",
      ok: apiOnline,
      detail: apiOnline ? "Connected" : "Offline",
    },
    {
      label: "LLM",
      ok: llmOnline || !!data?.llm_online,
      detail: llmOnline || data?.llm_online ? "Ready" : "Starting",
    },
    {
      label: "Knowledge base",
      ok: (data?.kb_chunks ?? 0) > 0 || data?.kb_status === "ready",
      detail: `${data?.kb_chunks ?? 0} chunks · ${kbLabel}`,
    },
    {
      label: "Embeddings",
      ok: !!data?.embedding?.ready,
      detail: data?.embedding?.ready
        ? data?.embedding?.device || "ready"
        : data?.embedding?.state || "loading",
    },
  ];

  const invoiced = data?.practice?.billing?.invoiced_total_inr ?? 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Command center"
        title={greeting}
        subtitle="Research, documents, matters, billing, and intake."
      >
        <Button variant="secondary" size="md" onClick={() => load(true)} disabled={refreshing} loading={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
        <ButtonLink href="/" size="md">
          New chat
        </ButtonLink>
      </PageHeader>

      <PageShell maxWidth="7xl">
          {err && <Alert variant="error">{err}</Alert>}

          <MobileCollapsible title="System status & plan usage">
            <SystemHealthStrip pills={healthPills} compact />
            <UsageLimitsCard
              compact
              documentCount={
                typeof data?.documents === "number" ? data.documents : 0
              }
            />
          </MobileCollapsible>

          <div className="hidden lg:block space-y-6">
            <SystemHealthStrip pills={healthPills} />
            <UsageLimitsCard
              compact
              documentCount={
                typeof data?.documents === "number" ? data.documents : 0
              }
            />
          </div>

          <HearingDigestPanel />

          <EvidenceAlertsPanel />

          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
              Workspace overview
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Documents"
                value={data?.documents ?? "—"}
                sublabel={`${data?.kb_documents ?? 0} in knowledge base`}
                icon="📄"
                href="/documents"
                accent="navy"
                loading={loading}
              />
              <StatCard
                label="AI queries"
                value={data?.queries ?? "—"}
                sublabel={
                  data?.learning?.total_turns
                    ? `${data.learning.total_turns} tracked turns`
                    : "All-time conversations"
                }
                icon="⚡"
                href="/analytics"
                accent="blue"
                loading={loading}
              />
              <StatCard
                label="KB chunks"
                value={data?.kb_chunks ?? "—"}
                sublabel={kbLabel}
                icon="🧠"
                href="/documents"
                accent="violet"
                loading={loading}
              />
              <StatCard
                label="Invoiced"
                value={
                  loading
                    ? "—"
                    : `₹${invoiced.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`
                }
                sublabel="Practice billing total"
                icon="📊"
                href="/billing"
                accent="emerald"
                loading={loading}
              />
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 m-0">
                Practice suite
              </h2>
              <Link href="/matters" className="text-xs text-blue-600 hover:underline">
                Open matters →
              </Link>
            </div>
            {loading ? (
              <div className="grid sm:grid-cols-2 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-24 rounded-xl bg-slate-100 animate-pulse" />
                ))}
              </div>
            ) : (
              <PracticeModuleCards practice={data?.practice || {}} />
            )}
          </section>

          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className="grid md:grid-cols-2 gap-4">
                <AnalyticsPieChart
                  title="CRM pipeline"
                  slices={pipelineSlices}
                  emptyMessage="No leads in pipeline yet — add leads in Intake CRM"
                />
                <AnalyticsPieChart
                  title="User feedback"
                  slices={feedbackSlices}
                  emptyMessage="No feedback yet — rate answers in chat to train the system"
                />
              </div>

              {loading ? (
                <div className="h-48 rounded-2xl bg-slate-100 animate-pulse" />
              ) : (
                <RecentActivityPanel
                  chats={data?.recent_queries || []}
                  documents={data?.recent_documents || []}
                />
              )}

              {data?.learning && (data.learning.feedback_count ?? 0) > 0 && (
                <div className="border rounded-2xl bg-gradient-to-r from-slate-50 to-white p-5 flex flex-wrap gap-6 items-center">
                  <div>
                    <p className="text-xs text-slate-500 m-0">Learning accuracy</p>
                    <p className="text-2xl font-bold text-navy m-0">
                      {data.learning.accuracy_pct != null
                        ? `${data.learning.accuracy_pct}%`
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 m-0">Avg hit rate</p>
                    <p className="text-2xl font-bold text-emerald-700 m-0">
                      {data.learning.avg_hit_rate_pct != null
                        ? `${data.learning.avg_hit_rate_pct}%`
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 m-0">Feedback signals</p>
                    <p className="text-2xl font-bold text-navy m-0">
                      {data.learning.feedback_count}
                    </p>
                  </div>
                  <Link
                    href="/analytics"
                    className="ml-auto text-sm text-blue-600 hover:underline"
                  >
                    Full analytics →
                  </Link>
                </div>
              )}
            </div>

            <div className="space-y-6">
              <div className="le-card le-card-hover border rounded-2xl bg-white p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-navy m-0">Quick actions</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Jump to the tools you use most
                </p>
                <QuickActionGrid actions={quickActions} />
              </div>

              <div className="le-card le-card-hover border rounded-2xl bg-white p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-navy m-0">Modules</h3>
                <ul className="mt-3 space-y-2 m-0 p-0 list-none text-sm">
                  {(
                    [
                      ["Matters & workflow", "/matters", true],
                      ["Billing & invoices", "/billing", true],
                      ["Intake CRM", "/intake", true],
                      ["Evidence Intelligence", "/discovery", true],
                      ["Legal tools", "/tools", true],
                    ] as const
                  ).map(([label, href, ready]) => (
                    <li key={href}>
                      <Link
                        href={href}
                        className="flex items-center justify-between py-1.5 hover:text-blue-600 no-underline text-slate-700"
                      >
                        <span>{label}</span>
                        <span
                          className={`text-[0.62rem] px-2 py-0.5 rounded-full ${
                            ready
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {ready ? "Active" : "Soon"}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>

              {!loading && (data?.documents ?? 0) === 0 && (
                <div className="rounded-2xl border border-dashed border-blue-200 bg-blue-50/50 p-5">
                  <p className="text-sm font-semibold text-navy m-0">Get started</p>
                  <p className="text-xs text-slate-600 mt-2 mb-3 leading-relaxed">
                    Upload your first case PDFs, then ask questions in Knowledge Base mode for
                    grounded answers with citations.
                  </p>
                  <Link
                    href="/documents"
                    className="inline-block text-sm font-medium text-blue-700 hover:underline"
                  >
                    Upload documents →
                  </Link>
                </div>
              )}
            </div>
          </div>
      </PageShell>
    </div>
  );
}
