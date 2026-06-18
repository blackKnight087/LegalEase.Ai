"use client";

import type { MatterBillingProfile } from "@/lib/api";

type Props = {
  profile: MatterBillingProfile | null;
  loading?: boolean;
};

export default function ClientBillingProfile({ profile, loading }: Props) {
  if (loading) {
    return (
      <div className="border border-slate-200 rounded-xl p-4 animate-pulse h-32 bg-slate-50" />
    );
  }
  if (!profile?.matter_id) {
    return (
      <p className="text-sm text-slate-500 border border-dashed border-slate-200 rounded-xl p-4">
        Select a matter to view client billing profile.
      </p>
    );
  }
  const rows: [string, string][] = [
    ["Client", profile.client_name || "—"],
    ["Email", profile.client_email || "—"],
    ["Phone", profile.client_phone || "—"],
    ["Address", profile.client_address || "—"],
    ["Matter", profile.matter_name || "—"],
    ["Matter #", profile.matter_number || "—"],
    ["Assigned", profile.assigned_lawyer || "—"],
    ["Retainer", `₹${(profile.retainer_balance ?? 0).toLocaleString("en-IN")}`],
    ["Outstanding", `₹${(profile.outstanding_balance ?? 0).toLocaleString("en-IN")}`],
    ["Total billed", `₹${(profile.total_billed ?? 0).toLocaleString("en-IN")}`],
    ["Collected", `₹${(profile.total_collected ?? 0).toLocaleString("en-IN")}`],
  ];
  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
        <h2 className="text-sm font-semibold text-navy tracking-wide">Client billing profile</h2>
        <p className="text-xs text-slate-500 mt-0.5">{profile.case_number || profile.court_name || "Matter finances"}</p>
      </div>
      <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2 p-4 text-sm">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</dt>
            <dd className="text-slate-800 font-medium mt-0.5">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
