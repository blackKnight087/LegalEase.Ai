"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import LeadAnalysisPanel from "@/components/crm/LeadAnalysisPanel";
import CrmAssistantPanel from "@/components/crm/CrmAssistantPanel";
import MatterConversionModal from "@/components/crm/MatterConversionModal";
import { getAnalysis, formatApiError, STAGE_COLORS } from "@/components/crm/crmUtils";
import * as api from "@/lib/api";

const TABS = [
  "Overview",
  "AI Analysis",
  "Documents",
  "Evidence",
  "Consultation",
  "Activity",
  "Audit",
] as const;

export default function LeadProfilePage() {
  const params = useParams();
  const router = useRouter();
  const leadId = String(params.leadId || "");
  const [lead, setLead] = useState<Record<string, unknown> | null>(null);
  const [perms, setPerms] = useState<api.CrmPermissions | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertPreview, setConvertPreview] = useState<Record<string, unknown> | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [templates, setTemplates] = useState<Array<Record<string, unknown>>>([]);
  const [selectedTpl, setSelectedTpl] = useState("");

  const load = useCallback(async () => {
    if (!leadId) return;
    try {
      const [l, p] = await Promise.all([
        api.getCrmLead(leadId),
        api.fetchCrmPermissions(),
      ]);
      setLead(l);
      setPerms(p);
      setFollowUp(String(l.follow_up_draft || ""));
      setErr("");
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [leadId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!leadId || !perms?.edit) return;
    api
      .fetchCrmFollowUpTemplates(leadId)
      .then((r) => setTemplates(r.templates || []))
      .catch(() => setTemplates([]));
  }, [leadId, perms?.edit]);

  const analysis = lead ? getAnalysis(lead) : {};
  const entities =
    (lead?.entities as Array<Record<string, unknown>>) || analysis.entities || [];
  const documents = (lead?.documents as Array<Record<string, unknown>>) || [];
  const interactions = (lead?.interactions as Array<Record<string, unknown>>) || [];

  const runAnalyze = async () => {
    setBusy(true);
    try {
      const l = await api.analyzeCrmLead(leadId);
      setLead(l);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const openConvert = async () => {
    setBusy(true);
    try {
      const prev = await api.previewCrmConversion(leadId);
      setConvertPreview(prev);
      setConvertOpen(true);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const confirmConvert = async () => {
    setBusy(true);
    try {
      const out = await api.convertLeadToMatter(leadId);
      const mid = out.matter_id || (out.matter as Record<string, unknown>)?.matter_id;
      setConvertOpen(false);
      if (mid) {
        router.push(`/matters?matter=${mid}`);
      } else {
        await load();
      }
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const uploadDoc = async (file: File) => {
    setBusy(true);
    try {
      await api.uploadCrmLeadDocument(leadId, file);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    setBusy(true);
    try {
      await api.addCrmInteraction(leadId, {
        interaction_type: "note",
        title: "Note",
        body: note,
      });
      setNote("");
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!rejectReason.trim()) return;
    setBusy(true);
    try {
      await api.rejectCrmLead(leadId, rejectReason);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const sendFollowUp = async () => {
    setBusy(true);
    try {
      await api.crmFollowUpSend(leadId, { body: followUp });
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const previewFollowUp = async () => {
    setBusy(true);
    try {
      const r = await api.crmFollowUpPreview(
        leadId,
        String(lead?.prospect_name || "Client")
      );
      setFollowUp(r.draft || "");
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const applyTemplate = async () => {
    if (!selectedTpl) return;
    setBusy(true);
    try {
      const r = await api.applyCrmFollowUpTemplate(leadId, selectedTpl);
      setFollowUp(r.draft || "");
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    setBusy(true);
    try {
      await api.archiveCrmLead(leadId);
      await load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  if (!lead && !err) {
    return (
      <div className="p-6 text-sm text-slate-500">Loading lead…</div>
    );
  }

  const stage = String(lead?.pipeline_stage || "");
  const score = Number(lead?.lead_score || 0);

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title={String(lead?.prospect_name || "Lead")}
        subtitle={`Score ${score} · ${String(lead?.case_type || "")}`}
      />
      <div className="flex-1 overflow-y-auto le-scroll p-3 sm:p-4 md:p-6">
        <div className="flex flex-wrap gap-2 mb-4">
          <Link href="/intake/board" className="text-sm text-blue-700 hover:underline">
            ← Board
          </Link>
          <span
            className={`text-xs uppercase px-2 py-1 rounded-full ml-auto ${STAGE_COLORS[stage] || "bg-slate-100"}`}
          >
            {stage}
          </span>
        </div>
        {err && (
          <p className="text-red-600 text-sm bg-red-50 border px-4 py-3 rounded-lg mb-4">{err}</p>
        )}

        <div className="flex flex-wrap gap-2 mb-4">
          {perms?.edit && (
            <button
              type="button"
              disabled={busy}
              onClick={runAnalyze}
              className="text-xs px-3 py-1.5 border rounded-lg"
            >
              Re-run AI
            </button>
          )}
          {perms?.convert && stage !== "MATTER_CREATED" && (
            <button
              type="button"
              disabled={busy}
              onClick={openConvert}
              className="text-xs px-3 py-1.5 bg-emerald-700 text-white rounded-lg"
            >
              Convert to matter
            </button>
          )}
          {perms?.reject && stage !== "REJECTED" && (
            <button
              type="button"
              disabled={busy}
              onClick={reject}
              className="text-xs px-3 py-1.5 border border-red-300 text-red-700 rounded-lg"
            >
              Reject
            </button>
          )}
          {perms?.edit && !["CLOSED", "REJECTED"].includes(stage) && (
            <button
              type="button"
              disabled={busy}
              onClick={archive}
              className="text-xs px-3 py-1.5 border rounded-lg"
            >
              Archive
            </button>
          )}
          {lead?.matter_id ? (
            <Link
              href={`/matters?matter=${String(lead.matter_id)}`}
              className="text-xs px-3 py-1.5 bg-blue-700 text-white rounded-lg"
            >
              Open matter
            </Link>
          ) : null}
        </div>
        {perms?.reject && (
          <input
            className="border rounded-lg px-3 py-2 text-sm w-full max-w-md mb-4"
            placeholder="Rejection reason (required to reject)"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
          />
        )}

        <div className="flex gap-1 overflow-x-auto border-b mb-4 touch-scroll-x -mx-1 px-1 pb-1">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-2.5 min-h-[44px] text-xs whitespace-nowrap border-b-2 -mb-px ${
                tab === t ? "border-navy text-navy font-semibold" : "border-transparent text-slate-500"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 lg:gap-6">
          <div>
            {tab === "Overview" && (
              <div className="space-y-4">
                <section className="bg-white border rounded-xl p-4 text-sm space-y-2">
                  <p>
                    <b>Email:</b> {String(lead?.contact_email)}
                  </p>
                  <p>
                    <b>Phone:</b> {String(lead?.contact_phone || "—")}
                  </p>
                  <p>
                    <b>Location:</b>{" "}
                    {[lead?.city, lead?.state].filter(Boolean).join(", ") || "—"}
                  </p>
                  <p>
                    <b>Referral:</b> {String(lead?.referral_source || "—")}
                  </p>
                  <p className="whitespace-pre-wrap mt-3">{String(lead?.raw_intake_query)}</p>
                </section>
                <section className="bg-white border rounded-xl p-4">
                  <h3 className="text-sm font-semibold mb-2">Follow-up</h3>
                  {perms?.edit && templates.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      <select
                        className="border rounded-lg text-xs px-2 py-1.5 flex-1 min-w-[140px]"
                        value={selectedTpl}
                        onChange={(e) => setSelectedTpl(e.target.value)}
                      >
                        <option value="">Template…</option>
                        {templates.map((t) => (
                          <option key={String(t.template_id)} value={String(t.template_id)}>
                            {String(t.name)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={busy || !selectedTpl}
                        onClick={applyTemplate}
                        className="text-xs px-2 py-1.5 border rounded-lg"
                      >
                        Apply
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={previewFollowUp}
                        className="text-xs px-2 py-1.5 border rounded-lg"
                      >
                        AI draft
                      </button>
                    </div>
                  )}
                  <textarea
                    className="w-full border rounded-lg text-sm p-2 min-h-[120px]"
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    disabled={!perms?.edit}
                  />
                  {perms?.edit && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={sendFollowUp}
                      className="mt-2 text-xs px-3 py-1.5 bg-navy text-white rounded-lg"
                    >
                      Log follow-up sent
                    </button>
                  )}
                </section>
              </div>
            )}
            {tab === "AI Analysis" && (
              <LeadAnalysisPanel
                analysis={analysis}
                leadScore={score}
                leadScoreBand={String(lead?.lead_score_band || "")}
              />
            )}
            {tab === "Documents" && (
              <div className="space-y-4">
                {perms?.edit && (
                  <input
                    type="file"
                    className="text-sm"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadDoc(f);
                    }}
                  />
                )}
                <ul className="space-y-2">
                  {documents.map((d) => (
                    <li key={String(d.doc_id)} className="bg-white border rounded-lg p-3 text-sm">
                      {String(d.filename)}
                      <span className="text-xs text-slate-500 ml-2">{String(d.doc_kind)}</span>
                    </li>
                  ))}
                  {!documents.length && (
                    <p className="text-sm text-slate-500">No documents uploaded.</p>
                  )}
                </ul>
              </div>
            )}
            {tab === "Evidence" && (
              <LeadAnalysisPanel analysis={{ evidence_readiness: analysis.evidence_readiness }} />
            )}
            {tab === "Consultation" && (
              <section className="bg-white border rounded-xl p-4">
                <h3 className="text-sm font-semibold mb-3">Consultation questions</h3>
                <ol className="list-decimal pl-5 text-sm space-y-2">
                  {(analysis.consultation_questions || []).map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ol>
                <h3 className="text-sm font-semibold mt-6 mb-3">Parties & entities</h3>
                <ul className="text-sm space-y-1">
                  {entities.map((e, i) => (
                    <li key={i}>
                      {String(e.label)} — {String(e.role || e.entity_type)}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {tab === "Activity" && (
              <div className="space-y-3">
                {perms?.edit && (
                  <div className="flex gap-2">
                    <input
                      className="flex-1 border rounded-lg px-3 py-2 text-sm"
                      placeholder="Add note…"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={addNote}
                      disabled={busy}
                      className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
                    >
                      Add
                    </button>
                  </div>
                )}
                {interactions.map((ix) => (
                  <div key={String(ix.interaction_id)} className="bg-white border rounded-lg p-3 text-sm">
                    <p className="font-medium text-xs text-slate-500">
                      {String(ix.interaction_type)} · {String(ix.created_at)}
                    </p>
                    <p>{String(ix.body || ix.title)}</p>
                  </div>
                ))}
              </div>
            )}
            {tab === "Audit" && <AuditTab leadId={leadId} />}
          </div>
          <CrmAssistantPanel leadId={leadId} />
        </div>
      </div>
      <MatterConversionModal
        preview={convertPreview}
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        onConfirm={confirmConvert}
        busy={busy}
      />
    </div>
  );
}

function AuditTab({ leadId }: { leadId: string }) {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  useEffect(() => {
    api.listCrmAudit(leadId).then((r) => setRows(r.audit || []));
  }, [leadId]);
  return (
    <ul className="space-y-2 text-sm">
      {rows.map((a) => (
        <li key={String(a.id)} className="bg-white border rounded-lg p-3">
          <span className="font-medium">{String(a.action)}</span>
          <span className="text-slate-500 text-xs ml-2">{String(a.created_at)}</span>
          {a.detail ? <p className="text-xs mt-1">{String(a.detail)}</p> : null}
        </li>
      ))}
      {!rows.length && <p className="text-slate-500">No audit entries.</p>}
    </ul>
  );
}
