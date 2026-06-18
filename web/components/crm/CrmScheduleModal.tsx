"use client";

import { useEffect, useState } from "react";

type Props = {
  open: boolean;
  leadName: string;
  busy?: boolean;
  onClose: () => void;
  onConfirm: (scheduledAt: string, note: string) => void;
};

export default function CrmScheduleModal({
  open,
  leadName,
  busy,
  onClose,
  onConfirm,
}: Props) {
  const [scheduledAt, setScheduledAt] = useState("");
  const [note, setNote] = useState("Initial consultation with client.");

  useEffect(() => {
    if (!open) return;
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(10, 0, 0, 0);
    const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    setScheduledAt(local);
    setNote("Initial consultation with client.");
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-navy/40" onClick={busy ? undefined : onClose} aria-hidden />
      <div className="relative bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md p-5">
        <h3 className="text-lg font-bold text-navy">Schedule consultation</h3>
        <p className="text-sm text-slate-600 mt-1">{leadName}</p>
        <label className="block mt-4 text-xs font-semibold text-slate-500 uppercase">
          Date & time
          <input
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            disabled={busy}
            className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-normal text-slate-800"
          />
        </label>
        <label className="block mt-3 text-xs font-semibold text-slate-500 uppercase">
          Notes
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={busy}
            rows={3}
            className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-normal text-slate-800"
          />
        </label>
        <div className="flex gap-2 mt-5">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="flex-1 text-sm font-semibold py-2 rounded-lg border border-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !scheduledAt}
            onClick={() => onConfirm(scheduledAt, note.trim())}
            className="flex-1 text-sm font-semibold py-2 rounded-lg bg-navy text-white disabled:opacity-50"
          >
            {busy ? "Saving…" : "Confirm schedule"}
          </button>
        </div>
      </div>
    </div>
  );
}
