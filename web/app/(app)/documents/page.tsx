"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import KbHealthPanel from "@/components/documents/KbHealthPanel";
import * as api from "@/lib/api";

const ACCEPT_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "image/bmp",
  "image/tiff",
];

const ACCEPT_EXT = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"];

function isAllowedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return (
    ACCEPT_TYPES.includes(file.type) ||
    ACCEPT_EXT.some((ext) => name.endsWith(ext))
  );
}

function uploadKindHint(files: File[]): string {
  const hasImage = files.some(
    (f) => f.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(f.name)
  );
  if (hasImage) {
    return "Uploading image (OCR runs automatically — first load may take 1–2 min)…";
  }
  return "Uploading file (indexing runs in background)…";
}

export default function DocumentsPage() {
  const [data, setData] = useState<api.DocumentsListResponse | null>(null);
  const [kb, setKb] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [msg, setMsg] = useState("");
  const [smokeResult, setSmokeResult] = useState<api.KbSmokeTestResult | null>(null);
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState("");
  const [meta, setMeta] = useState<
    Record<string, { timeline: Array<{ date: string; text: string }>; entities: Record<string, string> | null }>
  >({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadingRef = useRef(false);

  const appendSmokeResult = useCallback(async (scopeMatterId: string) => {
    try {
      const smoke = await api.runKbSmokeTest(scopeMatterId);
      setSmokeResult(smoke);
      if (smoke.skipped) {
        setMsg(
          `Smoke test deferred: ${smoke.reason || "system busy"}. Try again when chat is idle.`
        );
        return;
      }
      if (smoke.ok) {
        setMsg(
          `✅ KB smoke test passed (${smoke.passed ?? 0} queries, ${smoke.faiss_vectors ?? 0} vectors, ${smoke.total_latency_ms ?? 0}ms).`
        );
      } else {
        const failed = smoke.failed ?? 0;
        setMsg(
          `⚠️ KB smoke test: ${failed} failed, ${smoke.passed ?? 0} passed. See results below.`
        );
      }
    } catch (e) {
      const err = e instanceof Error ? e.message : "Smoke test failed";
      setMsg(err);
      setSmokeResult({ ok: false, error: err, queries: [] });
    }
  }, []);

  const load = useCallback(() => {
    setMsg("");
    Promise.all([
      api.fetchDocuments().then(setData),
      api.fetchKbHealth(matterId).then(setKb),
      api.listMatters().then((r) => {
        setMatters(r.matters || []);
      }),
    ]).catch((e) => {
      setMsg(e instanceof Error ? e.message : "Failed to load documents");
    });
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  const embeddingsReady = Boolean(
    kb?.embeddings_ok ?? (kb?.embeddings as { ready?: boolean } | undefined)?.ready
  );

  // Poll KB health while embeddings preload — slow interval to avoid API overload at high RAM.
  useEffect(() => {
    if (embeddingsReady) return;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      api.fetchKbHealth(matterId).then(setKb).catch(() => {});
    };
    tick();
    const id = window.setInterval(tick, 15000);
    return () => clearInterval(id);
  }, [embeddingsReady, matterId]);

  const uploadFiles = useCallback(
    async (files: File[]) => {
      const allowed = files.filter(isAllowedFile);
      if (!allowed.length) {
        setMsg("Please drop PDF or image files (PNG, JPG, WEBP, GIF, BMP, TIFF).");
        return;
      }
      if (uploadingRef.current) return;
      uploadingRef.current = true;
      setBusy(true);
      setMsg(
        ocrEnabled
          ? "Uploading with OCR (first image may take 1–2 min while EasyOCR loads)…"
          : uploadKindHint(files)
      );
      try {
        let lastMsg = "";
        for (const f of allowed) {
          const isImage =
            f.type.startsWith("image/") ||
            /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(f.name);
          const useOcr = isImage || ocrEnabled;
          const res = await api.uploadDocument(f, useOcr, matterId);
          if (res.index_message?.includes("duplicate")) {
            lastMsg = `${res.document_name}: already in library (duplicate skipped).`;
          } else if (res.index_job_id && res.indexing_async) {
            setMsg(`Indexing ${res.document_name} in background…`);
            const job = await api.waitForIndexJob(res.index_job_id, (m) =>
              setMsg(`Indexing ${res.document_name}: ${m}`)
            );
            if (job.status === "completed" && job.indexing_ok) {
              lastMsg = `✅ ${res.document_name} — indexed (${job.chunks_added ?? "?"} chunks in KB).`;
            } else {
              lastMsg = `⚠️ ${res.document_name}: ${job.message || "Indexing failed"}`;
            }
          } else if (
            res.error_code === "ZERO_CHUNKS" ||
            (res.indexing_ok === false &&
              !res.indexing_async &&
              res.error_code !== "INDEXING")
          ) {
            lastMsg =
              `⚠️ ${res.document_name}: indexing failed — 0 searchable chunks. ` +
              (res.user_action || res.index_message || "Try Re-index with OCR.");
          } else if (res.index_message && !res.indexed) {
            lastMsg = `⚠️ ${res.document_name}: ${res.index_message}`;
          } else {
            lastMsg = `✅ ${res.document_name} — ${res.index_vectors ?? res.chunks_added} vectors indexed (${res.index_scope || "KB"}).`;
          }
        }
        setMsg(lastMsg || `Uploaded ${allowed.length} file(s).`);
        await api.syncKbStatus().catch(() => {});
        load();
      } catch (err) {
        setMsg(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setBusy(false);
        uploadingRef.current = false;
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [ocrEnabled, matterId, load]
  );

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = [...(e.target.files || [])];
    if (!files.length) return;
    await uploadFiles(files);
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (busy) return;
    const files = [...e.dataTransfer.files];
    await uploadFiles(files);
  };

  const onAutoReindex = async () => {
    setBusy(true);
    setMsg(
      "Loading embeddings and starting re-index in background (API stays online)…"
    );
    try {
      const r = await api.autoReindexKb();
      if (r.index_job_id) {
        setMsg(r.message || "Auto-fix running in background…");
        const job = await api.waitForIndexJob(r.index_job_id, (m) => setMsg(m));
        if (job.status === "completed" && job.indexing_ok) {
          setMsg(`✅ Auto-fix complete — ${job.chunks_added ?? "?"} chunks in knowledge base.`);
          await appendSmokeResult(matterId);
        } else {
          setMsg(`⚠️ Auto-fix failed: ${job.message || "unknown error"}`);
        }
      } else {
        setMsg(r.message || (r.reindexed ? "Index repaired." : "Index already healthy."));
      }
      await api.syncKbStatus().catch(() => {});
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Auto-fix failed");
    } finally {
      setBusy(false);
    }
  };

  const onReindex = async () => {
    setBusy(true);
    setMsg(
      ocrEnabled
        ? "Re-indexing all documents (with OCR — slower)…"
        : "Re-indexing all documents (fast path)…"
    );
    try {
      const r = await api.reindexDocuments(ocrEnabled, matterId);
      if (r.index_job_id) {
        setMsg(r.message || "Re-indexing in background…");
        const job = await api.waitForIndexJob(r.index_job_id, (m) => setMsg(m));
        if (job.status === "completed" && job.indexing_ok) {
          setMsg(`✅ Re-index complete — ${job.chunks_added ?? "?"} chunks in knowledge base.`);
          await appendSmokeResult(matterId);
        } else {
          setMsg(`⚠️ Re-index failed: ${job.message || "unknown error"}`);
        }
      } else {
        setMsg(r.message || `Re-indexed — ${r.chunks_added} chunks in knowledge base.`);
        await appendSmokeResult(matterId);
      }
      await api.syncKbStatus().catch(() => {});
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Re-index failed");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this document?")) return;
    setBusy(true);
    try {
      await api.deleteDocument(id);
      setMsg("Document deleted and knowledge base refreshed.");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleDoc = async (id: string) => {
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
      setMeta((m) => ({
        ...m,
        [id]: { timeline: tl.events || [], entities: ent.entities },
      }));
    }
  };

  const maxMb = data?.max_upload_mb ?? 200;

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Document Management"
        subtitle={`Upload PDFs or images (up to ${maxMb} MB). Drag and drop or browse.`}
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-6xl mx-auto w-full">
        <KbHealthPanel
          kb={
            (kb ?? api.EMPTY_KB_HEALTH) as Parameters<
              typeof KbHealthPanel
            >[0]["kb"]
          }
          loading={!kb}
          onAutoReindex={onAutoReindex}
          smokeResult={smokeResult}
          onSmokeTest={async () => {
            setBusy(true);
            setMsg("Running KB smoke test (fast retrieval check)…");
            setSmokeResult(null);
            try {
              await appendSmokeResult(matterId);
              load();
            } finally {
              setBusy(false);
            }
          }}
          busy={busy}
        />

        <p className="text-sm text-slate-600 mb-4 max-w-3xl">
          {data?.membership === "Free" ? (
            <>
              Free plan: {data?.count ?? 0} / {data?.free_limit ?? 2} documents
              {(data?.count ?? 0) >= (data?.free_limit ?? 2) && (
                <>
                  {" "}
                  —{" "}
                  <a href="/settings/subscription" className="text-blue-700 font-medium hover:underline">
                    Upgrade to upload more
                  </a>
                </>
              )}
            </>
          ) : (
            `${data?.count ?? 0} documents (unlimited)`
          )}
        </p>

        <div className="grid md:grid-cols-2 gap-4 mb-6 max-w-4xl">
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="font-semibold text-navy text-sm mb-2">📤 Upload Documents</h3>
            <p className="text-xs text-slate-500 mb-3">
              Drag PDFs or images here (up to {maxMb} MB). Text PDFs: leave OCR off.
              Scanned PDFs or photos: enable OCR.
            </p>

            <div
              role="button"
              tabIndex={0}
              onDragEnter={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setDragOver(false);
              }}
              onDrop={onDrop}
              onClick={() => !busy && fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              className={`mb-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors cursor-pointer ${
                dragOver
                  ? "border-blue-500 bg-blue-50"
                  : "border-slate-300 bg-slate-50 hover:border-slate-400 hover:bg-slate-100"
              } ${busy ? "opacity-60 pointer-events-none" : ""}`}
            >
              <p className="text-sm font-medium text-slate-700">
                {busy ? "Working…" : "Drop PDF or image files here"}
              </p>
              <p className="text-xs text-slate-500 mt-1">or click to browse</p>
              <p className="text-[0.65rem] text-slate-400 mt-2">
                PDF · PNG · JPG · WEBP · GIF · BMP · TIFF
              </p>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_EXT.join(",")}
              multiple
              className="hidden"
              onChange={onUpload}
              disabled={busy}
            />

            {matters.length > 0 && (
              <label className="block text-xs text-slate-600 mb-2">
                Link to matter (optional)
                <select
                  className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm"
                  value={matterId}
                  onChange={(e) => setMatterId(e.target.value)}
                  disabled={busy}
                >
                  <option value="">— None —</option>
                  {matters.map((m) => (
                    <option key={m.matter_id} value={m.matter_id}>
                      {m.matter_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="flex items-center gap-2 text-sm text-slate-700 mb-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ocrEnabled}
                onChange={(e) => setOcrEnabled(e.target.checked)}
                disabled={busy}
                className="rounded border-slate-300"
              />
              Enable OCR for scanned PDFs (images always use OCR)
            </label>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="font-semibold text-navy text-sm mb-2">🔄 Build Knowledge Base</h3>
            <p className="text-xs text-slate-500 mb-3">
              Re-index all uploaded files: OCR pass + entity extraction + FAISS indexing.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={onReindex}
              className="w-full py-2.5 border border-slate-300 rounded-lg text-sm font-semibold hover:border-navy disabled:opacity-50"
            >
              Re-index all
            </button>
          </div>
        </div>

        {msg && (
          <p
            className={`text-sm mb-6 max-w-3xl px-4 py-2 rounded-lg border ${
              msg.startsWith("⚠️") ||
              msg.toLowerCase().includes("fail") ||
              msg.includes("error") ||
              msg.includes("0 searchable") ||
              msg.includes("OCR failed") ||
              msg.includes("No text detected") ||
              msg.includes("'tuple'")
                ? "text-red-700 bg-red-50 border-red-200"
                : msg.startsWith("✅")
                  ? "text-emerald-800 bg-emerald-50 border-emerald-200"
                  : msg.includes("saved") && msg.toLowerCase().includes("index")
                    ? "text-amber-800 bg-amber-50 border-amber-200"
                    : "text-slate-700 bg-slate-50 border-slate-200"
            }`}
          >
            {msg}
          </p>
        )}

        <h3 className="font-semibold text-navy mb-3 text-sm">📋 Your Documents</h3>
        <div className="space-y-2 max-w-3xl">
          {(data?.documents || []).map((d) => (
            <div
              key={d.id}
              className="bg-white rounded-xl border border-slate-200 overflow-hidden"
            >
              <button
                type="button"
                onClick={() => toggleDoc(d.id)}
                className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-slate-50"
              >
                <span className="text-lg shrink-0">📄</span>
                <span className="font-medium text-sm text-slate-800 flex-1 truncate">
                  {d.filename}
                </span>
                <span className="text-xs text-slate-400 shrink-0">— {d.pages} pages</span>
              </button>
              {expanded === d.id && (
                <div className="px-4 pb-4 border-t border-slate-100 text-sm space-y-3">
                  {meta[d.id]?.entities && (
                    <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 pt-2">
                      <p>
                        <b>Plaintiff:</b> {meta[d.id].entities?.plaintiff || "N/A"}
                      </p>
                      <p>
                        <b>Defendant:</b> {meta[d.id].entities?.defendant || "N/A"}
                      </p>
                      <p>
                        <b>Court:</b> {meta[d.id].entities?.court || "N/A"}
                      </p>
                      <p>
                        <b>Sections:</b> {meta[d.id].entities?.sections || "N/A"}
                      </p>
                    </div>
                  )}
                  {meta[d.id]?.timeline && meta[d.id].timeline.length > 0 && (
                    <ul className="text-xs text-slate-600 space-y-1">
                      {meta[d.id].timeline.slice(0, 5).map((ev, i) => (
                        <li key={i}>
                          <b>{ev.date}:</b> {(ev.text || "").slice(0, 80)}
                        </li>
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
          {!data?.documents?.length && !busy && (
            <p className="text-sm text-slate-400 py-12 text-center border border-dashed rounded-xl">
              No documents yet. Drag a PDF or image above to enable Knowledge Base search.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
