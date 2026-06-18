"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import TimelineSuggestions from "@/components/matters/TimelineSuggestions";

export default function MatterTimelinePanel({ matterId }: { matterId: string }) {
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const d = await api.listMatterTimeline(matterId);
      setEvents(d.events || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load timeline");
      setEvents([]);
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.generateMatterTimeline(matterId, true);
      setMsg(`Generated ${r.inserted ?? 0} timeline event(s).`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Timeline generation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <TimelineSuggestions matterId={matterId} onChanged={load} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void generate()}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Building…" : "Build timeline from documents"}
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
      {msg && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 m-0">
          {msg}
        </p>
      )}
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}
      <ul className="space-y-2">
        {events.map((ev) => (
          <li key={String(ev.event_id)} className="rounded-lg border bg-white p-3 text-sm">
            <span className="text-xs text-slate-500">{String(ev.event_date || "—")}</span>
            <p className="font-semibold text-navy m-0 mt-1">{String(ev.title || "")}</p>
            {ev.description ? (
              <p className="text-slate-600 m-0 mt-1 text-xs">{String(ev.description)}</p>
            ) : null}
          </li>
        ))}
      </ul>
      {!events.length && !busy && !err && (
        <p className="text-sm text-slate-500 m-0">
          No timeline events yet. Upload documents, then build the chronology.
        </p>
      )}
    </div>
  );
}
