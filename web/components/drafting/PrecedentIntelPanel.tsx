"use client";

import { useState } from "react";
import * as api from "@/lib/api";

type Props = {
  draftId: string;
  onInsert: (text: string) => void;
  onErr: (msg: string) => void;
  onOk: (msg: string) => void;
};

export default function PrecedentIntelPanel({ draftId, onInsert, onErr, onOk }: Props) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [compare, setCompare] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const search = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try {
      const r = await api.searchPrecedents(q);
      setResults((r.results as Array<Record<string, unknown>>) || []);
      setCompare(null);
    } catch (e) {
      onErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  const runCompare = async (precedentId: string) => {
    setBusy(true);
    try {
      const r = await api.compareDraftPrecedent(draftId, precedentId);
      setCompare(r);
    } catch (e) {
      onErr(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-2 text-xs flex flex-col min-h-0 h-full">
      <h3 className="font-semibold text-navy">Firm precedents</h3>
      <p className="text-slate-500 m-0">Search approved language · compare to current draft</p>
      <div className="flex gap-1 my-2">
        <input
          className="flex-1 border rounded px-2 py-1"
          placeholder="e.g. indemnity NDA Delhi"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button type="button" disabled={busy} onClick={search} className="px-2 py-1 border rounded bg-white">
          Search
        </button>
      </div>
      <ul className="flex-1 overflow-y-auto le-scroll space-y-2 m-0 p-0 list-none min-h-0">
        {results.map((p) => (
          <li key={String(p.precedent_id)} className="border rounded-lg p-2 bg-white">
            <p className="font-medium text-navy m-0">{String(p.title)}</p>
            <p className="text-[10px] text-slate-500 m-0">
              {String(p.document_type)} · match {String(p.confidence ?? "—")}
            </p>
            <div className="flex flex-wrap gap-2 mt-2">
              <button type="button" className="underline text-navy" onClick={() => runCompare(String(p.precedent_id))}>
                Compare
              </button>
              <button
                type="button"
                className="underline"
                onClick={() => {
                  onInsert(`<p>${String(p.content || "").slice(0, 500).replace(/</g, "")}</p>`);
                  onOk("Precedent excerpt inserted");
                }}
              >
                Insert excerpt
              </button>
            </div>
          </li>
        ))}
      </ul>
      {compare && (
        <div className="border-t pt-2 mt-2 max-h-40 overflow-y-auto le-scroll shrink-0">
          <p className="font-medium m-0">
            Similarity {String(compare.similarity_score)}% — {String(compare.precedent_title)}
          </p>
          <div
            className="redline-diff text-[10px] mt-1 border rounded p-1 bg-slate-50"
            dangerouslySetInnerHTML={{ __html: String(compare.diff_html || "") }}
          />
        </div>
      )}
    </div>
  );
}
