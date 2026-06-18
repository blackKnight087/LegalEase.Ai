"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

type DualKb = {
  global_kb?: {
    documents?: number;
    chunks?: number;
    vectors?: number;
    ready?: boolean;
    label?: string;
  };
};

export default function KbScopeHealth({
  matterId = "",
  mode = "knowledge_base",
  warnOnly = false,
}: {
  matterId?: string;
  mode?: string;
  /** On mobile: only show warnings, hide green "ready" banner */
  warnOnly?: boolean;
}) {
  const [kb, setKb] = useState<Awaited<ReturnType<typeof api.fetchKbHealth>> | null>(null);
  const kbModeGlobalOnly = mode === "knowledge_base";

  useEffect(() => {
    if (mode !== "knowledge_base" && mode !== "deep_case" && mode !== "hybrid") {
      setKb(null);
      return;
    }
    let alive = true;
    const load = () => {
      api
        .fetchKbHealth(kbModeGlobalOnly ? undefined : matterId || undefined)
        .then((h) => {
          if (alive) setKb(h);
        })
        .catch(() => {
          if (alive) setKb(null);
        });
    };
    load();
    const t = setInterval(load, 60000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [matterId, mode, kbModeGlobalOnly]);

  if (mode !== "knowledge_base" && mode !== "deep_case" && mode !== "hybrid") return null;
  if (!kb) return null;

  const dual = (kb as { dual_kb?: DualKb }).dual_kb;
  const globalStats = dual?.global_kb;

  const globalVectors =
    globalStats?.vectors ?? kb.faiss_chunks ?? kb.index_vectors ?? 0;
  const globalDocs = globalStats?.documents ?? kb.documents ?? 0;
  const globalReady = globalVectors > 0 && (kb.embeddings_ok ?? kb.embeddings?.ready);
  const indexSparse = globalDocs >= 1 && globalVectors > 0 && globalVectors < 20;

  if (warnOnly && globalReady && !indexSparse) return null;

  if (kbModeGlobalOnly) {
    return (
      <div
        className={`text-[10px] sm:text-[0.65rem] rounded-md sm:rounded-lg border px-2 py-1.5 sm:px-3 sm:py-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 ${
          globalReady
            ? "bg-emerald-50/80 border-emerald-200 text-emerald-900"
            : "bg-amber-50/80 border-amber-200 text-amber-900"
        }`}
      >
        <span className="font-semibold">Global KB</span>
        <span>{globalReady ? "READY" : "NOT READY"}</span>
        <span>{globalDocs} docs</span>
        <span>{globalVectors} vectors</span>
        {indexSparse && (
          <span className="text-amber-800 font-medium">Index sparse — re-index recommended</span>
        )}
        {!globalReady && (
          <Link href="/documents" className="underline font-semibold">
            Re-index global documents
          </Link>
        )}
      </div>
    );
  }

  return (
    <div
      className={`text-[10px] sm:text-[0.65rem] rounded-md sm:rounded-lg border px-2 py-1.5 sm:px-3 sm:py-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 ${
        globalReady
          ? "bg-emerald-50/80 border-emerald-200 text-emerald-900"
          : "bg-amber-50/80 border-amber-200 text-amber-900"
      }`}
    >
      <span className="font-semibold">Global KB</span>
      <span>{globalReady ? "READY" : "NOT READY"}</span>
      <span>{globalDocs} docs</span>
      <span>{globalVectors} vectors</span>
      {indexSparse && (
        <span className="text-amber-800 font-medium">Index sparse — re-index recommended</span>
      )}
      {!globalReady && (
        <Link href="/documents" className="underline font-semibold">
          Re-index global documents
        </Link>
      )}
    </div>
  );
}
