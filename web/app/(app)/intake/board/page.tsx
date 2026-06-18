"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import CrmKanbanBoard from "@/components/crm/CrmKanbanBoard";
import CrmKanbanMetrics from "@/components/crm/CrmKanbanMetrics";
import { formatApiError } from "@/components/crm/crmUtils";
import * as api from "@/lib/api";

type KanbanMetrics = {
  total_leads?: number;
  pipeline_value_inr?: number;
  conversion_rate?: number;
  consultations_scheduled?: number;
  matters_created?: number;
  revenue_forecast_inr?: number;
};

export default function IntakeBoardPage() {
  const [columns, setColumns] = useState<Record<string, Array<Record<string, unknown>>>>({});
  const [stages, setStages] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [emptyHints, setEmptyHints] = useState<Record<string, string>>({});
  const [metrics, setMetrics] = useState<KanbanMetrics>({});
  const [commandCenter, setCommandCenter] = useState<api.CrmCommandCenter | null>(null);
  const [canEdit, setCanEdit] = useState(true);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kanban, stageMeta, perms, cc] = await Promise.all([
        api.fetchCrmKanban(),
        api.fetchCrmPipelineStages(),
        api.fetchCrmPermissions(),
        api.fetchCrmCommandCenter().catch(() => null),
      ]);
      setColumns(kanban.columns || {});
      setStages(kanban.stages || stageMeta.stages || []);
      setLabels(stageMeta.labels || {});
      setEmptyHints(
        (kanban.empty_hints as Record<string, string>) ||
          (stageMeta.empty_hints as Record<string, string>) ||
          {}
      );
      setMetrics((kanban.metrics as KanbanMetrics) || {});
      setCommandCenter(cc);
      setCanEdit(!!perms.edit);
      setErr("");
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const displayMetrics = useMemo(() => {
    const all = Object.values(columns).flat();
    const pipelineInr = all.reduce((sum, lead) => {
      const k = lead.kanban as { potential_value_inr?: number } | undefined;
      return sum + (k?.potential_value_inr ?? 25_000);
    }, 0);
    return {
      ...metrics,
      total_leads: metrics.total_leads ?? all.length,
      pipeline_value_inr: metrics.pipeline_value_inr ?? pipelineInr,
      revenue_forecast_inr: metrics.revenue_forecast_inr ?? Math.round(pipelineInr * 0.35),
    };
  }, [columns, metrics]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Intake pipeline"
        subtitle="Leads display in a responsive grid per stage — drag cards between stages below"
      />
      <div className="flex-1 overflow-y-auto flex flex-col p-2 sm:p-4 min-h-0 le-scroll">
        <div className="flex gap-2 mb-3 items-center shrink-0">
          <Link href="/intake" className="text-sm text-blue-700 hover:underline">
            ← Command center
          </Link>
          <Link href="/intake/new" className="text-sm text-blue-700 hover:underline ml-auto">
            + New lead
          </Link>
        </div>
        {err && (
          <p className="text-red-600 text-sm mb-2 bg-red-50 border border-red-100 rounded-lg px-3 py-2 shrink-0">
            {err}
          </p>
        )}
        {loading ? (
          <p className="text-sm text-slate-500">Loading pipeline…</p>
        ) : (
          <>
            <div className="shrink-0">
              <CrmKanbanMetrics metrics={displayMetrics} />
            </div>
            <CrmKanbanBoard
              columns={columns}
              stages={stages}
              stageLabels={labels}
              emptyHints={emptyHints}
              metrics={displayMetrics}
              commandCenter={commandCenter}
              canEdit={canEdit}
              onMoved={load}
            />
          </>
        )}
      </div>
    </div>
  );
}
