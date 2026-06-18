"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import * as api from "@/lib/api";

export default function FirmChatCreateChannelModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (roomId: string) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [desc, setDesc] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const submit = async () => {
    const n = name.trim();
    const s = (slug.trim() || n.toLowerCase().replace(/[^a-z0-9]+/g, "-")).replace(/^-|-$/g, "");
    if (!n || s.length < 2) {
      setErr("Name and slug required");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await api.createCollabChannel({ slug: s, name: n, description: desc.trim() });
      onCreated(r.room.room_id);
      onClose();
      setName("");
      setSlug("");
      setDesc("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create channel");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="firm-chat-modal fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white border border-slate-200 shadow-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-slate-900 m-0">Create practice channel</h3>
        <p className="text-xs text-slate-500 mt-1 mb-4">
          e.g. Criminal Team, Civil Team, Associates — visible to your firm members.
        </p>
        <label className="block text-xs font-medium text-slate-700 mb-1">Display name</label>
        <input
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm mb-3"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Criminal Team"
        />
        <label className="block text-xs font-medium text-slate-700 mb-1">Slug (optional)</label>
        <input
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm mb-3"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="criminal-team"
        />
        <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
        <textarea
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm mb-3 resize-none"
          rows={2}
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        {err && <p className="text-xs text-red-600 mb-2">{err}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={busy}>
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
