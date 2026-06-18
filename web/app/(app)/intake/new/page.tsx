"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import * as api from "@/lib/api";
import { formatApiError } from "@/components/crm/crmUtils";

export default function NewLeadPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    prospect_name: "",
    contact_email: "",
    contact_phone: "",
    address: "",
    city: "",
    state: "",
    preferred_contact: "email",
    preferred_language: "English",
    referral_source: "",
    raw_intake_query: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (form.raw_intake_query.trim().length < 10) {
      setErr("Intake description must be at least 10 characters.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const lead = await api.createCrmLead(form);
      router.push(`/intake/${lead.lead_id}`);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader title="New intake lead" subtitle="Full contact profile with AI analysis on save" />
      <div className="flex-1 overflow-y-auto le-scroll p-3 sm:p-6 max-w-3xl mx-auto w-full space-y-4">
        <Link href="/intake" className="text-sm text-blue-700 hover:underline">
          ← Dashboard
        </Link>
        {err && <p className="text-red-600 text-sm bg-red-50 border px-4 py-3 rounded-lg">{err}</p>}
        <section className="bg-white border rounded-xl p-4 space-y-3">
          <div className="grid md:grid-cols-2 gap-3">
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="Prospect name *"
              value={form.prospect_name}
              onChange={(e) => set("prospect_name", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="Email *"
              value={form.contact_email}
              onChange={(e) => set("contact_email", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="Phone"
              value={form.contact_phone}
              onChange={(e) => set("contact_phone", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="Referral source"
              value={form.referral_source}
              onChange={(e) => set("referral_source", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm md:col-span-2"
              placeholder="Address"
              value={form.address}
              onChange={(e) => set("address", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="City"
              value={form.city}
              onChange={(e) => set("city", e.target.value)}
            />
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="State"
              value={form.state}
              onChange={(e) => set("state", e.target.value)}
            />
            <select
              className="border rounded-lg px-3 py-2 text-sm"
              value={form.preferred_contact}
              onChange={(e) => set("preferred_contact", e.target.value)}
            >
              <option value="email">Preferred: Email</option>
              <option value="phone">Preferred: Phone</option>
              <option value="whatsapp">Preferred: WhatsApp</option>
            </select>
            <input
              className="border rounded-lg px-3 py-2 text-sm"
              placeholder="Preferred language"
              value={form.preferred_language}
              onChange={(e) => set("preferred_language", e.target.value)}
            />
          </div>
          <VoiceTextarea
            className="min-h-[8rem]"
            rows={6}
            value={form.raw_intake_query}
            onChange={(v) => set("raw_intake_query", v)}
            placeholder="Describe the legal problem in detail…"
          />
          <button
            type="button"
            disabled={busy}
            onClick={submit}
            className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            {busy ? "Creating & analyzing…" : "Create lead"}
          </button>
        </section>
      </div>
    </div>
  );
}
