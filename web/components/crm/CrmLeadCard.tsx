"use client";

import { useState } from "react";
import {
  formatInr,
  getKanbanMeta,
  PRIORITY_STYLES,
  resolveLeadRisk,
  resolveLeadScore,
  RISK_STYLES,
  scoreBandColor,
  timeAgo,
  whatsappUrl,
} from "./crmUtils";

export type LeadCardActions = {
  onOpenSchedule: (leadId: string, lead: Record<string, unknown>) => void;
  onRequestDocuments: (leadId: string) => Promise<void>;
  onLogCall: (leadId: string, phone: string) => void;
  onLogEmail: (leadId: string, email: string) => void;
  onLogWhatsApp: (leadId: string, phone: string) => void;
};

type Props = {
  lead: Record<string, unknown>;
  canEdit: boolean;
  draggable?: boolean;
  onDragStart?: () => void;
  onDragEnd?: () => void;
  onOpen?: (leadId: string) => void;
  actions: LeadCardActions;
};

const btn =
  "shrink-0 text-[0.6rem] font-semibold px-1.5 py-1 rounded border transition-colors whitespace-nowrap";
const btnDefault = `${btn} bg-white text-slate-700 border-slate-200 hover:border-blue-300 hover:text-blue-800`;
const btnPrimary = `${btn} bg-navy text-white border-navy hover:bg-slate-800`;
const btnDisabled = `${btn} bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed`;

export default function CrmLeadCard({
  lead,
  canEdit,
  draggable,
  onDragStart,
  onDragEnd,
  onOpen,
  actions,
}: Props) {
  const id = String(lead.lead_id);
  const meta = getKanbanMeta(lead);
  const { total: scoreTotal, band: scoreBand, needsAnalysis } = resolveLeadScore(lead);
  const priority = meta.priority || "low";
  const pStyle = PRIORITY_STYLES[priority] || PRIORITY_STYLES.low;
  const phone = String(lead.contact_phone || "");
  const email = String(lead.contact_email || "");
  const name = String(lead.prospect_name || "Lead");
  const { risk100, tier: riskTier, scale10 } = resolveLeadRisk(lead);
  const rStyle = RISK_STYLES[riskTier] || RISK_STYLES.medium;
  const [pending, setPending] = useState("");

  const stopBubble = (e: React.SyntheticEvent) => e.stopPropagation();

  const runDocs = async () => {
    if (!canEdit || pending) return;
    setPending("docs");
    try {
      await actions.onRequestDocuments(id);
    } finally {
      setPending("");
    }
  };

  return (
    <article
      className={`group h-full min-h-[220px] flex flex-col bg-white border border-slate-200/90 rounded-xl shadow-sm hover:shadow-xl hover:border-slate-300 hover:-translate-y-0.5 transition-all duration-200 border-l-4 ${pStyle.border}`}
    >
      <div className="flex items-start gap-1 p-3 pb-2">
        <span
          draggable={draggable && !pending}
          onDragStart={(e) => {
            e.stopPropagation();
            onDragStart?.();
          }}
          onDragEnd={(e) => {
            e.stopPropagation();
            onDragEnd?.();
          }}
          onMouseDown={stopBubble}
          className="text-slate-300 hover:text-slate-500 cursor-grab active:cursor-grabbing px-0.5 select-none text-sm leading-none"
          title="Drag to move stage"
        >
          ⠿
        </span>
        <button type="button" onClick={() => onOpen?.(id)} className="flex-1 min-w-0 text-left">
          <div className="flex justify-between gap-2 items-start">
            <h4 className="font-bold text-sm text-navy truncate uppercase tracking-tight hover:underline">
              {name}
            </h4>
            <span className={`shrink-0 text-[0.6rem] font-bold px-1.5 py-0.5 rounded border ${pStyle.badge}`}>
              {pStyle.label}
            </span>
          </div>
          <p className="text-xs text-slate-600 mt-0.5 font-medium">{meta.case_type_label}</p>
        </button>
      </div>

      <div className="px-3 pb-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[0.7rem]">
        <div>
          <span className="text-slate-400">AI score</span>
          <p className={`font-bold tabular-nums ${scoreBandColor(scoreBand)}`}>
            {needsAnalysis ? "Run AI" : `${meta.ai_score ?? scoreTotal}%`}
          </p>
          {!needsAnalysis && scoreBand ? (
            <p className="text-[0.55rem] uppercase text-slate-400">{scoreBand}</p>
          ) : null}
        </div>
        <div>
          <span className="text-slate-400">Conversion</span>
          <p className="font-bold text-emerald-700">{meta.conversion_probability ?? "—"}%</p>
        </div>
        <div className="col-span-2">
          <span className="text-slate-400">Potential fee</span>
          <p className="font-bold text-navy text-sm">{formatInr(meta.potential_value_inr ?? 0)}</p>
        </div>
      </div>

      <div className="px-3 pb-2 flex flex-wrap gap-1">
        <span className={`text-[0.6rem] px-1.5 py-0.5 rounded border font-semibold ${rStyle.badge}`}>
          Risk {scale10}/10
        </span>
        <span className={`text-[0.6rem] px-1.5 py-0.5 rounded ${rStyle.text} bg-white/80`}>
          {risk100}/100
        </span>
        {(meta.doc_badges || []).map((b) => (
          <span
            key={b.label}
            className={`text-[0.6rem] px-1.5 py-0.5 rounded ${
              b.status === "ok"
                ? "bg-emerald-50 text-emerald-800"
                : b.status === "warn"
                  ? "bg-amber-50 text-amber-800"
                  : "bg-slate-100 text-slate-600"
            }`}
          >
            {b.status === "ok" ? "✓ " : b.status === "warn" ? "⚠ " : ""}
            {b.label}
          </span>
        ))}
      </div>

      <div className="px-3 pb-2 text-[0.65rem] text-slate-500 space-y-0.5 border-t border-slate-100 pt-2 mx-3 flex-1">
        <p>
          <span className="text-slate-400">Follow-up: </span>
          <span className="font-semibold text-slate-700">{meta.follow_up_label}</span>
        </p>
        <p>
          <span className="text-slate-400">Assigned: </span>
          <span className="font-semibold text-slate-700">{meta.assigned_to}</span>
          {lead.created_at ? (
            <span className="text-slate-400"> · {timeAgo(String(lead.created_at))}</span>
          ) : null}
        </p>
      </div>

      <div
        className="mt-auto px-2 pb-2.5 flex flex-nowrap items-center gap-1 overflow-x-auto le-scroll"
        onMouseDown={stopBubble}
        onClick={stopBubble}
      >
        {phone ? (
          <a
            href={`tel:${phone}`}
            onClick={() => actions.onLogCall(id, phone)}
            className={btnDefault}
          >
            Call
          </a>
        ) : (
          <span className={btnDisabled}>Call</span>
        )}
        {email ? (
          <a href={`mailto:${email}`} onClick={() => actions.onLogEmail(id, email)} className={btnDefault}>
            Email
          </a>
        ) : (
          <span className={btnDisabled}>Email</span>
        )}
        {phone ? (
          <a
            href={whatsappUrl(phone, `Hello ${name}, this is regarding your legal inquiry.`)}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => actions.onLogWhatsApp(id, phone)}
            className={btnDefault}
          >
            WhatsApp
          </a>
        ) : (
          <span className={btnDisabled}>WA</span>
        )}
        <button
          type="button"
          disabled={!canEdit}
          className={canEdit ? btnPrimary : btnDisabled}
          onClick={() => actions.onOpenSchedule(id, lead)}
        >
          Schedule
        </button>
        <button
          type="button"
          disabled={!canEdit || pending === "docs"}
          className={canEdit ? btnDefault : btnDisabled}
          onClick={() => void runDocs()}
        >
          {pending === "docs" ? "…" : "Docs"}
        </button>
      </div>
    </article>
  );
}
