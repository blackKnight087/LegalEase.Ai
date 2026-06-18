"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

type UploadItem = {
  name: string;
  status: "pending" | "uploading" | "done" | "error";
  message?: string;
  documentId?: string;
};

type LinkedDoc = {
  document_id: string;
  filename: string;
  index_status?: string;
};

export default function MatterDocumentUpload({
  matterId,
  onComplete,
}: {
  matterId: string;
  onComplete?: () => void;
}) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [linked, setLinked] = useState<LinkedDoc[]>([]);
  const [drag, setDrag] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(false);

  const refreshLinked = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const dash = await api.getMatterDashboard(matterId);
      const docs = (dash.documents || []) as LinkedDoc[];
      setLinked(docs);
    } catch {
      /* keep prior list */
    } finally {
      setLoadingDocs(false);
    }
  }, [matterId]);

  useEffect(() => {
    void refreshLinked();
  }, [refreshLinked]);

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      setItems((prev) => [
        ...prev,
        ...list.map((f) => ({ name: f.name, status: "pending" as const })),
      ]);
      for (const file of list) {
        setItems((prev) =>
          prev.map((it) =>
            it.name === file.name ? { ...it, status: "uploading" } : it
          )
        );
        try {
          const r = await api.uploadMatterDocument(matterId, file, true);
          setItems((prev) =>
            prev.map((it) =>
              it.name === file.name
                ? {
                    ...it,
                    status: "done",
                    message: r.index_message || "Indexed",
                    documentId: r.document_id,
                  }
                : it
            )
          );
        } catch (e) {
          setItems((prev) =>
            prev.map((it) =>
              it.name === file.name
                ? {
                    ...it,
                    status: "error",
                    message: e instanceof Error ? e.message : "Failed",
                  }
                : it
            )
          );
        }
      }
      await refreshLinked();
      onComplete?.();
    },
    [matterId, onComplete, refreshLinked]
  );

  return (
    <div className="space-y-4">
      <div
        className={`rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          drag ? "border-navy bg-blue-50" : "border-slate-300 bg-slate-50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (e.dataTransfer.files?.length) void uploadFiles(e.dataTransfer.files);
        }}
      >
        <p className="text-sm text-slate-700 m-0 mb-2">
          Drag & drop PDFs or images here, or click to browse
        </p>
        <input
          type="file"
          multiple
          accept=".pdf,image/*"
          className="text-xs"
          onChange={(e) => {
            if (e.target.files?.length) void uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
        {items.length > 0 && (
          <ul className="mt-4 text-left text-xs space-y-1 max-h-32 overflow-y-auto">
            {items.map((it) => (
              <li key={it.name} className="flex justify-between gap-2">
                <span className="truncate">{it.name}</span>
                <span
                  className={
                    it.status === "done"
                      ? "text-emerald-700"
                      : it.status === "error"
                        ? "text-red-600"
                        : "text-slate-500"
                  }
                >
                  {it.status === "uploading" ? "Indexing…" : it.message || it.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <section className="rounded-xl border bg-white p-3">
        <div className="flex items-center justify-between gap-2 mb-2">
          <h4 className="text-xs font-semibold uppercase text-slate-500 m-0">
            Documents in this matter ({linked.length})
          </h4>
          <button
            type="button"
            className="text-xs text-blue-700 hover:underline"
            disabled={loadingDocs}
            onClick={() => void refreshLinked()}
          >
            Refresh
          </button>
        </div>
        {linked.length === 0 && !loadingDocs && (
          <p className="text-xs text-slate-500 m-0">No documents linked yet.</p>
        )}
        {loadingDocs && linked.length === 0 && (
          <p className="text-xs text-slate-500 m-0">Loading…</p>
        )}
        <ul className="space-y-1 m-0 p-0 list-none max-h-40 overflow-y-auto">
          {linked.map((d) => (
            <li
              key={d.document_id}
              className="text-xs flex justify-between gap-2 p-2 rounded-lg bg-slate-50 border"
            >
              <span className="truncate font-medium text-navy">{d.filename}</span>
              <span className="text-slate-500 shrink-0">{d.index_status || "—"}</span>
            </li>
          ))}
        </ul>
        <p className="text-[0.65rem] text-slate-400 mt-2 m-0">
          Files stay linked when you switch tabs. Duplicate uploads re-index into this matter.
        </p>
      </section>
    </div>
  );
}
