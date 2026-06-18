"use client";

export type TabItem = { id: string; label: string };

export default function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="shrink-0 border-b border-slate-200 bg-white/90 overflow-x-auto touch-scroll-x">
      <div className="flex gap-0.5 min-w-min px-2 sm:px-6 lg:px-8">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`shrink-0 px-3 sm:px-4 py-3 text-xs sm:text-sm font-medium border-b-2 -mb-px whitespace-nowrap min-h-[44px] sm:min-h-0 transition-colors ${
              active === t.id
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
