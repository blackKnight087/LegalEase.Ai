"use client";

type Props = {
  summary: Record<string, number> | null;
};

export default function CollectionsBar({ summary }: Props) {
  if (!summary) return null;
  const cards = [
    { label: "Unbilled", value: summary.unbilled_amount_inr, tone: "amber" },
    { label: "Total billed", value: summary.total_billed, tone: "slate" },
    { label: "Collected", value: summary.total_collected, tone: "emerald" },
    { label: "Outstanding", value: summary.outstanding_receivables, tone: "rose" },
    { label: "Overdue", value: summary.overdue_receivables, tone: "red" },
    { label: "This month", value: summary.current_month_revenue, tone: "navy" },
    { label: "Last month", value: summary.last_month_revenue, tone: "slate" },
    { label: "Collection rate", value: summary.collection_rate_pct, tone: "emerald", suffix: "%" },
  ];
  const toneBg: Record<string, string> = {
    amber: "bg-amber-50 border-amber-200",
    slate: "bg-slate-50 border-slate-200",
    emerald: "bg-emerald-50 border-emerald-200",
    rose: "bg-rose-50 border-rose-200",
    red: "bg-red-50 border-red-200",
    navy: "bg-slate-900 text-white border-slate-800",
  };
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`p-3 rounded-lg border ${toneBg[c.tone] || toneBg.slate} ${c.tone === "navy" ? "" : ""}`}
        >
          <p className={`text-xs font-medium ${c.tone === "navy" ? "text-slate-300" : "text-slate-500"}`}>{c.label}</p>
          <p className={`text-lg font-semibold tabular-nums ${c.tone === "navy" ? "text-white" : "text-navy"}`}>
            {c.suffix
              ? `${c.value ?? 0}${c.suffix}`
              : `₹${(c.value ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          </p>
        </div>
      ))}
    </div>
  );
}
