"use client";

import Link from "next/link";
import type { CrmCommandCenter } from "@/lib/api";
import { formatInr, getKanbanMeta, PRIORITY_STYLES } from "./crmUtils";

type LeadRow = Record<string, unknown>;

function pickTopLead(
  columns: Record<string, LeadRow[]>,
  compare: (a: LeadRow, b: LeadRow) => number
): LeadRow | null {
  const all = Object.values(columns).flat();
  if (!all.length) return null;
  return [...all].sort(compare)[0];
}

type Props = {
  columns: Record<string, LeadRow[]>;
  metrics: {
    conversion_rate?: number;
    revenue_forecast_inr?: number;
    pipeline_value_inr?: number;
  };
  commandCenter?: CrmCommandCenter | null;
  onOpenLead?: (leadId: string) => void;
};

export default function CrmKanbanIntelligencePanel({
  columns,
  metrics,
  commandCenter,
  onOpenLead,
}: Props) {
  const highestValue = pickTopLead(columns, (a, b) => {
    const va = getKanbanMeta(a).potential_value_inr ?? 0;
    const vb = getKanbanMeta(b).potential_value_inr ?? 0;
    return vb - va;
  });

  const highestPriority = pickTopLead(columns, (a, b) => {
    const order = { high: 3, medium: 2, low: 1 };
    const pa = order[getKanbanMeta(a).priority as keyof typeof order] ?? 0;
    const pb = order[getKanbanMeta(b).priority as keyof typeof order] ?? 0;
    if (pb !== pa) return pb - pa;
    return (getKanbanMeta(b).ai_score ?? 0) - (getKanbanMeta(a).ai_score ?? 0);
  });

  const followUps = commandCenter?.follow_ups?.due_today ?? [];
  const recommendations = commandCenter?.ai_recommendations ?? [];
  const totalLeads = Object.values(columns).flat().length;

  const renderLeadHighlight = (
    label: string,
    lead: LeadRow | null,
    accent: string
  ) => {
    if (!lead) {
      return (
        <div className="rounded-xl border border-dashed border-slate-200 p-3 text-sm text-slate-500">
          No active leads yet — add an inquiry to see {label.toLowerCase()}.
        </div>
      );
    }
    const meta = getKanbanMeta(lead);
    const id = String(lead.lead_id);
    const priority = meta.priority || "low";
    const pStyle = PRIORITY_STYLES[priority] || PRIORITY_STYLES.low;

    return (
      <button
        type="button"
        onClick={() => onOpenLead?.(id)}
        className={`w-full text-left rounded-xl border p-3 transition-all hover:shadow-md hover:border-slate-300 ${accent}`}
      >
        <p className="text-[0.65rem] font-bold uppercase text-slate-500">{label}</p>
        <p className="font-bold text-navy mt-1 truncate">{String(lead.prospect_name)}</p>
        <p className="text-xs text-slate-600 mt-0.5">{meta.case_type_label}</p>
        <div className="flex flex-wrap gap-2 mt-2 text-xs">
          <span className={`px-1.5 py-0.5 rounded border ${pStyle.badge}`}>{pStyle.label}</span>
          <span className="text-slate-600">
            Fee <strong className="text-navy">{formatInr(meta.potential_value_inr ?? 0)}</strong>
          </span>
          <span className="text-emerald-700">
            {meta.conversion_probability}% likely
          </span>
        </div>
        <p className="text-[0.65rem] text-slate-500 mt-2 line-clamp-2">
          {meta.recommended_action || "Review and schedule next step."}
        </p>
      </button>
    );
  };

  return (
    <aside className="w-full lg:w-[280px] xl:w-[300px] flex-shrink-0 flex flex-col gap-3 lg:sticky lg:top-2 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto le-scroll">
      <div className="rounded-2xl bg-gradient-to-br from-navy via-slate-800 to-slate-900 text-white p-4 shadow-lg">
        <p className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-300">
          Lead intelligence
        </p>
        <p className="text-2xl font-bold mt-1 tabular-nums">
          {formatInr(metrics.pipeline_value_inr ?? 0)}
        </p>
        <p className="text-xs text-slate-300 mt-0.5">Active pipeline value</p>
        <div className="grid grid-cols-2 gap-2 mt-3 text-center">
          <div className="bg-white/10 rounded-lg py-2">
            <p className="text-lg font-bold">{metrics.conversion_rate ?? 0}%</p>
            <p className="text-[0.6rem] text-slate-300">Conversion</p>
          </div>
          <div className="bg-white/10 rounded-lg py-2">
            <p className="text-lg font-bold">{formatInr(metrics.revenue_forecast_inr ?? 0)}</p>
            <p className="text-[0.6rem] text-slate-300">Forecast</p>
          </div>
        </div>
      </div>

      {totalLeads === 0 ? (
        <div className="rounded-xl border border-blue-100 bg-blue-50/80 p-4 text-sm">
          <p className="font-semibold text-navy">Get your pipeline moving</p>
          <p className="text-slate-600 mt-1 text-xs leading-relaxed">
            Add a lead or enable your public intake portal. Empty stages stay collapsed so
            the board never looks unfinished.
          </p>
          <Link
            href="/intake/new"
            className="inline-block mt-3 text-xs font-bold px-3 py-1.5 rounded-lg bg-navy text-white"
          >
            Create first lead
          </Link>
        </div>
      ) : null}

      {renderLeadHighlight("Highest value", highestValue, "bg-amber-50/50 border-amber-100")}
      {renderLeadHighlight("Highest priority", highestPriority, "bg-red-50/40 border-red-100")}

      <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <h3 className="text-xs font-bold uppercase text-slate-500">Follow-ups due today</h3>
        {followUps.length === 0 ? (
          <p className="text-xs text-slate-500 mt-2">No follow-ups flagged for today.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {followUps.slice(0, 5).map((f) => (
              <li key={String(f.lead_id)}>
                <button
                  type="button"
                  onClick={() => onOpenLead?.(String(f.lead_id))}
                  className="w-full text-left text-xs hover:bg-slate-50 rounded-lg p-1.5 -mx-1"
                >
                  <span className="font-semibold text-navy">{String(f.prospect_name || "Lead")}</span>
                  <span className="text-slate-500 block">{String(f.due_label || "Follow up")}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <h3 className="text-xs font-bold uppercase text-slate-500">AI recommendations</h3>
        {recommendations.length === 0 ? (
          <p className="text-xs text-slate-500 mt-2">Run AI analysis on leads for tailored actions.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {recommendations.slice(0, 4).map((r, i) => (
              <li key={i} className="text-xs border-l-2 border-indigo-300 pl-2">
                <p className="font-semibold text-slate-800">{r.title}</p>
                <p className="text-slate-600 mt-0.5 line-clamp-2">{r.body}</p>
                {r.lead_id ? (
                  <button
                    type="button"
                    onClick={() => onOpenLead?.(String(r.lead_id))}
                    className="text-blue-700 font-semibold mt-1 hover:underline"
                  >
                    Open lead →
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
