import * as api from "@/lib/api";
import { formatApiError } from "./crmUtils";

export type LeadActionResult = { ok: true; message: string } | { ok: false; message: string };

async function runAction(fn: () => Promise<void>, successMessage: string): Promise<LeadActionResult> {
  try {
    await fn();
    return { ok: true, message: successMessage };
  } catch (e) {
    return { ok: false, message: formatApiError(e) };
  }
}

export async function scheduleConsultation(
  leadId: string,
  opts?: {
    note?: string;
    scheduledAt?: string;
    currentStage?: string;
  }
): Promise<LeadActionResult> {
  const when = opts?.scheduledAt
    ? new Date(opts.scheduledAt).toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "";
  const detail = opts?.note?.trim() || "Consultation scheduled from intake pipeline";
  const body = when ? `Scheduled for ${when}. ${detail}` : detail;
  const already =
    (opts?.currentStage || "").toUpperCase() === "CONSULTATION_SCHEDULED";

  return runAction(async () => {
    if (!already) {
      await api.patchCrmLeadStage(leadId, "CONSULTATION_SCHEDULED", body);
    }
    await api.addCrmInteraction(leadId, {
      interaction_type: "consultation",
      title: when ? `Consultation — ${when}` : "Consultation scheduled",
      body,
    });
  }, already
    ? `Consultation updated${when ? ` for ${when}` : ""} — logged on timeline.`
    : `Consultation scheduled${when ? ` for ${when}` : ""} — lead moved to Consultation Scheduled.`);
}

export async function requestDocuments(
  leadId: string,
  note = "Client asked to upload FIR, ID, and supporting documents."
): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.patchCrmLeadStage(leadId, "DOCUMENTS_REQUESTED", note);
    await api.addCrmInteraction(leadId, {
      interaction_type: "document_request",
      title: "Documents requested",
      body: note,
    });
  }, "Document request recorded — stage updated.");
}

export async function logOutboundCall(leadId: string, phone: string): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.addCrmInteraction(leadId, {
      interaction_type: "call",
      title: "Outbound call",
      body: phone ? `Called ${phone}` : "Outbound call logged",
    });
  }, "Call logged on timeline.");
}

export async function logOutboundEmail(leadId: string, email: string): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.addCrmInteraction(leadId, {
      interaction_type: "email",
      title: "Email sent",
      body: email ? `Emailed ${email}` : "Email logged",
    });
  }, "Email logged on timeline.");
}

export async function logWhatsApp(leadId: string, phone: string): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.addCrmInteraction(leadId, {
      interaction_type: "whatsapp",
      title: "WhatsApp message",
      body: phone ? `WhatsApp to ${phone}` : "WhatsApp logged",
    });
  }, "WhatsApp logged on timeline.");
}

export async function addLeadNote(leadId: string, body: string): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.addCrmInteraction(leadId, {
      interaction_type: "note",
      title: "Note",
      body,
    });
  }, "Note saved.");
}

export async function moveLeadStage(
  leadId: string,
  stage: string,
  note = ""
): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.patchCrmLeadStage(leadId, stage, note);
  }, "Pipeline stage updated.");
}

export async function sendFollowUpEmail(
  leadId: string,
  body: string,
  subject?: string
): Promise<LeadActionResult> {
  return runAction(async () => {
    await api.crmFollowUpSend(leadId, { body, subject });
  }, "Follow-up saved and marked sent.");
}

export async function previewFollowUpEmail(
  leadId: string,
  prospectName: string
): Promise<{ ok: true; draft: string } | { ok: false; message: string }> {
  try {
    const r = await api.crmFollowUpPreview(leadId, prospectName);
    return { ok: true, draft: r.draft || "" };
  } catch (e) {
    return { ok: false, message: formatApiError(e) };
  }
}
