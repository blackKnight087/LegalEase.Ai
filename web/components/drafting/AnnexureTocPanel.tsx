"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

type Props = {
  draftId: string;
  onDocumentUpdate: (doc: api.WorkspaceDocument) => void;
  onErr: (msg: string) => void;
  onOk: (msg: string) => void;
};

export default function AnnexureTocPanel({ draftId, onDocumentUpdate, onErr, onOk }: Props) {
  const [annexures, setAnnexures] = useState<Array<{ annexure_id: string; label: string; content: string }>>([]);
  const [label, setLabel] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await api.listDraftAnnexures(draftId);
    setAnnexures(r.annexures || []);
  }, [draftId]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  return (
    <div className="p-2 text-xs space-y-3 overflow-y-auto le-scroll">
      <h3 className="font-semibold text-navy">TOC & annexures</h3>
      <div className="flex flex-col gap-1">
        <button
          type="button"
          disabled={busy}
          className="py-1.5 bg-navy text-white rounded-lg"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.insertDocumentToc(draftId);
              onDocumentUpdate(r.document);
              onOk("Table of contents inserted at top");
            } catch (e) {
              onErr(e instanceof Error ? e.message : "TOC failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Insert table of contents
        </button>
        <button
          type="button"
          disabled={busy}
          className="py-1.5 border rounded-lg"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.insertAnnexureIndex(draftId);
              onDocumentUpdate(r.document);
              onOk("Annexure index inserted");
            } catch (e) {
              onErr(e instanceof Error ? e.message : "Index failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Insert annexure index
        </button>
      </div>

      <div className="border-t pt-2">
        <p className="font-medium m-0 mb-1">Annexures ({annexures.length})</p>
        <ul className="space-y-1 m-0 p-0 list-none mb-2">
          {annexures.map((a) => (
            <li key={a.annexure_id} className="border rounded p-1.5 bg-white">
              <strong>{a.label}</strong>
              <p className="m-0 text-slate-500 line-clamp-2">{a.content || "—"}</p>
            </li>
          ))}
        </ul>
        <input className="w-full border rounded px-2 py-1 mb-1" placeholder="Annexure A — label" value={label} onChange={(e) => setLabel(e.target.value)} />
        <textarea className="w-full border rounded p-2 h-12 mb-1" placeholder="Content summary" value={content} onChange={(e) => setContent(e.target.value)} />
        <button
          type="button"
          disabled={busy || !label.trim()}
          className="w-full py-1.5 border rounded-lg"
          onClick={async () => {
            setBusy(true);
            try {
              await api.addDraftAnnexure(draftId, label, content);
              setLabel("");
              setContent("");
              await load();
              onOk("Annexure added");
            } catch (e) {
              onErr(e instanceof Error ? e.message : "Failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Add annexure
        </button>
      </div>
    </div>
  );
}
