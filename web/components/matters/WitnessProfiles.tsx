"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";

export default function WitnessProfiles({ matterId }: { matterId: string }) {
  const [profiles, setProfiles] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setBusy(true);
    api
      .fetchEntityProfiles(matterId)
      .then((r) => setProfiles(r.profiles || []))
      .finally(() => setBusy(false));
  };

  useEffect(() => {
    load();
  }, [matterId]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            api.extractMatterEntities(matterId).then(load).finally(() => setBusy(false));
          }}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
        >
          Refresh entities
        </button>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {profiles.map((p) => (
          <div
            key={String(p.entity_id)}
            className="rounded-xl border bg-white p-4 shadow-sm space-y-2"
          >
            <div className="flex justify-between items-start">
              <h3 className="font-semibold text-navy m-0">{String(p.label)}</h3>
              <span className="text-[0.65rem] uppercase text-slate-500">{String(p.role)}</span>
            </div>
            {(p.quotes as Array<Record<string, string>>)?.length ? (
              <ul className="text-xs space-y-2 m-0 pl-0 list-none">
                {(p.quotes as Array<Record<string, string>>).map((q, i) => (
                  <li key={i} className="bg-slate-50 border-l-2 border-navy pl-2 py-1">
                    <p className="m-0 text-slate-700 italic">&ldquo;{q.text?.slice(0, 280)}&rdquo;</p>
                    {q.filename && (
                      <span className="text-slate-400">{q.filename}</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500 m-0">No excerpts found yet.</p>
            )}
          </div>
        ))}
      </div>
      {!profiles.length && !busy && (
        <p className="text-sm text-slate-500">Run entity extraction from the Knowledge tab first.</p>
      )}
    </div>
  );
}
