"use client";

type Pill = {
  label: string;
  ok: boolean;
  detail?: string;
};

export default function SystemHealthStrip({
  pills,
  compact = false,
}: {
  pills: Pill[];
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact
          ? "flex gap-1.5 overflow-x-auto touch-scroll-x flex-nowrap pb-0.5"
          : "flex flex-wrap gap-2"
      }
    >
      {pills.map((p) => (
        <div
          key={p.label}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full font-medium border ${
            compact ? "px-2 py-1 text-[10px]" : "px-3 py-1.5 text-xs gap-2"
          } ${
            p.ok
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-amber-50 border-amber-200 text-amber-900"
          }`}
          title={p.detail}
        >
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${p.ok ? "bg-emerald-500" : "bg-amber-500"}`}
          />
          <span>{p.label}</span>
          {p.detail ? (
            <span className="text-[0.65rem] opacity-75 hidden sm:inline">{p.detail}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
