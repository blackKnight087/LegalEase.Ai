"use client";

import { useState } from "react";
import * as api from "@/lib/api";

export default function MatterDeleteModal({
  matterId,
  matterName,
  open,
  onClose,
  onDeleted,
}: {
  matterId: string;
  matterName: string;
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;

  const canDelete = confirm.trim() === matterName.trim();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-5 space-y-3">
        <h3 className="text-lg font-semibold text-navy m-0">Delete matter</h3>
        <p className="text-sm text-slate-600 m-0">
          This removes the matter, unlinks documents, and deletes its search index. Type the
          matter name to confirm:
        </p>
        <p className="text-sm font-mono bg-slate-100 px-2 py-1 rounded">{matterName}</p>
        <input
          className="w-full border rounded-lg px-3 py-2 text-sm"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Matter name"
        />
        {err && <p className="text-red-600 text-xs m-0">{err}</p>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">
            Cancel
          </button>
          <button
            type="button"
            disabled={!canDelete || busy}
            onClick={async () => {
              setBusy(true);
              setErr("");
              try {
                await api.deleteMatter(matterId);
                onDeleted();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Delete failed");
              } finally {
                setBusy(false);
              }
            }}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg disabled:opacity-50"
          >
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
