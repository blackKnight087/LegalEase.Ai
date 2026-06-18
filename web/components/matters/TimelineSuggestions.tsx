"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

export default function TimelineSuggestions({
  matterId,
  onChanged,
}: {
  matterId: string;
  onChanged?: () => void;
}) {
  const [items, setItems] = useState<Array<Record<string, string>>>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await api.listTimelineSuggestions(matterId);
    setItems(r.suggestions || []);
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!items.length) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 space-y-2">
      <p className="text-xs font-semibold text-amber-900 m-0">
        AI suggested timeline events (from indexed documents)
      </p>
      <ul className="space-y-2 max-h-48 overflow-y-auto">
        {items.map((s) => (
          <li key={s.suggestion_id} className="text-xs bg-white rounded-lg border p-2">
            <span className="text-slate-500">{s.event_date}</span>
            <b className="block text-navy">{s.title}</b>
            {s.description && <p className="m-0 text-slate-600">{s.description}</p>}
            <div className="flex gap-2 mt-2">
              <button
                type="button"
                disabled={busy}
                className="px-2 py-1 bg-emerald-700 text-white rounded text-[0.65rem]"
                onClick={async () => {
                  setBusy(true);
                  await api.approveTimelineSuggestion(matterId, s.suggestion_id);
                  await load();
                  onChanged?.();
                  setBusy(false);
                }}
              >
                Approve
              </button>
              <button
                type="button"
                disabled={busy}
                className="px-2 py-1 border rounded text-[0.65rem]"
                onClick={async () => {
                  setBusy(true);
                  await api.rejectTimelineSuggestion(matterId, s.suggestion_id);
                  await load();
                  setBusy(false);
                }}
              >
                Dismiss
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
