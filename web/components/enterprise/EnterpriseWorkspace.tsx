"use client";

import { useCallback, useEffect, useState } from "react";
import EnterpriseCommandHeader from "@/components/enterprise/EnterpriseCommandHeader";
import * as api from "@/lib/api";
import {
  ENTERPRISE_NAV,
  type CommandCenterData,
  type DashboardMetrics,
  type EnterpriseModule,
  type NotificationItem,
} from "@/lib/enterpriseWorkspace";
import {
  AgentsModule,
  AnalyticsModule,
  AutomationModule,
  ClientPortalModule,
  ComplianceModule,
  CourtOrdersModule,
  DashboardModule,
  DocumentCenterModule,
  KnowledgeModule,
  MatterHubModule,
  StorageModule,
} from "./EnterpriseModules";

const DEFAULT_METRICS: DashboardMetrics = {
  total_documents: 0,
  total_orders: 0,
  pending_reviews: 0,
  upcoming_deadlines: 0,
  client_requests: 0,
  storage_mb: 0,
  ocr_queue: 0,
  ai_processing_queue: 0,
  knowledge_base_size: 0,
  open_matters: 0,
  closed_matters: 0,
};

const EMPTY_COMMAND: CommandCenterData = {
  metrics: DEFAULT_METRICS,
  activity_feed: [],
  priorities_today: [],
  action_queues: {},
  notifications: [],
  is_empty: true,
};

export default function EnterpriseWorkspace() {
  const [module, setModule] = useState<EnterpriseModule>("dashboard");
  const [command, setCommand] = useState<CommandCenterData>(EMPTY_COMMAND);
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [selectedMatter, setSelectedMatter] = useState("");
  const [hubMatterId, setHubMatterId] = useState("");
  const [causeText, setCauseText] = useState("");
  const [agentResult, setAgentResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const refreshDashboard = useCallback(() => {
    api
      .fetchEnterpriseDashboard()
      .then((d) => {
        setCommand({
          metrics: { ...DEFAULT_METRICS, ...(d.metrics as DashboardMetrics) },
          kpi_strip: d.kpi_strip,
          snapshot: d.snapshot,
          action_queues: d.action_queues,
          activity_feed: (d.activity_feed || []) as CommandCenterData["activity_feed"],
          priorities_today: (d.priorities_today || []) as CommandCenterData["priorities_today"],
          agents: (d.agents || []) as CommandCenterData["agents"],
          notifications: (d.notifications || []) as NotificationItem[],
          is_empty: Boolean(d.is_empty),
          analytics: d.analytics,
          permission_roles: d.permission_roles as CommandCenterData["permission_roles"],
        });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshDashboard();
    api.listMatters().then((r) => setMatters(r.matters || [])).catch(() => {});
  }, [refreshDashboard]);

  const [fallbackAgents, setFallbackAgents] = useState<CommandCenterData["agents"]>([]);
  useEffect(() => {
    if (!command.agents?.length) {
      api.fetchEnterpriseAgents().then((r) =>
        setFallbackAgents(
          (r.agents || []).map((a) => ({
            ...a,
            status: "idle" as const,
            mode: "autonomous",
            schedule: "On demand",
          }))
        )
      );
    }
  }, [command.agents?.length]);

  const agents = command.agents?.length ? command.agents : fallbackAgents || [];

  const runAgent = async (agentId: string) => {
    setBusy(true);
    setErr("");
    setAgentResult(null);
    try {
      const payload =
        agentId === "matter_agent" || agentId === "drafting_agent"
          ? { matter_id: selectedMatter }
          : agentId === "order_analysis_agent"
            ? { matter_id: selectedMatter }
            : agentId === "knowledge_agent"
              ? { query: "bail orders Delhi High Court" }
              : {};
      const r = await api.runEnterpriseAgent(agentId, payload);
      setAgentResult(r);
      refreshDashboard();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Agent failed");
    } finally {
      setBusy(false);
    }
  };

  const syncCause = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.syncCourtCauseList({ source: "paste", text: causeText, auto_schedule: true });
      refreshDashboard();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  };

  const isDashboard = module === "dashboard";

  return (
    <div className="enterprise-v2 legal-tools-v2 flex flex-col h-full min-h-0">
      <EnterpriseCommandHeader
        notifications={command.notifications || []}
        onNavigate={setModule}
        onSelectMatter={(id) => {
          setHubMatterId(id);
          setModule("matters");
        }}
      />
      <div className="legal-tools-v2__shell flex-1 min-h-0">
        <aside className="legal-tools-v2__sidebar">
          <div className="px-4 py-4 border-b border-slate-100">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 m-0">Firm OS</p>
            <p className="text-sm font-semibold text-navy m-0 mt-1">Enterprise</p>
          </div>
          <nav className="legal-tools-v2__sidebar-nav">
            {ENTERPRISE_NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setModule(item.id)}
                className={`legal-tools-v2__nav-btn ${module === item.id ? "is-active" : ""}`}
              >
                <span className="mr-2">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="legal-tools-v2__main">
          {!isDashboard && (
            <div className="legal-tools-v2__search-bar flex items-center justify-between gap-4 shrink-0">
              <p className="font-semibold text-navy m-0 text-sm">
                {ENTERPRISE_NAV.find((n) => n.id === module)?.label}
              </p>
            </div>
          )}
          <div className={`legal-tools-v2__body flex-1 min-h-0 ${isDashboard ? "ent-dashboard-body" : ""}`}>
            <div
              className={`legal-tools-v2__center w-full h-full ${
                isDashboard ? "max-w-none px-4 md:px-6 py-4" : "max-w-5xl mx-auto p-4 md:p-6"
              }`}
            >
              {module === "dashboard" && <DashboardModule data={command} onNavigate={setModule} />}
              {module === "matters" && (
                <MatterHubModule matters={matters} initialMatterId={hubMatterId || selectedMatter} />
              )}
              {module === "client-portal" && <ClientPortalModule matters={matters} />}
              {module === "documents" && <DocumentCenterModule matters={matters} />}
              {module === "court-orders" && <CourtOrdersModule matters={matters} />}
              {module === "knowledge" && <KnowledgeModule />}
              {module === "agents" && (
                <AgentsModule
                  agents={agents}
                  matters={matters}
                  selectedMatter={selectedMatter}
                  onMatterChange={setSelectedMatter}
                  onRun={runAgent}
                  onRunAll={() => runAgent("compliance_agent")}
                  busy={busy}
                  result={agentResult}
                  err={err}
                />
              )}
              {module === "automation" && (
                <AutomationModule causeText={causeText} onCauseChange={setCauseText} onSync={syncCause} busy={busy} />
              )}
              {module === "compliance" && <ComplianceModule matters={matters} />}
              {module === "analytics" && <AnalyticsModule data={command.analytics} />}
              {module === "storage" && <StorageModule />}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
