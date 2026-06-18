"use client";

import { useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import * as api from "@/lib/api";
import { formatApiError } from "@/components/crm/crmUtils";

export default function PublicIntakePage() {
  const [form, setForm] = useState({
    prospect_name: "",
    contact_email: "",
    contact_phone: "",
    raw_intake_query: "",
  });
  const [intakeKey, setIntakeKey] = useState("");
  const [done, setDone] = useState(false);
  const [leadId, setLeadId] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      const out = await api.submitPublicIntake(form, intakeKey);
      setLeadId(String(out.lead_id || ""));
      setDone(true);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Public intake form"
        subtitle="Shareable client form — requires INTAKE_PUBLIC_ENABLED on the server"
      />
      <div className="flex-1 overflow-y-auto le-scroll p-3 sm:p-6 max-w-xl mx-auto w-full">
        {done ? (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6 text-sm">
            <p className="font-semibold text-emerald-900">Thank you — your inquiry was received.</p>
            {leadId && <p className="text-xs mt-2 text-slate-600">Reference: {leadId}</p>}
          </div>
        ) : (
          <section className="bg-white border rounded-xl p-4 space-y-3">
            <input
              className="border rounded-lg px-3 py-2 text-sm w-full"
              placeholder="Intake API key (if configured)"
              value={intakeKey}
              onChange={(e) => setIntakeKey(e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm w-full"
              placeholder="Your name"
              value={form.prospect_name}
              onChange={(e) => setForm((f) => ({ ...f, prospect_name: e.target.value }))}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm w-full"
              placeholder="Email"
              value={form.contact_email}
              onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm w-full"
              placeholder="Phone"
              value={form.contact_phone}
              onChange={(e) => setForm((f) => ({ ...f, contact_phone: e.target.value }))}
            />
            <VoiceTextarea
              rows={5}
              value={form.raw_intake_query}
              onChange={(v) => setForm((f) => ({ ...f, raw_intake_query: v }))}
              placeholder="Describe your legal issue…"
            />
            {err && <p className="text-red-600 text-sm">{err}</p>}
            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="w-full py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
            >
              {busy ? "Submitting…" : "Submit inquiry"}
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
