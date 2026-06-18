"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";

export default function MatterCreateForm() {
  const router = useRouter();
  const [meta, setMeta] = useState<api.MatterMetaTypes | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [form, setForm] = useState({
    matter_name: "",
    matter_type: "Criminal",
    client_name: "",
    opposing_party: "",
    venue: "",
    case_number: "",
    fir_number: "",
    police_station: "",
    filing_date: "",
    next_hearing_date: "",
    status_tier: "Open",
    priority: "Medium",
    description: "",
  });

  useEffect(() => {
    api.fetchMatterMetaTypes().then(setMeta).catch(() => {});
  }, []);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.matter_name.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const m = await api.createMatter({
        ...form,
        practice_area: form.matter_type,
      });
      if (typeof window !== "undefined") {
        localStorage.setItem("legalease_active_matter", m.matter_id);
      }
      router.push(`/matters/${m.matter_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create matter");
    } finally {
      setBusy(false);
    }
  };

  const types = meta?.matter_types || [
    "Criminal",
    "Civil",
    "Family",
    "Corporate",
    "General Research",
  ];

  return (
    <form onSubmit={submit} className="space-y-6 max-w-3xl">
      {err && (
        <p className="text-red-700 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {err}
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
        <h2 className="text-sm font-semibold text-navy m-0">Case identity</h2>
        <input
          required
          className="w-full border rounded-lg px-3 py-2 text-sm"
          placeholder="Matter name (e.g. State vs Imran Khan)"
          value={form.matter_name}
          onChange={(e) => set("matter_name", e.target.value)}
        />
        <select
          className="w-full border rounded-lg px-3 py-2 text-sm"
          value={form.matter_type}
          onChange={(e) => set("matter_type", e.target.value)}
        >
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <textarea
          className="w-full border rounded-lg px-3 py-2 text-sm min-h-[80px]"
          placeholder="Description / summary"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 grid md:grid-cols-2 gap-3">
        <h2 className="text-sm font-semibold text-navy m-0 md:col-span-2">Parties & court</h2>
        <input
          className="border rounded-lg px-3 py-2 text-sm"
          placeholder="Client name"
          value={form.client_name}
          onChange={(e) => set("client_name", e.target.value)}
        />
        <input
          className="border rounded-lg px-3 py-2 text-sm"
          placeholder="Opposing party"
          value={form.opposing_party}
          onChange={(e) => set("opposing_party", e.target.value)}
        />
        <input
          className="border rounded-lg px-3 py-2 text-sm md:col-span-2"
          placeholder="Court / venue"
          value={form.venue}
          onChange={(e) => set("venue", e.target.value)}
        />
        <input
          className="border rounded-lg px-3 py-2 text-sm"
          placeholder="Case / FIR number"
          value={form.case_number}
          onChange={(e) => set("case_number", e.target.value)}
        />
        <input
          className="border rounded-lg px-3 py-2 text-sm"
          placeholder="FIR number"
          value={form.fir_number}
          onChange={(e) => set("fir_number", e.target.value)}
        />
        <input
          className="border rounded-lg px-3 py-2 text-sm md:col-span-2"
          placeholder="Police station"
          value={form.police_station}
          onChange={(e) => set("police_station", e.target.value)}
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 grid md:grid-cols-2 gap-3">
        <h2 className="text-sm font-semibold text-navy m-0 md:col-span-2">Status & dates</h2>
        <select
          className="border rounded-lg px-3 py-2 text-sm"
          value={form.status_tier}
          onChange={(e) => set("status_tier", e.target.value)}
        >
          {(meta?.status_tiers || ["Open", "In Hearing", "Pending", "Closed"]).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="border rounded-lg px-3 py-2 text-sm"
          value={form.priority}
          onChange={(e) => set("priority", e.target.value)}
        >
          {(meta?.priorities || ["Low", "Medium", "High", "Critical"]).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <label className="text-xs text-slate-600">
          Filing date
          <input
            type="date"
            className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
            value={form.filing_date}
            onChange={(e) => set("filing_date", e.target.value)}
          />
        </label>
        <label className="text-xs text-slate-600">
          Next hearing
          <input
            type="date"
            className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
            value={form.next_hearing_date}
            onChange={(e) => set("next_hearing_date", e.target.value)}
          />
        </label>
      </section>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-navy text-white px-6 py-2.5 text-sm font-semibold disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create matter workspace"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/matters")}
          className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
