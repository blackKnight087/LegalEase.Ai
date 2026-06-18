"use client";

import Link from "next/link";

type Overview = {
  matter_id?: string;
  total?: number;
  drafts?: number;
  awaiting_review?: number;
  filed_or_ready?: number;
  control_center_url?: string;
  awaiting_documents?: Array<{ draft_id: string; title: string; status: string }>;
};

export default function MatterDraftingOverviewCard({
  overview,
  matterId,
}: {
  overview: Overview | null | undefined;
  matterId: string;
}) {
  if (!overview || (overview.total ?? 0) === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-navy m-0">Drafting Studio</h3>
        <p className="text-sm text-slate-600 mt-1 mb-3">No matter-linked drafts yet.</p>
        <Link
          href={`/drafting?matter=${matterId}`}
          className="text-sm text-navy font-medium underline"
        >
          Open Drafting Studio →
        </Link>
      </div>
    );
  }

  const awaiting = overview.awaiting_review ?? 0;
  const ccUrl = overview.control_center_url || `/drafting?matter=${matterId}`;

  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-navy m-0">Drafting Studio</h3>
          <p className="text-xs text-slate-500 mt-1 m-0">
            {overview.total} document{overview.total === 1 ? "" : "s"} on this matter
          </p>
        </div>
        <Link href={ccUrl} className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs no-underline">
          Control center
        </Link>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-3">
        <div className="rounded-lg bg-slate-50 p-2 text-center">
          <p className="text-lg font-bold text-navy m-0">{overview.drafts ?? 0}</p>
          <p className="text-[10px] text-slate-500 m-0">Drafts</p>
        </div>
        <div className="rounded-lg bg-amber-50 p-2 text-center">
          <p className="text-lg font-bold text-amber-800 m-0">{awaiting}</p>
          <p className="text-[10px] text-amber-900 m-0">Awaiting review</p>
        </div>
        <div className="rounded-lg bg-green-50 p-2 text-center">
          <p className="text-lg font-bold text-green-800 m-0">{overview.filed_or_ready ?? 0}</p>
          <p className="text-[10px] text-green-900 m-0">Filed / ready</p>
        </div>
      </div>

      {awaiting > 0 && (
        <div className="mt-3">
          <Link
            href={ccUrl}
            className="text-sm font-medium text-amber-800 underline"
          >
            {awaiting} document{awaiting === 1 ? "" : "s"} awaiting action →
          </Link>
          <ul className="mt-2 space-y-1">
            {(overview.awaiting_documents || []).slice(0, 4).map((d) => (
              <li key={d.draft_id}>
                <Link href={`/drafting/${d.draft_id}`} className="text-xs text-navy underline">
                  {d.title}
                </Link>
                <span className="text-[10px] text-slate-400 ml-1">({d.status})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        <Link
          href={`/matters/${matterId}?tab=drafting`}
          className="text-xs border rounded-lg px-2 py-1 no-underline text-inherit hover:bg-slate-50"
        >
          Matter drafting tab
        </Link>
        <Link
          href={`/billing?matter=${matterId}`}
          className="text-xs border rounded-lg px-2 py-1 no-underline text-inherit hover:bg-slate-50"
        >
          Billing
        </Link>
        <Link
          href={`/litigation?tab=orders&matter=${matterId}`}
          className="text-xs border rounded-lg px-2 py-1 no-underline text-inherit hover:bg-slate-50"
        >
          Court orders
        </Link>
      </div>
    </div>
  );
}
