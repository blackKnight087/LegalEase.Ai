"use client";

import { useState } from "react";
import * as api from "@/lib/api";
import { formatApiError } from "./crmUtils";

const ACTIONS = [
  { id: "summarize_lead", label: "Summarize lead" },
  { id: "missing_documents", label: "Missing documents" },
  { id: "consultation_questions", label: "Consultation questions" },
  { id: "convert_preview", label: "Conversion preview" },
  { id: "draft_follow_up", label: "Draft follow-up" },
  { id: "draft_legal_notice_outline", label: "Legal notice outline" },
];

type Props = {
  leadId: string;
};

export default function CrmAssistantPanel({ leadId }: Props) {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const run = async (action: string) => {
    setBusy(true);
    setErr("");
    try {
      const out = await api.crmAssistant(leadId, action);
      setResult(out);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="border rounded-xl bg-slate-50 p-4 space-y-3 h-fit lg:sticky lg:top-4">
      <h3 className="text-sm font-semibold text-navy">Intake assistant</h3>
      <div className="flex flex-col gap-2">
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            disabled={busy}
            onClick={() => run(a.id)}
            className="text-left text-xs px-3 py-2 bg-white border rounded-lg hover:bg-blue-50 disabled:opacity-50"
          >
            {a.label}
          </button>
        ))}
      </div>
      {err && <p className="text-red-600 text-xs">{err}</p>}
      {result && (
        <div className="text-xs bg-white border rounded-lg p-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
          {typeof result.text === "string" && result.text}
          {Array.isArray(result.questions) && (
            <ol className="list-decimal pl-4">
              {(result.questions as string[]).map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ol>
          )}
          {Array.isArray(result.missing_documents) && (
            <ul className="list-disc pl-4">
              {(result.missing_documents as string[]).map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
          {result.draft ? (
            <p className="whitespace-pre-wrap">{String(result.draft)}</p>
          ) : null}
          {result.matter_preview ? (
            <pre className="text-[0.65rem]">{JSON.stringify(result.matter_preview, null, 2)}</pre>
          ) : null}
          {!result.text &&
            !result.questions &&
            !result.missing_documents &&
            !result.draft &&
            !result.matter_preview && (
              <pre className="text-[0.65rem]">{JSON.stringify(result, null, 2)}</pre>
            )}
        </div>
      )}
    </aside>
  );
}
