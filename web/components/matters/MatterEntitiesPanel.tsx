"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  victim: "Victims",
  accused: "Accused",
  witness: "Witnesses",
  person: "Persons",
  judge: "Judges",
  lawyer: "Lawyers",
  police: "Police",
  court: "Courts",
  law: "Laws (IPC)",
  section: "Sections",
  statute: "Laws",
  fir: "FIR",
  case_number: "Case numbers",
  police_station: "Police stations",
  reference: "References",
  date: "Dates",
  location: "Locations",
  organization: "Organizations",
  phone: "Phone numbers",
  email: "Emails",
  document: "Documents",
};

const TYPE_ORDER = [
  "victim",
  "accused",
  "witness",
  "person",
  "law",
  "section",
  "statute",
  "court",
  "location",
  "police_station",
  "fir",
  "case_number",
  "date",
  "organization",
  "reference",
  "judge",
  "lawyer",
  "police",
  "phone",
  "email",
];

export default function MatterEntitiesPanel({ matterId }: { matterId: string }) {
  const [entities, setEntities] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.listMatterEntities(matterId);
      setEntities(r.entities || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load entities");
      setEntities([]);
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await api.getMatterIntelStatus(matterId);
        const stage = String(s.stage || "idle");
        if (stage === "ready" || stage === "failed") await load();
      } catch {
        /* ignore */
      }
    };
    void poll();
    const t = setInterval(() => void poll(), 5000);
    return () => clearInterval(t);
  }, [matterId, load]);

  const extract = async () => {
    setBusy(true);
    setErr("");
    setSuccess("");
    try {
      const r = await api.extractMatterEntities(matterId);
      setEntities(r.entities || []);
      if (r.count) {
        setSuccess(`Extracted ${r.count} entities.`);
      } else {
        setErr("No entities found. Ensure documents contain names, courts, and IPC sections.");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Entity extraction failed");
    } finally {
      setBusy(false);
    }
  };

  const grouped = entities.reduce<Record<string, Array<Record<string, unknown>>>>((acc, ent) => {
    const t = String(ent.entity_type || "other");
    if (!acc[t]) acc[t] = [];
    acc[t].push(ent);
    return acc;
  }, {});

  const sortedTypes = [
    ...TYPE_ORDER.filter((t) => grouped[t]?.length),
    ...Object.keys(grouped).filter((t) => !TYPE_ORDER.includes(t)),
  ];

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void extract()}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Extracting…" : "Extract entities"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          Refresh
        </button>
      </div>
      {success && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 m-0">
          {success}
        </p>
      )}
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}
      {sortedTypes.map((type) => {
        const list = grouped[type] || [];
        return (
          <section key={type}>
            <h3 className="text-xs font-semibold uppercase text-slate-500 mb-2">
              {TYPE_LABELS[type] || type} ({list.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {list.map((ent) => {
                const meta = (ent.metadata || {}) as Record<string, string>;
                const role = meta.role ? ` (${meta.role})` : "";
                return (
                  <span
                    key={String(ent.entity_id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 text-sm text-navy border"
                    title={`Confidence: ${ent.confidence}`}
                  >
                    {String(ent.label)}
                    {role && <span className="text-slate-500 text-xs">{role}</span>}
                  </span>
                );
              })}
            </div>
          </section>
        );
      })}
      {!entities.length && !busy && !err && (
        <p className="text-sm text-slate-500 m-0">
          No entities yet. Upload documents, then extract — or wait for automatic analysis after upload.
        </p>
      )}
    </div>
  );
}
