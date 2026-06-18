"use client";

const KPI_META: Array<{
  key: string;
  label: string;
  accent: string;
  icon: string;
}> = [
  { key: "new_leads", label: "New inquiries", accent: "from-blue-500 to-indigo-500", icon: "✨" },
  { key: "pending_consultations", label: "Consultations", accent: "from-sky-500 to-blue-500", icon: "📅" },
  { key: "qualified", label: "Qualified", accent: "from-emerald-500 to-teal-500", icon: "✓" },
  { key: "converted", label: "Converted", accent: "from-green-600 to-emerald-500", icon: "📁" },
  { key: "high_risk", label: "High priority", accent: "from-amber-500 to-orange-500", icon: "⚡" },
  { key: "rejected", label: "Rejected", accent: "from-slate-400 to-slate-500", icon: "—" },
];

export default function CrmKpiStrip({ kpis }: { kpis: Record<string, number> }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
      {KPI_META.map(({ key, label, accent, icon }) => (
        <div key={key} className="le-metric-card group">
          <div
            className={`absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r ${accent} opacity-90`}
          />
          <div className="flex items-start justify-between gap-2 pt-1">
            <div className="min-w-0">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500 m-0">
                {label}
              </p>
              <p className="text-2xl sm:text-3xl font-bold text-slate-900 m-0 mt-1 tabular-nums tracking-tight">
                {kpis[key] ?? 0}
              </p>
            </div>
            <span
              className="text-lg opacity-60 group-hover:opacity-100 transition-opacity"
              aria-hidden
            >
              {icon}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
