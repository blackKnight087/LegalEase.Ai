"use client";

import { useEffect, useMemo, useState } from "react";
import type { CrmCommandCenter } from "@/lib/api";
import * as api from "@/lib/api";
import CrmActionBanner from "./CrmActionBanner";
import {
  logOutboundCall,
  logOutboundEmail,
  logWhatsApp,
  requestDocuments,
  scheduleConsultation,
} from "./crmLeadActions";
import { formatApiError } from "./crmUtils";
import CrmKanbanEmptyColumn from "./CrmKanbanEmptyColumn";
import CrmKanbanIntelligencePanel from "./CrmKanbanIntelligencePanel";
import CrmLeadCard from "./CrmLeadCard";
import CrmLeadDrawer from "./CrmLeadDrawer";
import CrmScheduleModal from "./CrmScheduleModal";

type KanbanMetrics = {
  total_leads?: number;
  pipeline_value_inr?: number;
  conversion_rate?: number;
  consultations_scheduled?: number;
  matters_created?: number;
  revenue_forecast_inr?: number;
};

type Props = {
  columns: Record<string, Array<Record<string, unknown>>>;
  stages: string[];
  stageLabels: Record<string, string>;
  emptyHints?: Record<string, string>;
  metrics?: KanbanMetrics;
  commandCenter?: CrmCommandCenter | null;
  canEdit: boolean;
  onMoved?: () => void;
};

export default function CrmKanbanBoard({
  columns,
  stages,
  stageLabels,
  emptyHints = {},
  metrics = {},
  commandCenter = null,
  canEdit,
  onMoved,
}: Props) {
  const [dragId, setDragId] = useState("");
  const [dragHover, setDragHover] = useState("");
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<{
    leadId: string;
    name: string;
    stage: string;
  } | null>(null);
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [pinnedEmpty, setPinnedEmpty] = useState<Set<string>>(new Set());

  const totalLeads = useMemo(
    () => stages.reduce((n, s) => n + (columns[s]?.length ?? 0), 0),
    [columns, stages]
  );

  const { activeStages, collapsedStages, visibleStages } = useMemo(() => {
    const active: string[] = [];
    const collapsed: string[] = [];
    for (const stage of stages) {
      const count = columns[stage]?.length ?? 0;
      if (count > 0) active.push(stage);
      else collapsed.push(stage);
    }
    const visible = [
      ...active,
      ...collapsed.filter((s) => pinnedEmpty.has(s)),
    ];
    return { activeStages: active, collapsedStages: collapsed, visibleStages: visible };
  }, [stages, columns, pinnedEmpty]);

  useEffect(() => {
    if (totalLeads === 0) {
      setPinnedEmpty((prev) => {
        if (prev.has("NEW_INQUIRY")) return prev;
        return new Set(["NEW_INQUIRY"]);
      });
    }
  }, [totalLeads]);

  useEffect(() => {
    setPinnedEmpty((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const stage of stages) {
        if ((columns[stage]?.length ?? 0) > 0 && next.has(stage)) {
          next.delete(stage);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [columns, stages]);

  const togglePin = (stage: string) => {
    setPinnedEmpty((prev) => {
      const next = new Set(prev);
      if (next.has(stage)) next.delete(stage);
      else next.add(stage);
      return next;
    });
  };

  const onDrop = async (stage: string) => {
    if (!canEdit || !dragId) return;
    setBusy(true);
    setErr("");
    setDragHover("");
    try {
      await api.patchCrmLeadStage(dragId, stage);
      onMoved?.();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
      setDragId("");
    }
  };

  const flash = (result: { ok: boolean; message: string }, openDrawerId?: string) => {
    if (result.ok) {
      setSuccess(result.message);
      setErr("");
      onMoved?.();
      if (openDrawerId) setDrawerId(openDrawerId);
    } else {
      setErr(result.message);
      setSuccess("");
    }
  };

  const confirmSchedule = async (scheduledAt: string, note: string) => {
    if (!scheduleTarget) return;
    if (!canEdit) {
      setErr("You do not have permission to edit leads.");
      return;
    }
    setScheduleBusy(true);
    const result = await scheduleConsultation(scheduleTarget.leadId, {
      scheduledAt,
      note,
      currentStage: scheduleTarget.stage,
    });
    setScheduleBusy(false);
    if (result.ok) {
      setScheduleTarget(null);
      flash(result, scheduleTarget.leadId);
    } else {
      setErr(result.message);
    }
  };

  const cardActions = {
    onOpenSchedule: (leadId: string, lead: Record<string, unknown>) => {
      if (!canEdit) {
        setErr("You do not have permission to edit leads.");
        return;
      }
      setScheduleTarget({
        leadId,
        name: String(lead.prospect_name || "Lead"),
        stage: String(lead.pipeline_stage || ""),
      });
    },
    onRequestDocuments: async (leadId: string) => {
      if (!canEdit) {
        setErr("You do not have permission to edit leads.");
        return;
      }
      const result = await requestDocuments(leadId);
      flash(result, leadId);
    },
    onLogCall: (leadId: string, phone: string) => {
      void logOutboundCall(leadId, phone).then((result) => {
        if (result.ok) flash(result);
        else setErr(result.message);
      });
    },
    onLogEmail: (leadId: string, email: string) => {
      void logOutboundEmail(leadId, email).then((result) => {
        if (result.ok) flash(result);
        else setErr(result.message);
      });
    },
    onLogWhatsApp: (leadId: string, phone: string) => {
      void logWhatsApp(leadId, phone).then((result) => {
        if (result.ok) flash(result);
        else setErr(result.message);
      });
    },
  };

  const chipDropProps = (stage: string) => ({
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      setDragHover(stage);
    },
    onDragLeave: () => setDragHover((h) => (h === stage ? "" : h)),
    onDrop: () => onDrop(stage),
  });

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-0">
      <div className="flex-1 min-w-0 flex flex-col">
        <CrmActionBanner message={success} variant="success" onDismiss={() => setSuccess("")} />
        <CrmActionBanner message={err} variant="error" onDismiss={() => setErr("")} />

        {collapsedStages.length > 0 && (
          <div
            className={`mb-3 rounded-xl border px-3 py-2.5 transition-colors duration-200 ${
              dragId ? "border-blue-200 bg-blue-50/50" : "border-slate-200 bg-slate-50/80"
            }`}
          >
            <p className="text-[0.65rem] font-bold uppercase text-slate-500 mb-2">
              {dragId ? "Drop on a stage to move lead" : "Hidden stages"}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {collapsedStages.map((stage) => {
                const isPinned = pinnedEmpty.has(stage);
                const isHover = dragHover === stage;
                return (
                  <button
                    key={stage}
                    type="button"
                    title={isPinned ? "Collapse column" : "Expand column"}
                    onClick={() => togglePin(stage)}
                    className={`text-[0.65rem] font-semibold px-2.5 py-1 rounded-full border transition-all duration-200 ${
                      isHover
                        ? "bg-blue-600 text-white border-blue-600 scale-105 shadow-md"
                        : isPinned
                          ? "bg-white text-navy border-navy shadow-sm"
                          : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                    }`}
                    {...chipDropProps(stage)}
                  >
                    {stageLabels[stage] || stage} (0)
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4 pb-4 w-full min-w-0">
          {visibleStages.length === 0 ? (
            <section className="kanban-column-enter w-full rounded-2xl border border-slate-200/90 bg-slate-50/70 shadow-sm p-3">
              <div className="kanban-stage-grid">
                <div className="kanban-stage-empty">
                  <CrmKanbanEmptyColumn
                    stage="NEW_INQUIRY"
                    stageLabel={stageLabels.NEW_INQUIRY || "New inquiry"}
                    hint={emptyHints.NEW_INQUIRY}
                  />
                </div>
              </div>
            </section>
          ) : (
            visibleStages.map((stage) => {
              const cards = columns[stage] || [];
              const isEmpty = cards.length === 0;
              return (
                <section
                  key={stage}
                  className={`kanban-column-enter w-full flex flex-col rounded-2xl border border-slate-200/90 bg-slate-50/70 shadow-sm transition-all duration-200 ${
                    dragHover === stage ? "ring-2 ring-blue-400 shadow-md border-blue-200" : ""
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragHover(stage);
                  }}
                  onDragLeave={() => setDragHover((h) => (h === stage ? "" : h))}
                  onDrop={() => onDrop(stage)}
                >
                  <div className="flex justify-between items-center gap-3 px-4 py-3 border-b border-slate-200/60 bg-white/80 rounded-t-2xl">
                    <h3 className="text-xs font-bold uppercase tracking-wide text-slate-800">
                      {stageLabels[stage] || stage}
                    </h3>
                    <span className="text-xs font-bold bg-navy text-white min-w-[1.5rem] text-center px-2 py-0.5 rounded-full shrink-0">
                      {cards.length}
                    </span>
                  </div>
                  <div className="p-3 sm:p-4 min-h-[4rem]">
                    <div className="kanban-stage-grid">
                      {isEmpty ? (
                        <div className="kanban-stage-empty">
                          <CrmKanbanEmptyColumn
                            stage={stage}
                            stageLabel={stageLabels[stage] || stage}
                            hint={emptyHints[stage]}
                            compact={activeStages.length > 0}
                          />
                        </div>
                      ) : (
                        cards.map((lead) => (
                          <div key={String(lead.lead_id)} className="kanban-stage-card">
                            <CrmLeadCard
                              lead={lead}
                              canEdit={canEdit}
                              draggable={canEdit && !busy}
                              actions={cardActions}
                              onDragStart={() => setDragId(String(lead.lead_id))}
                              onDragEnd={() => {
                                setDragId("");
                                setDragHover("");
                              }}
                              onOpen={setDrawerId}
                            />
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </section>
              );
            })
          )}
        </div>
      </div>

      <CrmKanbanIntelligencePanel
        columns={columns}
        metrics={metrics}
        commandCenter={commandCenter}
        onOpenLead={setDrawerId}
      />

      <CrmLeadDrawer
        leadId={drawerId}
        stageLabels={stageLabels}
        canEdit={canEdit}
        onClose={() => setDrawerId(null)}
        onUpdated={onMoved}
        onScheduleLead={(id, lead) => {
          setDrawerId(null);
          cardActions.onOpenSchedule(id, lead);
        }}
        onActionMessage={(message, variant) => {
          if (variant === "success") {
            setSuccess(message);
            setErr("");
          } else {
            setErr(message);
            setSuccess("");
          }
        }}
      />

      <CrmScheduleModal
        open={!!scheduleTarget}
        leadName={scheduleTarget?.name || ""}
        busy={scheduleBusy}
        onClose={() => !scheduleBusy && setScheduleTarget(null)}
        onConfirm={(at, note) => void confirmSchedule(at, note)}
      />
    </div>
  );
}
