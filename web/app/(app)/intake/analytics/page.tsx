"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import AnalyticsPieChart from "@/components/analytics/AnalyticsPieChart";
import * as api from "@/lib/api";
import { formatApiError } from "@/components/crm/crmUtils";

export default function IntakeAnalyticsPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .fetchCrmAnalytics()
      .then(setData)
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  const sources =
    (data?.lead_sources as Array<{ source: string; count: number }>) || [];
  const types = (data?.case_types as Array<{ type: string; count: number }>) || [];

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader title="Intake analytics" subtitle="Sources, conversion, case types, lawyer performance" />
      <div className="flex-1 overflow-y-auto le-scroll p-3 sm:p-6 max-w-5xl mx-auto w-full space-y-4 sm:space-y-6">
        <Link href="/intake" className="text-sm text-blue-700 hover:underline">
          ← Dashboard
        </Link>
        {err && <p className="text-red-600 text-sm">{err}</p>}
        {data && (
          <>
            <div className="grid sm:grid-cols-3 gap-4">
              <div className="bg-white border rounded-xl p-4">
                <p className="text-2xl font-bold">{String(data.conversion_rate)}%</p>
                <p className="text-xs text-slate-600">Conversion rate</p>
              </div>
              <div className="bg-white border rounded-xl p-4">
                <p className="text-2xl font-bold">{String(data.avg_lead_score)}</p>
                <p className="text-xs text-slate-600">Avg lead score</p>
              </div>
              <div className="bg-white border rounded-xl p-4">
                <p className="text-2xl font-bold">{String(data.total_leads)}</p>
                <p className="text-xs text-slate-600">Total leads</p>
              </div>
            </div>
            <div className="grid md:grid-cols-2 gap-6">
              <section className="bg-white border rounded-xl p-4">
                <AnalyticsPieChart
                  title="Lead sources"
                  slices={sources.map((s, i) => ({
                    label: s.source,
                    value: s.count,
                    color: ["#1e3a5f", "#2563eb", "#059669", "#7c3aed"][i % 4],
                  }))}
                />
              </section>
              <section className="bg-white border rounded-xl p-4">
                <AnalyticsPieChart
                  title="Case types"
                  slices={types.map((t, i) => ({
                    label: t.type,
                    value: t.count,
                    color: ["#d97706", "#dc2626", "#0891b2", "#64748b"][i % 4],
                  }))}
                />
              </section>
            </div>
            <section className="bg-white border rounded-xl p-4">
              <h2 className="text-sm font-semibold text-navy mb-3">Lawyer performance</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="pb-2">Lawyer</th>
                    <th>Assigned</th>
                    <th>Converted</th>
                  </tr>
                </thead>
                <tbody>
                  {((data.lawyer_performance as Array<Record<string, unknown>>) || []).map(
                    (row) => (
                      <tr key={String(row.lawyer_id)} className="border-t">
                        <td className="py-2">{String(row.lawyer_id)}</td>
                        <td>{String(row.assigned)}</td>
                        <td>{String(row.converted)}</td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
