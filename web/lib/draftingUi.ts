/** Shared drafting UI helpers — labels, health colors, doc type formatting. */

export function formatDocumentType(type?: string): string {
  if (!type) return "Document";
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function healthScoreTone(score: number): { bar: string; text: string } {
  if (score >= 75) return { bar: "bg-emerald-500", text: "text-emerald-700" };
  if (score >= 50) return { bar: "bg-amber-500", text: "text-amber-700" };
  if (score > 0) return { bar: "bg-orange-500", text: "text-orange-700" };
  return { bar: "bg-slate-300", text: "text-slate-500" };
}

export function templateMonogram(label: string): string {
  const parts = label.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return label.slice(0, 2).toUpperCase();
}

export const FEATURED_TEMPLATE_IDS = ["agreement", "petition", "bail_application"] as const;

export const KANBAN_COLUMN_META: Record<
  string,
  { label: string; accent: string }
> = {
  draft: { label: "Draft", accent: "from-slate-500 to-slate-600" },
  in_review: { label: "In review", accent: "from-blue-500 to-indigo-600" },
  partner_review: { label: "Partner review", accent: "from-violet-500 to-purple-600" },
  needs_revision: { label: "Needs revision", accent: "from-amber-500 to-orange-500" },
  approved: { label: "Approved", accent: "from-emerald-500 to-teal-600" },
  ready_to_file: { label: "Ready to file", accent: "from-cyan-500 to-blue-500" },
  filed: { label: "Filed", accent: "from-sky-600 to-blue-700" },
  executed: { label: "Executed", accent: "from-green-600 to-emerald-700" },
  archived: { label: "Archived", accent: "from-slate-400 to-slate-500" },
};
