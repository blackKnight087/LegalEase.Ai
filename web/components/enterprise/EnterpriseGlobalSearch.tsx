"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import type { EnterpriseModule } from "@/lib/enterpriseWorkspace";

const TYPE_LABELS: Record<string, string> = {
  document: "Document",
  matter: "Matter",
  order: "Court order",
  knowledge: "Knowledge",
  note: "Note",
  client: "Client",
  clause: "Clause",
};

export default function EnterpriseGlobalSearch({
  onNavigate,
  onSelectMatter,
  inHeader = false,
}: {
  onNavigate: (m: EnterpriseModule) => void;
  onSelectMatter?: (matterId: string) => void;
  inHeader?: boolean;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const search = useCallback(async (query: string) => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setBusy(true);
    try {
      const r = await api.enterpriseGlobalSearch(query);
      setResults(r.results || []);
      setOpen(true);
    } catch {
      setResults([]);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => search(q), 280);
    return () => clearTimeout(t);
  }, [q, search]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (r: Record<string, unknown>) => {
    const type = String(r.type);
    const mid = String(r.matter_id || "");
    if (type === "matter" && onSelectMatter) {
      onSelectMatter(mid);
      onNavigate("matters");
    } else if (type === "order") onNavigate("court-orders");
    else if (type === "document") onNavigate("documents");
    else if (type === "knowledge") onNavigate("knowledge");
    else if (type === "client") onNavigate("client-portal");
    else onNavigate("documents");
    setOpen(false);
    setQ("");
  };

  return (
    <div
      ref={ref}
      className={`ent-global-search relative w-full ${inHeader ? "ent-global-search--header" : "flex-1 max-w-2xl mx-auto"}`}
    >
      <div className="relative">
        <span className="ent-global-search__icon" aria-hidden>
          ⌕
        </span>
        <input
          className={`ent-global-search__input w-full ${inHeader ? "ent-global-search__input--header" : ""}`}
          placeholder="Search anything — matters, orders, documents, 302 murder…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => q.length >= 2 && setOpen(true)}
        />
        {busy && (
          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xs text-slate-400">…</span>
        )}
      </div>
      {open && (
        <div className="ent-global-search__dropdown absolute z-50 left-0 right-0 mt-2 rounded-xl border border-slate-200 bg-white shadow-lg max-h-[360px] overflow-y-auto le-scroll">
          {results.length === 0 && (
            <p className="text-sm text-slate-500 px-4 py-6 m-0">
              {q.length < 2 ? "Type at least 2 characters" : "No matches — try case number or section"}
            </p>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              type="button"
              onClick={() => pick(r)}
              className="w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 flex gap-3"
            >
              <span className="text-[10px] font-bold uppercase text-slate-400 w-16 shrink-0 pt-0.5">
                {TYPE_LABELS[String(r.type)] || String(r.type)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="font-medium text-navy text-sm block truncate">{String(r.title)}</span>
                <span className="text-xs text-slate-500 block truncate">
                  {String(r.subtitle)} {r.snippet ? `· ${String(r.snippet)}` : ""}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
