"use client";

import { useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

/**
 * Public client intake — no firm login required.
 * Server: INTAKE_PUBLIC_ENABLED=1 and INTAKE_ORG_USER_ID
 */
export default function ClientIntakePage() {
  const [form, setForm] = useState({
    prospect_name: "",
    contact_email: "",
    contact_phone: "",
    referral_source: "Website",
    raw_intake_query: "",
  });
  const [done, setDone] = useState(false);
  const [leadId, setLeadId] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const name = form.prospect_name.trim();
    const query = form.raw_intake_query.trim();
    if (name.length < 2) {
      setErr("Please enter your full name.");
      return;
    }
    if (query.length < 10) {
      setErr("Please describe your legal issue in at least 10 characters.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const out = await api.submitPublicIntake(
        {
          prospect_name: name,
          contact_email: form.contact_email.trim(),
          contact_phone: form.contact_phone.trim(),
          raw_intake_query: query,
          referral_source: form.referral_source,
        },
        ""
      );
      setLeadId(String(out.lead_id || ""));
      setDone(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Submission failed";
      if (/503|INTAKE_ORG_USER_ID|disabled|403/i.test(msg)) {
        setErr(
          "Intake portal is not fully configured on the server yet. Please contact the law firm directly."
        );
      } else {
        setErr(msg);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen min-h-[100dvh] bg-gradient-to-b from-slate-50 to-blue-50/30 flex flex-col">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur px-4 py-4 shrink-0">
        <div className="max-w-xl mx-auto flex items-center justify-between gap-3">
          <span className="font-serif text-lg font-bold text-navy">LegalEase.AI</span>
          <Link href="/login" className="text-xs text-blue-700 hover:underline shrink-0">
            Firm login
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-lg p-5 sm:p-8">
          {done ? (
            <div className="text-center py-4">
              <p className="text-4xl mb-2" aria-hidden>
                ✓
              </p>
              <h1 className="font-serif text-xl text-navy m-0">Inquiry received</h1>
              <p className="text-sm text-slate-600 mt-2">
                Our team will review your submission and contact you shortly.
              </p>
              {leadId && (
                <p className="text-xs text-slate-500 mt-4 font-mono break-all">
                  Reference: {leadId.slice(0, 8)}…
                </p>
              )}
            </div>
          ) : (
            <>
              <h1 className="font-serif text-xl text-navy m-0">Submit a legal inquiry</h1>
              <p className="text-sm text-slate-600 mt-1 mb-6">
                Describe your matter confidentially. Our AI-assisted intake helps the firm respond faster.
              </p>
              {err && (
                <p
                  role="alert"
                  className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-4"
                >
                  {err}
                </p>
              )}
              <div className="space-y-4">
                <label className="block text-sm">
                  Your name <span className="text-red-600">*</span>
                  <input
                    className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2.5 text-base min-h-[44px]"
                    value={form.prospect_name}
                    onChange={(e) => setForm((f) => ({ ...f, prospect_name: e.target.value }))}
                    placeholder="Full name"
                    autoComplete="name"
                  />
                </label>
                <label className="block text-sm">
                  Email
                  <input
                    type="email"
                    className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2.5 text-base min-h-[44px]"
                    value={form.contact_email}
                    onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))}
                    autoComplete="email"
                  />
                </label>
                <label className="block text-sm">
                  Phone
                  <input
                    type="tel"
                    className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2.5 text-base min-h-[44px]"
                    value={form.contact_phone}
                    onChange={(e) => setForm((f) => ({ ...f, contact_phone: e.target.value }))}
                    autoComplete="tel"
                  />
                </label>
                <label className="block text-sm">
                  How did you hear about us?
                  <select
                    className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2.5 text-base min-h-[44px] bg-white"
                    value={form.referral_source}
                    onChange={(e) => setForm((f) => ({ ...f, referral_source: e.target.value }))}
                  >
                    <option>Website</option>
                    <option>WhatsApp</option>
                    <option>Referral</option>
                    <option>LinkedIn</option>
                    <option>Direct call</option>
                    <option>Other</option>
                  </select>
                </label>
                <label className="block text-sm">
                  Describe your legal issue <span className="text-red-600">*</span>
                  <textarea
                    rows={6}
                    className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm min-h-[120px]"
                    value={form.raw_intake_query}
                    onChange={(e) => setForm((f) => ({ ...f, raw_intake_query: e.target.value }))}
                    placeholder="What happened? What outcome do you need? Any court dates or documents?"
                  />
                </label>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void submit()}
                  className="w-full py-3 min-h-[48px] bg-navy text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                >
                  {busy ? "Submitting…" : "Submit inquiry"}
                </button>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
