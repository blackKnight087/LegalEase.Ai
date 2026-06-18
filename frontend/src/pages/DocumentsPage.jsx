import { useCallback, useEffect, useState } from "react";
import * as api from "../api/client.js";
import PageHeader from "../components/PageHeader.jsx";

export default function DocumentsPage() {
  const [data, setData] = useState(null);
  const [kb, setKb] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [meta, setMeta] = useState({});

  const load = useCallback(() => {
    api.fetchDocuments().then(setData).catch((e) => setMsg(e.message));
    api.fetchKbHealth().then(setKb).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onUpload = async (e) => {
    const files = [...(e.target.files || [])];
    if (!files.length) return;
    setBusy(true);
    setMsg("");
    try {
      for (const f of files) await api.uploadDocument(f);
      setMsg(`Uploaded and indexed ${files.length} file(s).`);
      load();
    } catch (err) {
      setMsg(err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const onDelete = async (id) => {
    if (!confirm("Delete this document?")) return;
    setBusy(true);
    try {
      await api.deleteDocument(id);
      setMsg("Document deleted.");
      load();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleDoc = async (id) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!meta[id]) {
      const [tl, ent] = await Promise.all([
        api.fetchDocTimeline(id).catch(() => ({ events: [] })),
        api.fetchDocEntities(id).catch(() => ({ entities: null })),
      ]);
      setMeta((m) => ({ ...m, [id]: { timeline: tl.events, entities: ent.entities } }));
    }
  };

  return (
    <>
      <PageHeader title="Document Management" subtitle="Upload PDFs for Knowledge Base intelligence" />
      <div className="flex-1 overflow-y-auto le-scroll p-8">
        {kb && (
          <div className="mb-6 p-4 bg-white rounded-xl border border-slate-200 text-sm">
            <span className="font-semibold text-navy">KB Status:</span>{" "}
            <span className="text-slate-600">{kb.status}</span> · {kb.documents} docs · {kb.chunks} chunks
            {kb.index_exists ? " · ✅ index ready" : " · ⚠️ index missing"}
          </div>
        )}

        <p className="text-sm text-slate-600 mb-4">
          {data?.membership === "Free"
            ? `Free plan: ${data?.count ?? 0} / ${data?.free_limit ?? 2} documents`
            : `${data?.count ?? 0} documents (unlimited)`}
        </p>

        <div className="flex flex-wrap gap-3 mb-6">
          <label className="px-4 py-2.5 bg-navy text-white rounded-xl text-sm font-semibold cursor-pointer hover:bg-slate-800">
            {busy ? "Working…" : "Upload PDF(s)"}
            <input type="file" accept=".pdf" multiple className="hidden" onChange={onUpload} disabled={busy} />
          </label>
          <button
            type="button"
            onClick={async () => {
              setBusy(true);
              try {
                await api.reindexDocuments();
                setMsg("Knowledge base re-indexed.");
                load();
              } catch (e) {
                setMsg(e.message);
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold hover:border-navy"
          >
            Re-index all
          </button>
        </div>

        {msg && <p className="text-sm mb-4 text-slate-700">{msg}</p>}

        <div className="space-y-2 max-w-3xl">
          {(data?.documents || []).map((d) => (
            <div key={d.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <button
                type="button"
                onClick={() => toggleDoc(d.id)}
                className="w-full flex justify-between items-center px-4 py-3 text-left hover:bg-slate-50"
              >
                <span className="font-medium text-sm">📄 {d.filename}</span>
                <span className="text-xs text-slate-400">{d.pages} pg</span>
              </button>
              {expanded === d.id && (
                <div className="px-4 pb-4 border-t border-slate-100 text-sm space-y-3">
                  {meta[d.id]?.entities && (
                    <div className="grid grid-cols-2 gap-2 text-xs text-slate-600">
                      <p><b>Plaintiff:</b> {meta[d.id].entities.plaintiff || "N/A"}</p>
                      <p><b>Defendant:</b> {meta[d.id].entities.defendant || "N/A"}</p>
                      <p><b>Court:</b> {meta[d.id].entities.court || "N/A"}</p>
                      <p><b>Sections:</b> {meta[d.id].entities.sections || "N/A"}</p>
                    </div>
                  )}
                  {meta[d.id]?.timeline?.length > 0 && (
                    <ul className="text-xs text-slate-600 space-y-1">
                      {meta[d.id].timeline.slice(0, 5).map((ev, i) => (
                        <li key={i}><b>{ev.date}:</b> {(ev.text || "").slice(0, 80)}</li>
                      ))}
                    </ul>
                  )}
                  <button
                    type="button"
                    onClick={() => onDelete(d.id)}
                    className="text-red-600 text-xs font-semibold hover:underline"
                  >
                    Delete document
                  </button>
                </div>
              )}
            </div>
          ))}
          {!data?.documents?.length && (
            <p className="text-sm text-slate-400 py-12 text-center border border-dashed rounded-xl">
              No documents yet.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
