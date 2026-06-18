"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

type Change = {
  change_id: string;
  author_name: string;
  original_text: string;
  suggested_text: string;
  status: string;
  change_type: string;
};

type Props = {
  draftId: string;
  selectionText: string;
  onResolved: (doc?: api.WorkspaceDocument) => void;
  onErr: (msg: string) => void;
  onOk: (msg: string) => void;
};

export default function TrackChangesPanel({
  draftId,
  selectionText,
  onResolved,
  onErr,
  onOk,
}: Props) {
  const [changes, setChanges] = useState<Change[]>([]);
  const [suggested, setSuggested] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestionsMode, setSuggestionsMode] = useState(false);

  const load = useCallback(async () => {
    const r = await api.listTrackChanges(draftId);
    setChanges((r.changes as Change[]) || []);
  }, [draftId]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const propose = async () => {
    if (!selectionText.trim() || !suggested.trim()) {
      onErr("Select text in the document and enter suggested wording");
      return;
    }
    setBusy(true);
    try {
      await api.addTrackChange(draftId, {
        original_text: selectionText,
        suggested_text: suggested,
        change_type: "replace",
      });
      setSuggested("");
      await load();
      onOk("Track change proposed");
    } catch (e) {
      onErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const resolve = async (id: string, accept: boolean) => {
    setBusy(true);
    try {
      const r = await api.resolveTrackChange(draftId, id, accept);
      await load();
      if (r.document) onResolved(r.document);
      onOk(accept ? "Change accepted into document" : "Change rejected");
    } catch (e) {
      onErr(e instanceof Error ? e.message : "Resolve failed");
    } finally {
      setBusy(false);
    }
  };

  const pending = changes.filter((c) => c.status === "pending");

  return (
    <div className="p-2 text-xs space-y-3 h-full flex flex-col min-h-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-navy m-0">Track changes</h3>
        <label className="flex items-center gap-1 text-[10px]">
          <input
            type="checkbox"
            checked={suggestionsMode}
            onChange={(e) => setSuggestionsMode(e.target.checked)}
          />
          Suggestions mode
        </label>
      </div>
      {suggestionsMode && (
        <p className="text-slate-500 m-0 bg-amber-50 border border-amber-200 rounded p-2">
          Propose edits without changing the document until accepted. Select text, enter replacement, then Propose.
        </p>
      )}
      <div className="space-y-1 shrink-0">
        <p className="text-slate-500 m-0">Selection: {selectionText ? `"${selectionText.slice(0, 60)}…"` : "none"}</p>
        <textarea
          className="w-full border rounded p-2 h-14"
          placeholder="Suggested replacement text…"
          value={suggested}
          onChange={(e) => setSuggested(e.target.value)}
        />
        <button
          type="button"
          disabled={busy}
          onClick={propose}
          className="w-full py-1.5 bg-navy text-white rounded-lg"
        >
          Propose change
        </button>
      </div>
      <p className="font-medium text-slate-600 m-0">{pending.length} pending</p>
      <ul className="flex-1 overflow-y-auto le-scroll space-y-2 m-0 p-0 list-none">
        {changes.map((c) => (
          <li key={c.change_id} className="border rounded-lg p-2 bg-white">
            <p className="text-[10px] text-slate-500 m-0">
              {c.author_name} · {c.status}
            </p>
            <p className="m-0 mt-1 line-through text-red-800/80">{c.original_text.slice(0, 120)}</p>
            <p className="m-0 mt-1 text-green-800">{c.suggested_text.slice(0, 120)}</p>
            {c.status === "pending" && (
              <div className="flex gap-2 mt-2">
                <button type="button" className="text-green-700 underline" disabled={busy} onClick={() => resolve(c.change_id, true)}>
                  Accept
                </button>
                <button type="button" className="text-red-700 underline" disabled={busy} onClick={() => resolve(c.change_id, false)}>
                  Reject
                </button>
              </div>
            )}
          </li>
        ))}
        {changes.length === 0 && <li className="text-slate-400">No track changes yet.</li>}
      </ul>
    </div>
  );
}
