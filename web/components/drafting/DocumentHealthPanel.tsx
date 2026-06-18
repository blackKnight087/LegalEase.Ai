"use client";

import { healthScoreTone } from "@/lib/draftingUi";

type Props = {
  insights: Record<string, unknown> | null;
  clauseIntel: Record<string, unknown> | null;
  onInsertClause: (tag: string) => void;
  onFilingCheck: () => void;
  onAddExecution: () => void;
};

const CLAUSE_FIXES: Record<string, string> = {
  confidentiality: "confidentiality",
  indemnity: "indemnity",
  termination: "termination",
  arbitration: "arbitration",
  jurisdiction: "jurisdiction",
};

function StatusDot({ level }: { level: "red" | "amber" | "green" }) {
  const colors = {
    red: "bg-red-500",
    amber: "bg-amber-500",
    green: "bg-emerald-500",
  };
  return <span className={`inline-block w-2 h-2 rounded-full shrink-0 mt-1.5 ${colors[level]}`} />;
}

export default function DocumentHealthPanel({
  insights,
  clauseIntel,
  onInsertClause,
  onFilingCheck,
  onAddExecution,
}: Props) {
  if (!insights) {
    return <p className="text-sm text-slate-500 p-4">Loading document health…</p>;
  }

  const risk = Number(insights.risk_score ?? 50);
  const health = Math.max(0, Math.min(100, 100 - risk));
  const tone = healthScoreTone(health);
  const missing = (insights.missing_sections as string[]) || [];
  const recs =
    (clauseIntel?.recommendations as Array<{ clause: string; explanation: string }>) || [];
  const hasExecution = !missing.some((m) => /execution|signature|witness/i.test(m));

  const issueLevel = (tag: string) => {
    if (missing.some((m) => m.toLowerCase().includes(tag))) return "red" as const;
    if (recs.some((r) => r.clause.toLowerCase().includes(tag))) return "amber" as const;
    return "green" as const;
  };

  return (
    <div className="p-4 space-y-4 text-sm">
      <div className="rounded-2xl bg-white border border-slate-200/90 p-4 shadow-sm">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 m-0">Document health</p>
        <p className={`text-3xl font-bold m-0 mt-1 tabular-nums ${tone.text}`}>{health}%</p>
        <div className="drafting-health-bar mt-3">
          <div className={`drafting-health-bar__fill ${tone.bar}`} style={{ width: `${health}%` }} />
        </div>
      </div>

      <div>
        <p className="le-section-title m-0 mb-2">Clause checklist</p>
        <ul className="space-y-2">
          {["confidentiality", "indemnity", "termination", "arbitration"].map((tag) => {
            const lvl = issueLevel(tag);
            const label =
              lvl === "red"
                ? `No ${tag} clause`
                : lvl === "amber"
                  ? `${tag} — review recommended`
                  : `${tag.charAt(0).toUpperCase() + tag.slice(1)} present`;
            return (
              <li key={tag} className="flex items-start gap-2 text-slate-700">
                <StatusDot level={lvl} />
                <span>{label}</span>
              </li>
            );
          })}
          <li className="flex items-start gap-2 text-slate-700">
            <StatusDot level={hasExecution ? "green" : "red"} />
            <span>{hasExecution ? "Execution section present" : "Execution block missing"}</span>
          </li>
        </ul>
      </div>

      <div>
        <p className="le-section-title m-0 mb-2">Recommended actions</p>
        <div className="flex flex-col gap-1.5">
          {missing.slice(0, 4).map((m) => {
            const key = Object.keys(CLAUSE_FIXES).find((k) => m.toLowerCase().includes(k));
            return (
              <button
                key={m}
                type="button"
                className="text-left px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/40 text-slate-800 font-medium text-xs transition-colors"
                onClick={() => key && onInsertClause(CLAUSE_FIXES[key])}
              >
                Insert {m}
              </button>
            );
          })}
          {!hasExecution && (
            <button
              type="button"
              className="text-left px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/40 text-slate-800 font-medium text-xs transition-colors"
              onClick={onAddExecution}
            >
              Add execution block
            </button>
          )}
          <button
            type="button"
            className="text-left px-3 py-2 rounded-xl border border-slate-900 bg-slate-900 text-white font-medium text-xs hover:bg-slate-800 transition-colors"
            onClick={onFilingCheck}
          >
            Check filing readiness
          </button>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        {[
          ["Words", String(insights.word_count ?? "—")],
          ["Versions", `v${String(insights.version_count ?? "1")}`],
          ["Signatures", String(insights.required_signatures ?? "—")],
          ["Status", (insights.review_status as string) || "draft"],
        ].map(([label, val]) => (
          <div key={label} className="rounded-xl border border-slate-100 bg-white p-2.5">
            <dt className="text-slate-500 m-0">{label}</dt>
            <dd className="font-semibold text-slate-900 m-0 mt-0.5 capitalize">{val}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
