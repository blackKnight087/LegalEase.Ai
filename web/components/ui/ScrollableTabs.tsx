"use client";

export type TabItem = { id: string; label: string };

/** Horizontally scrollable tabs — mobile-friendly. */
export default function ScrollableTabs({
  tabs,
  active,
  onChange,
  className = "",
}: {
  tabs: TabItem[];
  active: string;
  onChange?: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      className={`shrink-0 border-b border-slate-200 bg-white/90 overflow-x-auto touch-scroll-x -mx-px ${className}`}
    >
      <div className="flex gap-0.5 min-w-min px-2 sm:px-4">
        {tabs.map((t) => {
          const isLink = !onChange;
          const cls = `shrink-0 px-3 sm:px-4 py-3 text-xs sm:text-sm font-medium border-b-2 -mb-px whitespace-nowrap min-h-[44px] sm:min-h-0 flex items-center transition-colors ${
            active === t.id
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`;
          if (isLink) {
            return (
              <a key={t.id} href={`#${t.id}`} className={cls}>
                {t.label}
              </a>
            );
          }
          return (
            <button key={t.id} type="button" onClick={() => onChange(t.id)} className={cls}>
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
