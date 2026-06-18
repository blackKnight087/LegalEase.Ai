"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import * as api from "@/lib/api";

export default function DraftReviewPage() {
  const params = useParams();
  const draftId = String(params.draftId || "");
  const [ws, setWs] = useState<Record<string, unknown> | null>(null);
  const [suggestion, setSuggestion] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [assigneeName, setAssigneeName] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    const data = await api.getReviewWorkspace(draftId);
    setWs(data);
  }, [draftId]);

  useEffect(() => {
    if (draftId) load().catch((e) => setErr(e instanceof Error ? e.message : "Load failed"));
  }, [draftId, load]);

  const doc = ws?.document as api.WorkspaceDocument | undefined;
  const readiness = ws?.filing_readiness as Record<string, unknown> | undefined;

  return (
    <div className="flex flex-col h-full min-h-0 p-4 space-y-4 le-scroll overflow-y-auto">
      <PageHeader
        title={`Review — ${doc?.title || "Document"}`}
        subtitle="Comments, suggestions, checklist, filing readiness"
      />
      <div className="flex gap-2 flex-wrap">
        <Link href={`/drafting/${draftId}`} className="text-sm text-navy underline">
          ← Editor
        </Link>
        <Link href="/drafting" className="text-sm text-navy underline">
          Control center
        </Link>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.getFilingReadiness(draftId);
              setWs((w) => (w ? { ...w, filing_readiness: r } : w));
              setErr("");
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Filing readiness failed");
            } finally {
              setBusy(false);
            }
          }}
          className="px-3 py-1.5 border rounded-lg text-sm"
        >
          Run filing readiness
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api.promoteToPrecedent(draftId);
              await load();
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Promote failed");
            } finally {
              setBusy(false);
            }
          }}
          className="px-3 py-1.5 bg-navy text-white rounded-lg text-sm"
        >
          Save as precedent
        </button>
      </div>

      {err && <p className="text-red-600 text-sm">{err}</p>}

      {readiness && (
        <section className="border rounded-xl p-4 bg-white">
          <h2 className="font-semibold text-navy text-sm">Filing readiness — {String(readiness.filing_readiness_score)}/100</h2>
          <ul className="text-sm mt-2 space-y-1">
            {((readiness.checks as Array<{ check: string; passed: boolean; message: string }>) || []).map((c) => (
              <li key={c.check} className={c.passed ? "text-green-800" : "text-red-700"}>
                {c.passed ? "✓" : "✗"} {c.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="border rounded-xl p-4 bg-white">
        <h2 className="font-semibold text-navy text-sm mb-2">Review checklist</h2>
        <ul className="text-sm space-y-1">
          {((ws?.checklist as Array<{ id: string; label: string; done: boolean }>) || []).map((c) => (
            <li key={c.id}>{c.done ? "✓" : "○"} {c.label}</li>
          ))}
        </ul>
      </section>

      <section className="border rounded-xl p-4 bg-white grid md:grid-cols-2 gap-4">
        <div>
          <h2 className="font-semibold text-navy text-sm mb-2">Assign reviewer</h2>
          <input className="w-full border rounded px-2 py-1 text-sm mb-1" placeholder="User ID" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} />
          <input className="w-full border rounded px-2 py-1 text-sm mb-1" placeholder="Name" value={assigneeName} onChange={(e) => setAssigneeName(e.target.value)} />
          <input className="w-full border rounded px-2 py-1 text-sm mb-2" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          <button
            type="button"
            className="px-3 py-1.5 bg-navy text-white rounded-lg text-sm"
            onClick={async () => {
              await api.assignDraftReviewer(draftId, assigneeId, assigneeName, dueDate);
              await load();
            }}
          >
            Assign
          </button>
        </div>
        <div>
          <h2 className="font-semibold text-navy text-sm mb-2">Suggestions</h2>
          <textarea className="w-full border rounded p-2 text-sm h-16 mb-2" value={suggestion} onChange={(e) => setSuggestion(e.target.value)} />
          <button
            type="button"
            className="px-3 py-1.5 border rounded-lg text-sm mb-2"
            onClick={async () => {
              await api.addReviewSuggestion(draftId, suggestion);
              setSuggestion("");
              await load();
            }}
          >
            Add suggestion
          </button>
          <ul className="text-xs space-y-2 max-h-40 overflow-y-auto">
            {((ws?.suggestions as Array<{ suggestion_id: string; body: string; status: string }>) || []).map((s) => (
              <li key={s.suggestion_id} className="border rounded p-2">
                <p className="m-0">{s.body}</p>
                <p className="text-slate-500 m-0">{s.status}</p>
                {s.status === "open" && (
                  <div className="flex gap-2 mt-1">
                    <button type="button" className="text-green-700 underline" onClick={() => api.resolveSuggestion(draftId, s.suggestion_id, true).then(load)}>
                      Accept
                    </button>
                    <button type="button" className="text-red-700 underline" onClick={() => api.resolveSuggestion(draftId, s.suggestion_id, false).then(load)}>
                      Reject
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border rounded-xl p-4 bg-white">
        <h2 className="font-semibold text-navy text-sm mb-2">Approval history</h2>
        <ul className="text-xs space-y-1 max-h-48 overflow-y-auto">
          {((ws?.timeline as Array<{ action: string; user_name: string; created_at: string; detail: string }>) || []).map((t, i) => (
            <li key={i}>
              <strong>{t.user_name}</strong> {t.action} — {t.detail}{" "}
              {t.created_at ? new Date(t.created_at).toLocaleString() : ""}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
