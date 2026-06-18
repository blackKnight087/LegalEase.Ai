"use client";

import { useMemo, useState } from "react";

const CATEGORIES = [
  { id: "", label: "All clauses" },
  { id: "confidentiality", label: "Confidentiality" },
  { id: "indemnity", label: "Indemnity" },
  { id: "termination", label: "Termination" },
  { id: "jurisdiction", label: "Jurisdiction" },
  { id: "force_majeure", label: "Force majeure" },
  { id: "arbitration", label: "Arbitration" },
  { id: "liability", label: "Liability" },
];

type Clause = { clause_id: string; clause_tag: string; clause_text_content: string };

type Props = {
  clauses: Clause[];
  tag: string;
  onTagChange: (tag: string) => void;
  onInsert: (text: string) => void;
  recent?: string[];
};

export default function ClauseLibraryDrawer({
  clauses,
  tag,
  onTagChange,
  onInsert,
  recent = [],
}: Props) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return clauses.filter((c) => {
      if (tag && c.clause_tag !== tag) return false;
      if (!qq) return true;
      return (
        c.clause_tag.toLowerCase().includes(qq) ||
        c.clause_text_content.toLowerCase().includes(qq)
      );
    });
  }, [clauses, tag, q]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-2 pb-2 border-b space-y-2">
        <h3 className="text-xs font-semibold text-navy">Firm clause library</h3>
        <p className="text-[10px] text-slate-500 m-0">Approved wording · searchable by intent</p>
        <input
          className="w-full border rounded-lg px-2 py-1.5 text-xs"
          placeholder="Search clauses…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="flex flex-wrap gap-1">
          {CATEGORIES.map((c) => (
            <button
              key={c.id || "all"}
              type="button"
              onClick={() => onTagChange(c.id)}
              className={`px-2 py-0.5 text-[10px] rounded-full border ${
                tag === c.id ? "bg-navy text-white border-navy" : "bg-white hover:bg-slate-50"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
      {recent.length > 0 && (
        <p className="px-2 pt-2 text-[10px] text-slate-500">Recent: {recent.slice(0, 3).join(", ")}</p>
      )}
      <ul className="flex-1 overflow-y-auto le-scroll p-2 space-y-2">
        {filtered.map((c) => (
          <li key={c.clause_id} className="p-2 border rounded-lg bg-white text-xs">
            <p className="font-medium text-navy capitalize">{c.clause_tag.replace(/_/g, " ")}</p>
            <p className="text-slate-600 line-clamp-3 mt-1">{c.clause_text_content.slice(0, 160)}…</p>
            <button
              type="button"
              className="mt-2 text-navy underline font-medium"
              onClick={() => onInsert(c.clause_text_content)}
            >
              Insert clause
            </button>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="text-slate-400 text-xs p-2">No clauses match. Try another category or search.</li>
        )}
      </ul>
    </div>
  );
}
