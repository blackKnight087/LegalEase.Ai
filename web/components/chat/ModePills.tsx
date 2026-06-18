"use client";

const MODES = [
  {
    id: "knowledge_base",
    label: "Knowledge Base",
    hint: "Answers from your uploaded documents only",
  },
  {
    id: "web_search",
    label: "Web Intel",
    hint: "Live Indian law — statutes, courts, gazettes (no upload required)",
  },
  {
    id: "hybrid",
    label: "Hybrid",
    hint: "Your documents + Gemini live web research (KB + Web Intel)",
  },
] as const;

export default function ModePills({
  mode,
  onChange,
  membership,
  compact = false,
}: {
  mode: string;
  onChange: (m: string) => void;
  membership: string;
  compact?: boolean;
}) {
  const visible = MODES;

  if (compact) {
    return (
      <div
        className="grid gap-1 w-full"
        style={{ gridTemplateColumns: `repeat(${visible.length}, minmax(0, 1fr))` }}
        role="tablist"
        aria-label="Research mode"
      >
        {visible.map((m) => {
          const active = mode === m.id;
          const short =
            m.id === "knowledge_base" ? "KB" : m.id === "web_search" ? "Web" : "Hybrid";
          return (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onChange(m.id)}
              title={m.hint}
              className={`h-8 rounded-lg text-[11px] font-semibold border transition-colors ${
                active
                  ? "bg-navy text-white border-navy shadow-sm"
                  : "bg-slate-50 text-slate-600 border-slate-200"
              }`}
            >
              {short}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex gap-2 overflow-x-auto touch-scroll-x justify-start sm:justify-center pb-1 -mx-1 px-1 snap-x-child">
      {visible.map((m) => {
        const active = mode === m.id;
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => onChange(m.id)}
            title={m.hint}
            className={`shrink-0 px-3 py-2 sm:py-1 rounded-full text-xs font-semibold border transition-colors min-h-[36px] sm:min-h-0 flex items-center ${
              active
                ? "bg-navy text-white border-navy"
                : "bg-white text-slate-600 border-slate-300 hover:border-slate-400"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
