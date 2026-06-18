"use client";

import { useState } from "react";
import * as api from "@/lib/api";

const REPORTS = [
  { id: "summary", label: "Summary" },
  { id: "revenue_by_matter", label: "Revenue by matter" },
  { id: "outstanding", label: "Outstanding invoices" },
  { id: "gst", label: "GST report" },
  { id: "expenses", label: "Expense report" },
  { id: "collections", label: "Collections" },
];

export default function BillingReportsPanel() {
  const [report, setReport] = useState("summary");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async (id: string) => {
    setReport(id);
    setBusy(true);
    try {
      setData(await api.fetchBillingReport(id));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm p-4 space-y-3">
      <h2 className="text-sm font-semibold text-navy">Reports</h2>
      <div className="flex flex-wrap gap-2">
        {REPORTS.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => load(r.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${
              report === r.id ? "bg-navy text-white border-navy" : "border-slate-200 text-slate-700"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>
      {busy && <p className="text-xs text-slate-500">Loading…</p>}
      {data && (
        <pre className="text-xs bg-slate-50 border rounded-lg p-3 overflow-auto max-h-64">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </section>
  );
}
