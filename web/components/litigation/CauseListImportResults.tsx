"use client";

export type CauseListImportSummary = {
  parsedCount: number;
  matchedCount: number;
  unmatchedCount?: number;
  inserted: number;
  skipped: number;
  errors: string[];
  hearingDates?: number;
  apiCalls?: number;
  confidence?: string;
  parser?: string;
};

type ParsedRow = {
  row_index?: number;
  hearing_date?: string;
  purpose?: string;
  confidence?: string;
  selected?: boolean;
  suggested_matter_id?: string;
  matter_id?: string;
  suggested_matter_name?: string;
};

export function buildImportSummaryFromSync(r: Record<string, unknown>): CauseListImportSummary {
  const parsed = (r.parsed as { rows?: ParsedRow[]; parsed_count?: number; parser?: string }) || {};
  const rows = parsed.rows || [];
  const scheduled = (r.scheduled_hearings as Array<Record<string, unknown>>) || [];
  const imp = scheduled[0] || {};
  const api = (r.api as { billed_calls?: number }) || {};
  const matched = rows.filter((row) => row.selected && (row.suggested_matter_id || row.matter_id)).length;
  const confidences = [...new Set(rows.map((row) => row.confidence).filter(Boolean))];
  return {
    parsedCount: Number(parsed.parsed_count ?? rows.length),
    matchedCount: matched,
    unmatchedCount: Math.max(0, rows.length - matched),
    inserted: Number(imp.inserted ?? 0),
    skipped: Number(imp.skipped ?? 0),
    errors: Array.isArray(imp.errors) ? (imp.errors as string[]) : [],
    hearingDates: Array.isArray(r.hearing_dates) ? r.hearing_dates.length : rows.length,
    apiCalls: api.billed_calls,
    confidence: confidences.length === 1 ? String(confidences[0]) : confidences.length > 1 ? "mixed" : "",
    parser: parsed.parser,
  };
}

export function buildImportSummaryFromRows(
  rows: ParsedRow[],
  imp?: { inserted?: number; skipped?: number; errors?: string[] },
  parser?: string
): CauseListImportSummary {
  const matched = rows.filter((row) => row.selected && (row.suggested_matter_id || row.matter_id)).length;
  const confidences = [...new Set(rows.map((row) => row.confidence).filter(Boolean))];
  return {
    parsedCount: rows.length,
    matchedCount: matched,
    unmatchedCount: Math.max(0, rows.length - matched),
    inserted: imp?.inserted ?? 0,
    skipped: imp?.skipped ?? 0,
    errors: imp?.errors || [],
    confidence: confidences.length === 1 ? String(confidences[0]) : confidences.length > 1 ? "mixed" : "",
    parser,
  };
}

export default function CauseListImportResults({ summary }: { summary: CauseListImportSummary | null }) {
  if (!summary) return null;

  return (
    <section className="text-xs text-slate-600 rounded-lg bg-slate-50 border border-slate-200 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-navy m-0">Import results</h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        <p className="m-0">
          <strong>Parsed:</strong> {summary.parsedCount}
        </p>
        <p className="m-0">
          <strong>Matched:</strong> {summary.matchedCount}
        </p>
        <p className="m-0">
          <strong>Unmatched:</strong> {summary.unmatchedCount ?? Math.max(0, summary.parsedCount - summary.matchedCount)}
        </p>
        <p className="m-0">
          <strong>Imported:</strong> {summary.inserted}
        </p>
        <p className="m-0">
          <strong>Skipped:</strong> {summary.skipped}
        </p>
        {summary.hearingDates != null && (
          <p className="m-0">
            <strong>Dates detected:</strong> {summary.hearingDates}
          </p>
        )}
        {summary.confidence && (
          <p className="m-0">
            <strong>Match confidence:</strong> {summary.confidence}
          </p>
        )}
        {summary.parser && (
          <p className="m-0">
            <strong>Parser:</strong> {summary.parser}
          </p>
        )}
        {summary.apiCalls ? (
          <p className="m-0 sm:col-span-2">
            <strong>API calls billed:</strong> {summary.apiCalls}
          </p>
        ) : null}
      </div>
      {summary.errors.length > 0 && (
        <div className="rounded-lg bg-red-50 border border-red-200 text-red-800 px-3 py-2">
          <p className="font-semibold m-0 mb-1">Errors</p>
          <ul className="m-0 pl-4 space-y-0.5">
            {summary.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
