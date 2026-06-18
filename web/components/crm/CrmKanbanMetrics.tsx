"use client";

import { formatInr } from "./crmUtils";

type Metrics = {
  total_leads?: number;
  pipeline_value_inr?: number;
  conversion_rate?: number;
  consultations_scheduled?: number;
  matters_created?: number;
  revenue_forecast_inr?: number;
};

export default function CrmKanbanMetrics({ metrics }: { metrics: Metrics }) {
  const items = [
    { label: "Total leads", value: String(metrics.total_leads ?? 0) },
    { label: "Pipeline value", value: formatInr(metrics.pipeline_value_inr ?? 0), highlight: true },
    { label: "Conversion rate", value: `${metrics.conversion_rate ?? 0}%` },
    { label: "Consultations", value: String(metrics.consultations_scheduled ?? 0) },
    { label: "Matters created", value: String(metrics.matters_created ?? 0) },
    { label: "Revenue forecast", value: formatInr(metrics.revenue_forecast_inr ?? 0) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-xl border px-3 py-2.5 ${
            item.highlight
              ? "bg-gradient-to-br from-navy to-slate-800 border-navy/20 text-white"
              : "bg-white border-slate-200/90 shadow-sm"
          }`}
        >
          <p className={`text-[0.65rem] uppercase tracking-wide font-semibold ${item.highlight ? "text-slate-300" : "text-slate-500"}`}>
            {item.label}
          </p>
          <p className={`text-lg font-bold mt-0.5 tabular-nums ${item.highlight ? "text-white" : "text-navy"}`}>
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}
