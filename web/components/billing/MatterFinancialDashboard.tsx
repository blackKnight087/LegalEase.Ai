"use client";

type Props = {
  financials: Record<string, unknown> | null;
};

export default function MatterFinancialDashboard({ financials }: Props) {
  if (!financials?.matter_id) return null;
  const cards = [
    { label: "Matter value", key: "matter_value" },
    { label: "Hours logged", key: "hours_logged", suffix: " hrs" },
    { label: "Billed", key: "amount_billed" },
    { label: "Collected", key: "amount_collected" },
    { label: "Outstanding", key: "outstanding_balance" },
    { label: "Expenses", key: "expenses" },
    { label: "Trust", key: "trust_balance" },
    { label: "Profitability", key: "profitability" },
  ];
  return (
    <section className="border border-slate-200 rounded-xl bg-navy text-white p-4">
      <h2 className="text-sm font-semibold mb-3">Matter financial dashboard</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        {cards.map((c) => {
          const v = financials[c.key];
          const display =
            c.suffix != null
              ? `${v ?? 0}${c.suffix}`
              : `₹${Number(v ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
          return (
            <div key={c.key} className="bg-white/10 rounded-lg p-3">
              <p className="text-xs text-slate-300">{c.label}</p>
              <p className="text-lg font-semibold tabular-nums">{display}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
