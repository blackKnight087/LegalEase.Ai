import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import PageHeader from "../components/PageHeader.jsx";
import MetricCard from "../components/MetricCard.jsx";

function BarChart({ data, labelKey, valueKey }) {
  const max = Math.max(...data.map((d) => d[valueKey]), 1);
  return (
    <div className="flex items-end gap-1 h-40 mt-4">
      {data.map((d, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0">
          <div
            className="w-full bg-navy/80 rounded-t transition-all"
            style={{ height: `${(d[valueKey] / max) * 100}%`, minHeight: d[valueKey] ? 4 : 0 }}
          />
          <span className="text-[0.55rem] text-slate-400 truncate w-full text-center">
            {(d[labelKey] || "").slice(5)}
          </span>
        </div>
      ))}
    </div>
  );
}

function PieLegend({ items, labelKey }) {
  const total = items.reduce((s, i) => s + i.count, 0) || 1;
  const colors = ["#0f172a", "#3b82f6", "#d97706", "#10b981", "#64748b"];
  return (
    <ul className="space-y-2 mt-4">
      {items.map((item, i) => (
        <li key={i} className="flex items-center gap-2 text-sm">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ background: colors[i % colors.length] }} />
          <span className="flex-1 truncate">{item[labelKey]}</span>
          <span className="text-slate-500 font-medium">{Math.round((item.count / total) * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.fetchAnalytics().then(setData).catch(() => {});
  }, []);

  return (
    <>
      <PageHeader title="Analytics" subtitle="Query activity and usage patterns" />
      <div className="flex-1 overflow-y-auto le-scroll p-8">
        <div className="grid grid-cols-3 gap-4 mb-8 max-w-3xl">
          <MetricCard icon="📄" label="Documents" value={data?.documents ?? "—"} />
          <MetricCard icon="💬" label="Queries" value={data?.queries ?? "—"} />
          <MetricCard icon="🧩" label="KB" value={data?.kb_status ?? "—"} />
        </div>

        <div className="grid md:grid-cols-2 gap-6 max-w-4xl">
          <div className="bg-white rounded-2xl border p-6">
            <h3 className="font-semibold text-navy">Daily query activity</h3>
            {data?.daily_activity?.length ? (
              <BarChart data={data.daily_activity} labelKey="date" valueKey="count" />
            ) : (
              <p className="text-sm text-slate-400 mt-4">No data yet</p>
            )}
          </div>
          <div className="bg-white rounded-2xl border p-6">
            <h3 className="font-semibold text-navy">By mode</h3>
            {data?.by_mode?.length ? (
              <PieLegend items={data.by_mode} labelKey="mode" />
            ) : (
              <p className="text-sm text-slate-400 mt-4">No data yet</p>
            )}
          </div>
          <div className="bg-white rounded-2xl border p-6 md:col-span-2">
            <h3 className="font-semibold text-navy">By language</h3>
            {data?.by_language?.length ? (
              <PieLegend items={data.by_language} labelKey="language" />
            ) : (
              <p className="text-sm text-slate-400 mt-4">No data yet</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
