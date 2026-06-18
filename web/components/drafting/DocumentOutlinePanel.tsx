"use client";

import type { OutlineSection } from "@/lib/legalDocumentFormat";

type Props = {
  sections: OutlineSection[];
  onSelect: (id: string) => void;
};

export default function DocumentOutlinePanel({ sections, onSelect }: Props) {
  return (
    <nav className="legal-outline-panel shrink-0 w-56 border-r border-slate-200/90 bg-slate-50/50 flex flex-col min-h-0 hidden lg:flex">
      <div className="px-4 py-3 border-b border-slate-200/90 bg-white">
        <h2 className="text-[10px] font-bold uppercase tracking-wider text-slate-500 m-0">Structure</h2>
        <p className="text-xs text-slate-400 m-0 mt-0.5">Headings H1–H3</p>
      </div>
      <ul className="flex-1 overflow-y-auto le-scroll p-2 text-sm">
        {sections.length === 0 && (
          <li className="text-slate-400 text-xs px-3 py-3 leading-relaxed">Add headings to generate the table of contents.</li>
        )}
        {sections.map((s, i) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onSelect(s.id)}
              className={`w-full text-left px-3 py-2 rounded-lg hover:bg-white hover:shadow-sm text-slate-700 transition-colors ${
                s.level === 1 ? "font-semibold text-slate-900" : s.level === 2 ? "pl-5 text-xs" : "pl-7 text-xs text-slate-600"
              }`}
            >
              <span className="text-slate-400 mr-1 tabular-nums">{i + 1}.</span>
              {s.title}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
