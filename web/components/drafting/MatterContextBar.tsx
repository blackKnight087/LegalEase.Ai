"use client";

type MatterVars = Record<string, string>;

const FIELDS: { key: string; label: string }[] = [
  { key: "ClientName", label: "Client" },
  { key: "MatterName", label: "Matter" },
  { key: "CaseNumber", label: "Case no." },
  { key: "CourtName", label: "Court" },
  { key: "OpposingParty", label: "Opposing" },
  { key: "Venue", label: "Venue" },
];

type Props = {
  matterId: string;
  variables: MatterVars;
  onInsertVariable: (token: string) => void;
  onAutofill: () => void;
  busy?: boolean;
};

export default function MatterContextBar({
  matterId,
  variables,
  onInsertVariable,
  onAutofill,
  busy,
}: Props) {
  if (!matterId) {
    return (
      <div className="px-3 py-2 text-xs text-amber-800 bg-amber-50 border-b border-amber-200 rounded-t-lg">
        Link a matter to enable autofill, court headings, and matter-aware copilot.
      </div>
    );
  }

  return (
    <div className="px-3 py-2 border-b bg-slate-50/90 text-xs flex flex-wrap gap-2 items-center">
      <span className="font-semibold text-navy shrink-0">Matter context</span>
      {FIELDS.map(({ key, label }) => {
        const val = variables[key] || variables[key.toLowerCase()] || "";
        return (
          <button
            key={key}
            type="button"
            title={val ? `Insert ${key}` : `${label} not set — autofill`}
            disabled={busy}
            onClick={() => onInsertVariable(val || `{{${key}}}`)}
            className="px-2 py-1 rounded-md border bg-white hover:border-navy max-w-[140px] truncate"
          >
            <span className="text-slate-500">{label}:</span>{" "}
            <span className="text-navy font-medium">{val || "—"}</span>
          </button>
        );
      })}
      <button
        type="button"
        disabled={busy}
        onClick={onAutofill}
        className="ml-auto px-3 py-1 bg-navy text-white rounded-md font-medium shrink-0"
      >
        Autofill all
      </button>
    </div>
  );
}
