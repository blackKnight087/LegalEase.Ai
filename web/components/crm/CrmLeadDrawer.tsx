"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import LeadAnalysisPanel from "./LeadAnalysisPanel";
import CrmActionBanner from "./CrmActionBanner";
import {
  addLeadNote,
  logOutboundCall,
  logOutboundEmail,
  logWhatsApp,
  previewFollowUpEmail,
  requestDocuments,
  sendFollowUpEmail,
} from "./crmLeadActions";
import {
  formatApiError,
  formatInr,
  getAnalysis,
  getKanbanMeta,
  resolveLeadRisk,
  resolveLeadScore,
  RISK_STYLES,
  PRIORITY_STYLES,
  STAGE_COLORS,
  whatsappUrl,
} from "./crmUtils";
import * as api from "@/lib/api";

const DRAWER_TABS = ["Profile", "AI Analysis", "Documents", "Timeline", "Follow-up"] as const;

type Props = {
  leadId: string | null;
  stageLabels: Record<string, string>;
  canEdit?: boolean;
  onClose: () => void;
  onUpdated?: () => void;
  onScheduleLead?: (leadId: string, lead: Record<string, unknown>) => void;
  onActionMessage?: (message: string, variant: "success" | "error") => void;
};

export default function CrmLeadDrawer({
  leadId,
  stageLabels,
  canEdit = true,
  onClose,
  onUpdated,
  onScheduleLead,
  onActionMessage,
}: Props) {
  const router = useRouter();
  const [lead, setLead] = useState<Record<string, unknown> | null>(null);
  const [tab, setTab] = useState<(typeof DRAWER_TABS)[number]>("Profile");
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [followUp, setFollowUp] = useState("");

  const reloadLead = useCallback(async () => {
    if (!leadId) return;
    const l = await api.getCrmLead(leadId);
    setLead(l);
    setFollowUp(String(l.follow_up_draft || ""));
  }, [leadId]);

  useEffect(() => {
    if (!leadId) {
      setLead(null);
      return;
    }
    setTab("Profile");
    setErr("");
    setSuccess("");
    reloadLead().catch((e) => setErr(formatApiError(e)));
  }, [leadId, reloadLead]);

  const notify = (message: string, variant: "success" | "error") => {
    if (variant === "success") {
      setSuccess(message);
      setErr("");
      onActionMessage?.(message, "success");
    } else {
      setErr(message);
      setSuccess("");
      onActionMessage?.(message, "error");
    }
  };

  const run = async (fn: () => Promise<{ ok: boolean; message: string }>) => {
    if (!canEdit) {
      notify("You do not have permission to edit leads.", "error");
      return;
    }
    setBusy(true);
    const result = await fn();
    if (result.ok) {
      notify(result.message, "success");
      await reloadLead();
      onUpdated?.();
    } else {
      notify(result.message, "error");
    }
    setBusy(false);
  };

  if (!leadId) return null;

  const meta = lead ? getKanbanMeta(lead) : {};
  const scoreInfo = lead ? resolveLeadScore(lead) : { total: 0, band: "", needsAnalysis: true };
  const riskInfo = lead ? resolveLeadRisk(lead) : { risk100: 0, tier: "low", scale10: 0 };
  const riskStyle = RISK_STYLES[riskInfo.tier] || RISK_STYLES.medium;
  const analysis = lead ? getAnalysis(lead) : {};
  const stage = String(lead?.pipeline_stage || "");
  const priority = meta.priority || "low";
  const pStyle = PRIORITY_STYLES[priority] || PRIORITY_STYLES.low;
  const documents = (lead?.documents as Array<Record<string, unknown>>) || [];
  const interactions = (lead?.interactions as Array<Record<string, unknown>>) || [];
  const phone = String(lead?.contact_phone || "");
  const email = String(lead?.contact_email || "");
  const name = String(lead?.prospect_name || "Lead");

  const btnClass =
    "text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-50 disabled:cursor-not-allowed";

  return (
    <>
      <div className="fixed inset-0 bg-navy/30 z-40 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <aside className="fixed top-0 right-0 h-full w-full max-w-md bg-white shadow-2xl z-50 flex flex-col border-l border-slate-200">
        <header className="flex items-start justify-between gap-3 p-4 border-b border-slate-100 bg-slate-50/80">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-navy truncate">{name}</h2>
            <p className="text-sm text-slate-600">{meta.case_type_label}</p>
            <div className="flex flex-wrap gap-1.5 mt-2">
              <span className={`text-xs px-2 py-0.5 rounded border ${pStyle.badge}`}>{pStyle.label} priority</span>
              <span className={`text-xs px-2 py-0.5 rounded ${STAGE_COLORS[stage] || "bg-slate-100"}`}>
                {stageLabels[stage] || stage}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-xl leading-none p-1"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="px-3 pt-2 space-y-2">
          <CrmActionBanner message={success} variant="success" onDismiss={() => setSuccess("")} />
          <CrmActionBanner message={err} variant="error" onDismiss={() => setErr("")} />
        </div>

        <div className="grid grid-cols-4 gap-1 px-3 py-2 border-b border-slate-100 text-center text-[0.65rem]">
          <div>
            <p className="text-slate-400">AI score</p>
            <p className="font-bold text-indigo-700">
              {scoreInfo.needsAnalysis ? "—" : `${meta.ai_score ?? scoreInfo.total}%`}
            </p>
          </div>
          <div>
            <p className="text-slate-400">Convert</p>
            <p className="font-bold text-emerald-700">{meta.conversion_probability ?? "—"}%</p>
          </div>
          <div>
            <p className="text-slate-400">Fee</p>
            <p className="font-bold text-navy">{formatInr(meta.potential_value_inr ?? 0)}</p>
          </div>
          <div>
            <p className="text-slate-400">Risk</p>
            <p className={`font-bold ${riskStyle.text}`}>
              {riskInfo.scale10}/10
            </p>
            <p className="text-[0.55rem] text-slate-400">{riskInfo.risk100}/100 · {riskInfo.tier}</p>
          </div>
        </div>

        <div className="flex gap-1 px-3 py-2 border-b overflow-x-auto">
          {DRAWER_TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${
                tab === t ? "bg-navy text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 le-scroll">
          {!lead && !err && <p className="text-sm text-slate-500">Loading lead…</p>}

          {tab === "Profile" && lead && (
            <div className="space-y-4 text-sm">
              <section>
                <h3 className="text-xs font-bold uppercase text-slate-500 mb-2">Client</h3>
                <dl className="space-y-1.5">
                  <div>
                    <dt className="text-slate-400 inline">Phone: </dt>
                    <dd className="inline font-medium">
                      {phone ? (
                        <a href={`tel:${phone}`} className="text-blue-700 hover:underline">
                          {phone}
                        </a>
                      ) : (
                        "—"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-400 inline">Email: </dt>
                    <dd className="inline font-medium">
                      {email ? (
                        <a href={`mailto:${email}`} className="text-blue-700 hover:underline">
                          {email}
                        </a>
                      ) : (
                        "—"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-400 inline">Address: </dt>
                    <dd className="inline font-medium">{String(lead.address || lead.city || "—")}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-400 inline">Assigned: </dt>
                    <dd className="inline font-medium">{meta.assigned_to}</dd>
                  </div>
                </dl>
              </section>
              <section>
                <h3 className="text-xs font-bold uppercase text-slate-500 mb-2">Case summary</h3>
                <p className="text-slate-700 whitespace-pre-wrap">{String(lead.raw_intake_query || "—")}</p>
              </section>
              <section>
                <h3 className="text-xs font-bold uppercase text-slate-500 mb-2">Recommended action</h3>
                <p className="text-slate-700 bg-blue-50 border border-blue-100 rounded-lg p-3">
                  {meta.recommended_action || analysis.executive_summary || "Run AI analysis for next steps."}
                </p>
              </section>
              <div className="flex flex-nowrap gap-1.5 overflow-x-auto le-scroll">
                {phone && (
                  <a
                    href={`tel:${phone}`}
                    onClick={() => void logOutboundCall(leadId, phone)}
                    className={`${btnClass} border-slate-200 hover:bg-slate-50 shrink-0`}
                  >
                    Call
                  </a>
                )}
                {email && (
                  <a
                    href={`mailto:${email}`}
                    onClick={() => void logOutboundEmail(leadId, email)}
                    className={`${btnClass} border-slate-200 hover:bg-slate-50 shrink-0`}
                  >
                    Email
                  </a>
                )}
                {phone && (
                  <a
                    href={whatsappUrl(phone, `Hello ${name}, regarding your legal inquiry.`)}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => void logWhatsApp(leadId, phone)}
                    className={`${btnClass} border-emerald-200 text-emerald-800 hover:bg-emerald-50 shrink-0`}
                  >
                    WhatsApp
                  </a>
                )}
                <button
                  type="button"
                  disabled={!canEdit}
                  onClick={() => lead && onScheduleLead?.(leadId, lead)}
                  className={`${btnClass} bg-navy text-white border-navy shrink-0`}
                >
                  Schedule
                </button>
                <button
                  type="button"
                  disabled={busy || !canEdit}
                  onClick={() => run(() => requestDocuments(leadId))}
                  className={`${btnClass} border-amber-200 text-amber-900 hover:bg-amber-50 shrink-0`}
                >
                  Docs
                </button>
                <button
                  type="button"
                  disabled={busy || !canEdit}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api.analyzeCrmLead(leadId);
                      await reloadLead();
                      onUpdated?.();
                      notify("AI analysis completed.", "success");
                    } catch (e) {
                      notify(formatApiError(e), "error");
                    } finally {
                      setBusy(false);
                    }
                  }}
                  className={`${btnClass} border-indigo-200 text-indigo-800 hover:bg-indigo-50`}
                >
                  Run AI analysis
                </button>
              </div>
            </div>
          )}

          {tab === "AI Analysis" && lead && (
            <LeadAnalysisPanel
              analysis={analysis}
              leadScore={Number(lead.lead_score || 0)}
              leadScoreBand={String(lead.lead_score_band || "")}
            />
          )}

          {tab === "Documents" && lead && (
            <div className="space-y-2">
              {documents.length === 0 ? (
                <p className="text-sm text-slate-500">No documents uploaded yet.</p>
              ) : (
                documents.map((d) => (
                  <div key={String(d.document_id)} className="border rounded-lg p-2 text-sm">
                    <p className="font-medium">{String(d.filename || d.document_id)}</p>
                    <p className="text-xs text-slate-500">{String(d.uploaded_at || "")}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "Timeline" && lead && (
            <div className="space-y-3">
              {interactions.length === 0 ? (
                <p className="text-sm text-slate-500">No activity yet.</p>
              ) : (
                interactions.map((ix) => (
                  <div key={String(ix.interaction_id || ix.created_at)} className="border-l-2 border-blue-200 pl-3">
                    <p className="text-xs font-bold text-slate-700">{String(ix.title || ix.interaction_type)}</p>
                    <p className="text-xs text-slate-500">{String(ix.created_at || "")}</p>
                    {ix.body ? <p className="text-sm mt-1 text-slate-600">{String(ix.body)}</p> : null}
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "Follow-up" && lead && (
            <div className="space-y-3 text-sm">
              <p className="text-slate-600 text-xs">
                Draft a follow-up email. Preview generates AI text; Send saves the draft and logs activity.
              </p>
              <textarea
                value={followUp}
                onChange={(e) => setFollowUp(e.target.value)}
                rows={8}
                className="w-full border rounded-lg p-2 text-sm"
                placeholder="Follow-up email body…"
                disabled={!canEdit}
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || !canEdit}
                  className={`${btnClass} border-slate-200`}
                  onClick={async () => {
                    setBusy(true);
                    const r = await previewFollowUpEmail(leadId, name);
                    if (r.ok) {
                      setFollowUp(r.draft);
                      notify("Follow-up draft generated.", "success");
                    } else {
                      notify(r.message, "error");
                    }
                    setBusy(false);
                  }}
                >
                  Preview draft
                </button>
                <button
                  type="button"
                  disabled={busy || !canEdit || !followUp.trim()}
                  className={`${btnClass} bg-navy text-white border-navy`}
                  onClick={() => run(() => sendFollowUpEmail(leadId, followUp))}
                >
                  Mark follow-up sent
                </button>
              </div>
            </div>
          )}
        </div>

        <footer className="p-4 border-t border-slate-100 bg-slate-50/50 space-y-2">
          <div className="flex gap-2">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add a note…"
              disabled={!canEdit}
              className="flex-1 text-sm border rounded-lg px-2 py-1.5"
            />
            <button
              type="button"
              disabled={busy || !note.trim() || !canEdit}
              onClick={async () => {
                if (!note.trim()) return;
                setBusy(true);
                const r = await addLeadNote(leadId, note.trim());
                if (r.ok) {
                  setNote("");
                  notify(r.message, "success");
                  await reloadLead();
                  onUpdated?.();
                } else {
                  notify(r.message, "error");
                }
                setBusy(false);
              }}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-800 text-white disabled:opacity-50"
            >
              Save note
            </button>
          </div>
          <div className="flex gap-2">
            <Link
              href={`/intake/${leadId}`}
              className="flex-1 text-center text-xs font-semibold py-2 rounded-lg border border-slate-200 hover:bg-white"
            >
              Open full profile →
            </Link>
            <button
              type="button"
              disabled={busy || !canEdit}
              className="flex-1 text-center text-xs font-semibold py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              onClick={() => router.push(`/intake/${leadId}`)}
            >
              Convert to matter
            </button>
          </div>
        </footer>
      </aside>
    </>
  );
}
