"use client";

import Link from "next/link";
import type { DashboardFull } from "@/lib/api";

type Practice = NonNullable<DashboardFull["practice"]>;

function fmtInr(n: number) {
  return `₹${n.toLocaleString("en-IN")}`;
}

export default function PracticeModuleCards({ practice }: { practice: Practice }) {
  const billing = practice.billing || {};
  const crm = practice.crm || {};
  const stages = crm.pipeline_stages || {};
  const topStage = Object.entries(stages).sort((a, b) => b[1] - a[1])[0];

  const cards = [
    {
      href: "/matters",
      label: "Active matters",
      value: `${practice.matters_active ?? 0}`,
      sub: `${practice.matters_total ?? 0} total`,
      color: "border-l-4 border-l-blue-500",
    },
    {
      href: "/billing",
      label: "Unbilled work",
      value: fmtInr(billing.unbilled_amount_inr ?? 0),
      sub: `${billing.unbilled_entries ?? 0} entries`,
      color: "border-l-4 border-l-amber-500",
    },
    {
      href: "/intake",
      label: "CRM pipeline",
      value: String(crm.leads_total ?? 0),
      sub: topStage ? `${topStage[0].replace(/_/g, " ")}: ${topStage[1]}` : "No leads yet",
      color: "border-l-4 border-l-emerald-500",
    },
    {
      href: "/discovery",
      label: "Evidence Intelligence",
      value: String(practice.ediscovery?.batches_total ?? 0),
      sub: "evidence items",
      color: "border-l-4 border-l-violet-500",
    },
  ];

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {cards.map((c) => (
        <Link
          key={c.href}
          href={c.href}
          className={`le-card le-card-hover le-interactive block p-4 rounded-xl bg-white border border-slate-200 hover:border-blue-200 no-underline ${c.color}`}
        >
          <p className="text-xs text-slate-500 m-0">{c.label}</p>
          <p className="text-2xl font-bold text-navy m-0 mt-1">{c.value}</p>
          <p className="text-xs text-slate-500 m-0 mt-1">{c.sub}</p>
        </Link>
      ))}
    </div>
  );
}
