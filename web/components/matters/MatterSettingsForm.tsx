"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import MatterDeleteModal from "@/components/matters/MatterDeleteModal";

export default function MatterSettingsForm({
  matterId,
  onSaved,
  onDeleted,
}: {
  matterId: string;
  onSaved?: () => void;
  onDeleted?: () => void;
}) {
  const [m, setM] = useState<api.Matter | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showDelete, setShowDelete] = useState(false);
  const [members, setMembers] = useState<Array<Record<string, string>>>([]);
  const [newMemberId, setNewMemberId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("viewer");
  const [audit, setAudit] = useState<Array<Record<string, string>>>([]);

  useEffect(() => {
    api.getMatter(matterId).then(setM);
    api.listMatterMembers(matterId).then((r) => setMembers(r.members || []));
    api.fetchMatterAudit(matterId).then((r) => setAudit(r.audit || []));
  }, [matterId]);

  if (!m) return <p className="text-sm text-slate-500">Loading…</p>;

  const field = (label: string, key: keyof api.Matter, type = "text") => (
    <label className="block text-xs text-slate-600">
      {label}
      <input
        type={type}
        className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
        value={String(m[key] ?? "")}
        onChange={(e) => setM({ ...m, [key]: e.target.value })}
      />
    </label>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      {err && <p className="text-red-600 text-sm">{err}</p>}

      <section className="rounded-xl border bg-white p-4 grid md:grid-cols-2 gap-3">
        <h2 className="md:col-span-2 text-sm font-semibold text-navy m-0">Edit matter</h2>
        {field("Matter name", "matter_name")}
        {field("Matter type", "matter_type")}
        {field("Client", "client_name")}
        {field("Opposing party", "opposing_party")}
        {field("Court / venue", "venue")}
        {field("Case number", "case_number")}
        {field("FIR number", "fir_number")}
        {field("Police station", "police_station")}
        {field("Status", "status_tier")}
        {field("Priority", "priority")}
        {field("Filing date", "filing_date", "date")}
        {field("Next hearing", "next_hearing_date", "date")}
        <label className="md:col-span-2 block text-xs text-slate-600">
          Description
          <textarea
            className="mt-1 w-full border rounded-lg px-3 py-2 text-sm min-h-[80px]"
            value={m.description || ""}
            onChange={(e) => setM({ ...m, description: e.target.value })}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          className="md:col-span-2 px-4 py-2 bg-navy text-white rounded-lg text-sm w-fit"
          onClick={async () => {
            setBusy(true);
            setErr("");
            try {
              const payload = {
                matter_name: m.matter_name,
                matter_type: m.matter_type,
                client_name: m.client_name,
                opposing_party: m.opposing_party,
                venue: m.venue,
                case_number: m.case_number,
                fir_number: m.fir_number,
                police_station: m.police_station,
                status_tier: m.status_tier,
                priority: m.priority,
                filing_date: m.filing_date,
                next_hearing_date: m.next_hearing_date,
                description: m.description,
              };
              await api.updateMatter(matterId, payload);
              // #region agent log
              fetch("http://127.0.0.1:7875/ingest/c3dd2ac2-3927-41bb-8511-dee0b46f3309", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "cf6ca9" },
                body: JSON.stringify({
                  sessionId: "cf6ca9",
                  hypothesisId: "H4",
                  location: "MatterSettingsForm.tsx:save",
                  message: "matter_saved",
                  data: { matterId, keys: Object.keys(payload) },
                  timestamp: Date.now(),
                }),
              }).catch(() => {});
              // #endregion
              onSaved?.();
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Save failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Save changes
        </button>
      </section>

      <section className="rounded-xl border bg-white p-4 space-y-2">
        <h2 className="text-sm font-semibold text-navy m-0">Export</h2>
        <button
          type="button"
          className="px-4 py-2 border rounded-lg text-sm"
          onClick={async () => {
            const blob = await api.exportMatterPack(matterId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${m.matter_name || "matter"}_pack.zip`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Download matter pack (ZIP)
        </button>
      </section>

      <section className="rounded-xl border bg-white p-4 space-y-2">
        <h2 className="text-sm font-semibold text-navy m-0">Team access (preview)</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded-lg px-2 py-1.5 text-sm"
            placeholder="User ID"
            value={newMemberId}
            onChange={(e) => setNewMemberId(e.target.value)}
          />
          <select
            className="border rounded-lg px-2 text-sm"
            value={newMemberRole}
            onChange={(e) => setNewMemberRole(e.target.value)}
          >
            <option value="lawyer">Lawyer</option>
            <option value="associate">Associate</option>
            <option value="client">Client</option>
            <option value="viewer">Viewer</option>
          </select>
          <button
            type="button"
            className="px-3 py-1.5 bg-slate-800 text-white rounded-lg text-sm"
            onClick={async () => {
              if (!newMemberId.trim()) return;
              await api.addMatterMember(matterId, newMemberId.trim(), newMemberRole);
              const r = await api.listMatterMembers(matterId);
              setMembers(r.members || []);
              setNewMemberId("");
            }}
          >
            Add
          </button>
        </div>
        <ul className="text-xs space-y-1">
          {members.map((mb) => (
            <li key={mb.member_id}>
              {mb.user_id} — {mb.role}
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border bg-white p-4">
        <h2 className="text-sm font-semibold text-navy m-0 mb-2">Audit log</h2>
        <ul className="text-xs max-h-40 overflow-y-auto space-y-1">
          {audit.map((a) => (
            <li key={a.log_id}>
              <span className="text-slate-500">{a.created_at}</span> {a.action}: {a.detail}
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-red-200 bg-red-50 p-4">
        <button
          type="button"
          onClick={() => setShowDelete(true)}
          className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm"
        >
          Delete matter…
        </button>
      </section>

      <MatterDeleteModal
        matterId={matterId}
        matterName={m.matter_name || ""}
        open={showDelete}
        onClose={() => setShowDelete(false)}
        onDeleted={() => onDeleted?.()}
      />
    </div>
  );
}
