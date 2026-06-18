"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as api from "@/lib/api";
import MarkdownBox from "@/components/ui/MarkdownBox";
import MatterChatHistory from "@/components/matters/MatterChatHistory";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";
import MatterDocumentUpload from "@/components/matters/MatterDocumentUpload";
import TimelineSuggestions from "@/components/matters/TimelineSuggestions";
import MatterHearingsPanel from "@/components/matters/MatterHearingsPanel";
import MatterEvidencePanel from "@/components/matters/MatterEvidencePanel";
import MatterEntitiesPanel from "@/components/matters/MatterEntitiesPanel";
import MatterKnowledgePanel from "@/components/matters/MatterKnowledgePanel";
import MatterAIPanel from "@/components/matters/MatterAIPanel";
import MatterDraftingPanel from "@/components/matters/MatterDraftingPanel";
import MatterDraftingOverviewCard from "@/components/matters/MatterDraftingOverviewCard";
import VoiceTextarea from "@/components/ui/VoiceTextarea";

type Tab =
  | "overview"
  | "documents"
  | "notes"
  | "timeline"
  | "hearings"
  | "tasks"
  | "deadlines"
  | "evidence"
  | "entities"
  | "knowledge"
  | "ai"
  | "drafting";

function MatterOverviewActions({ matterId }: { matterId: string }) {
  const [busy, setBusy] = useState(false);
  const [letter, setLetter] = useState("");
  const [err, setErr] = useState("");

  const draftLetter = async () => {
    setBusy(true);
    setErr("");
    setLetter("");
    try {
      const r = await api.fetchClientStatusLetter(matterId);
      setLetter(String(r.letter || ""));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to draft letter");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap gap-2 items-start">
      <button
        type="button"
        disabled={busy}
        onClick={() => void draftLetter()}
        className="px-3 py-2 text-sm border rounded-lg hover:bg-slate-50 disabled:opacity-50"
      >
        {busy ? "Drafting…" : "Client status letter"}
      </button>
      <Link
        href={`/matters/${matterId}/hearings`}
        className="px-3 py-2 text-sm border rounded-lg hover:bg-slate-50 no-underline text-inherit"
      >
        Hearings & prep pack
      </Link>
      {err && <p className="text-xs text-red-600 m-0 w-full">{err}</p>}
      {letter && (
        <div className="w-full rounded-xl border bg-white p-4 mt-2">
          <MarkdownBox content={letter} />
        </div>
      )}
    </div>
  );
}

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "documents", label: "Documents" },
  { id: "notes", label: "Notes" },
  { id: "timeline", label: "Timeline" },
  { id: "hearings", label: "Hearings" },
  { id: "tasks", label: "Tasks" },
  { id: "deadlines", label: "Deadlines" },
  { id: "evidence", label: "Evidence" },
  { id: "entities", label: "Entities" },
  { id: "knowledge", label: "Knowledge" },
  { id: "ai", label: "Matter AI" },
  { id: "drafting", label: "Drafting" },
];

export default function MatterDashboard({
  matterId,
  onError,
  initialTab = "overview",
}: {
  matterId: string;
  onError?: (msg: string) => void;
  initialTab?: Tab;
}) {
  const searchParams = useSearchParams();
  const [dash, setDash] = useState<api.MatterDashboard | null>(null);
  const [tab, setTab] = useState<Tab>(initialTab);

  useEffect(() => {
    const t = searchParams.get("tab");
    if (t && TABS.some((x) => x.id === t)) setTab(t as Tab);
  }, [searchParams]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [unlinked, setUnlinked] = useState<Array<{ document_id: string; filename: string }>>([]);
  const [linkDocId, setLinkDocId] = useState("");

  const [taskTitle, setTaskTitle] = useState("");
  const [taskDue, setTaskDue] = useState("");

  const [dlTitle, setDlTitle] = useState("");
  const [dlDate, setDlDate] = useState("");

  const [tlTitle, setTlTitle] = useState("");
  const [tlDate, setTlDate] = useState("");

  const reload = useCallback(async () => {
    try {
      const d = await api.getMatterDashboard(matterId);
      setDash(d);
      if (typeof window !== "undefined") {
        window.localStorage.setItem("legalease_active_matter", matterId);
      }
    } catch (e) {
      onError?.(e instanceof Error ? e.message : "Failed to load matter");
    }
  }, [matterId, onError]);

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    reload();
    api.listUnlinkedDocuments().then((r) => setUnlinked(r.documents || [])).catch(() => {});
  }, [reload]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
      await reload();
    } catch (e) {
      onError?.(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (!dash?.matter) {
    return <p className="text-sm text-slate-500 p-4">Loading matter…</p>;
  }

  const m = dash.matter;
  const kb = dash.kb_health as Record<string, unknown>;
  const kbReady = Boolean(kb.ready_for_kb_query ?? kb.healthy);

  return (
    <div className="border rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="p-4 border-b bg-gradient-to-r from-slate-50 to-blue-50">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-navy">{m.matter_name}</h2>
            <p className="text-xs text-slate-600 mt-1">
              <span className="font-medium">Case type:</span> {m.practice_area}
              {m.case_number ? ` · CN: ${m.case_number}` : ""}
            </p>
            <p className="text-xs text-slate-600">
              <span className="font-medium">Client:</span> {m.client_name || "—"}
              {m.opposing_party ? ` · Opposing: ${m.opposing_party}` : ""}
            </p>
            <p className="text-xs text-slate-600">
              <span className="font-medium">Court / venue:</span> {m.venue || "—"}
              {" · "}
              <span className="font-medium">Status:</span> {m.status_tier || "ACTIVE"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span
              className={`text-[0.65rem] font-bold uppercase px-2 py-1 rounded-full border ${
                kbReady
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : "bg-amber-50 text-amber-800 border-amber-200"
              }`}
            >
              {kbReady ? "Matter RAG ready" : "Index pending — upload & link docs"}
            </span>
            <Link
              href={`/?matter=${matterId}`}
              className="text-xs font-medium text-blue-700 hover:underline"
              onClick={() => {
                if (typeof window !== "undefined") {
                  window.localStorage.setItem("legalease_active_matter", matterId);
                }
              }}
            >
              Open AI chat (this matter only) →
            </Link>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                tab === t.id ? "bg-navy text-white" : "bg-white border text-slate-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 min-h-[280px]">
        {tab === "overview" && (
          <div className="space-y-4">
          <MatterOverviewActions matterId={matterId} />
          <MatterDraftingOverviewCard overview={dash.drafting} matterId={matterId} />
          <MatterIntelligenceStatus matterId={matterId} />
          <TimelineSuggestions matterId={matterId} onChanged={reload} />
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Documents" value={String(dash.stats?.document_count ?? 0)} />
            <Stat
              label="KB vectors (matter)"
              value={String(
                (kb.faiss_chunks as number | undefined) ??
                  (kb.index_vectors as number | undefined) ??
                  (kb.vector_count as number | undefined) ??
                  (dash.smoke as Record<string, unknown> | undefined)?.vector_count ??
                  0
              )}
            />
            <Stat label="Open tasks" value={String(dash.stats?.open_tasks ?? 0)} />
            <Stat label="Pending deadlines" value={String(dash.stats?.pending_deadlines ?? 0)} />
            <Stat label="Hearings" value={String(dash.stats?.upcoming_hearings ?? 0)} />
            <Stat
              label="AI confidence"
              value={`${dash.stats?.ai_confidence ?? (dash as { smoke?: { ai_confidence?: number } }).smoke?.ai_confidence ?? 0}%`}
            />
            <Stat
              label="Timeline"
              value={`${dash.stats?.timeline_events ?? 0} events`}
            />
            <div className="sm:col-span-2 lg:col-span-4 p-3 rounded-lg bg-violet-50 border border-violet-100 text-xs">
              <b className="text-violet-900">Matter-linked retrieval</b>
              <p className="text-violet-800 mt-1">
                Questions in Knowledge Base mode search only documents linked to this matter —
                not your global or other-matter files.
              </p>
              {dash.autopilot && Object.keys(dash.autopilot).length > 0 && (
                <pre className="mt-2 text-[0.65rem] overflow-auto max-h-24 opacity-80">
                  {JSON.stringify(dash.autopilot, null, 2)}
                </pre>
              )}
            </div>
          </div>
          </div>
        )}

        {tab === "documents" && (
          <div className="space-y-4">
            <MatterDocumentUpload matterId={matterId} onComplete={reload} />
            <ul className="space-y-2">
              {(dash.documents || []).map((d) => {
                const isPriv = Boolean(
                  (d as { privileged?: number | boolean }).privileged
                );
                return (
                  <li
                    key={d.document_id}
                    className="text-sm p-2 border rounded-lg bg-slate-50 flex flex-wrap items-center justify-between gap-2"
                  >
                    <span>
                      {d.filename}
                      {d.index_status && (
                        <span className="ml-2 text-[0.65rem] text-slate-500">
                          ({d.index_status})
                        </span>
                      )}
                    </span>
                    <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isPriv}
                        disabled={busy}
                        onChange={(e) =>
                          run(async () => {
                            await api.patchMatterDocumentMeta(
                              matterId,
                              d.document_id,
                              e.target.checked
                            );
                          })
                        }
                      />
                      Privileged
                    </label>
                  </li>
                );
              })}
              {!dash.documents?.length && (
                <li className="text-sm text-slate-500">No documents linked yet.</li>
              )}
            </ul>
            <div className="flex flex-wrap gap-2 items-center border-t pt-3">
              <select
                className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[200px]"
                value={linkDocId}
                onChange={(e) => setLinkDocId(e.target.value)}
              >
                <option value="">Link unlinked document…</option>
                {unlinked.map((d) => (
                  <option key={d.document_id} value={d.document_id}>
                    {d.filename}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={busy || !linkDocId}
                onClick={() =>
                  run(async () => {
                    await api.linkMatterDocument(matterId, linkDocId);
                    setLinkDocId("");
                    const r = await api.listUnlinkedDocuments();
                    setUnlinked(r.documents || []);
                  })
                }
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
              >
                Link to matter
              </button>
              <Link href="/documents" className="text-xs text-blue-700">
                Upload more →
              </Link>
            </div>
          </div>
        )}

        {tab === "notes" && (
          <div className="space-y-3">
            <div className="max-h-48 overflow-y-auto space-y-2">
              {(dash.notes || []).map((n) => (
                <div key={n.note_id} className="text-xs p-2 bg-slate-50 rounded border">
                  {n.raw_content}
                </div>
              ))}
            </div>
            <div className="flex gap-2 items-end">
              <VoiceTextarea
                className="flex-1"
                rows={2}
                matterId={matterId}
                polishOnStop
                placeholder="Case note / strategy…"
                value={note}
                onChange={setNote}
              />
              <button
                type="button"
                disabled={busy || !note.trim()}
                onClick={() =>
                  run(async () => {
                    await api.addMatterNote(matterId, note);
                    setNote("");
                  })
                }
                className="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm"
              >
                Save
              </button>
            </div>
          </div>
        )}

        {tab === "timeline" && (
          <div className="space-y-3">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await api.generateMatterTimeline(matterId, true);
                })
              }
              className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
            >
              Build timeline from documents
            </button>
            <TimelineSuggestions matterId={matterId} onChanged={reload} />
            <ul className="space-y-2 max-h-52 overflow-y-auto">
              {(dash.timeline || []).map((ev) => (
                <li key={ev.event_id} className="text-xs border-l-4 border-amber-500 pl-3 py-1">
                  <span className="text-slate-500">{ev.event_date}</span>
                  <b className="block text-navy">{ev.title}</b>
                  {ev.description ? <span>{ev.description}</span> : null}
                </li>
              ))}
            </ul>
            <div className="grid sm:grid-cols-3 gap-2">
              <input
                className="border rounded-lg px-2 py-1.5 text-sm"
                placeholder="Event title"
                value={tlTitle}
                onChange={(e) => setTlTitle(e.target.value)}
              />
              <input
                type="date"
                className="border rounded-lg px-2 py-1.5 text-sm"
                value={tlDate}
                onChange={(e) => setTlDate(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || !tlTitle}
                onClick={() =>
                  run(async () => {
                    await api.addMatterTimeline(matterId, {
                      title: tlTitle,
                      event_date: tlDate,
                    });
                    setTlTitle("");
                  })
                }
                className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Add event
              </button>
            </div>
          </div>
        )}

        {tab === "hearings" && <MatterHearingsPanel matterId={matterId} />}

        {tab === "tasks" && (
          <div className="space-y-3">
            <ul className="space-y-2">
              {(dash.tasks || []).map((t) => (
                <li
                  key={t.task_id}
                  className="flex items-center justify-between text-sm p-2 border rounded-lg"
                >
                  <span>
                    {t.title}
                    {t.due_date ? ` · due ${t.due_date}` : ""}
                  </span>
                  <button
                    type="button"
                    disabled={busy || t.status === "done"}
                    onClick={() =>
                      run(async () => {
                        await api.patchMatterTask(matterId, t.task_id!, { status: "done" });
                      })
                    }
                    className="text-xs text-emerald-700 font-medium"
                  >
                    {t.status === "done" ? "Done" : "Mark done"}
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <input
                className="flex-1 border rounded-lg px-2 py-1.5 text-sm"
                placeholder="Task title"
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
              />
              <input
                type="date"
                className="border rounded-lg px-2 py-1.5 text-sm"
                value={taskDue}
                onChange={(e) => setTaskDue(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || !taskTitle}
                onClick={() =>
                  run(async () => {
                    await api.addMatterTask(matterId, { title: taskTitle, due_date: taskDue });
                    setTaskTitle("");
                  })
                }
                className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Add task
              </button>
            </div>
          </div>
        )}

        {tab === "deadlines" && (
          <div className="space-y-3">
            <ul className="space-y-2">
              {(dash.deadlines || []).map((d) => (
                <li key={d.deadline_id} className="text-sm p-2 border rounded-lg bg-red-50/50">
                  <b className="text-red-900">{d.due_date}</b> — {d.title}
                  <span className="block text-xs text-slate-600">{d.deadline_type}</span>
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <input
                className="flex-1 border rounded-lg px-2 py-1.5 text-sm"
                placeholder="Deadline title"
                value={dlTitle}
                onChange={(e) => setDlTitle(e.target.value)}
              />
              <input
                type="date"
                className="border rounded-lg px-2 py-1.5 text-sm"
                value={dlDate}
                onChange={(e) => setDlDate(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || !dlTitle || !dlDate}
                onClick={() =>
                  run(async () => {
                    await api.addMatterDeadline(matterId, {
                      title: dlTitle,
                      due_date: dlDate,
                    });
                    setDlTitle("");
                  })
                }
                className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Add deadline
              </button>
            </div>
          </div>
        )}

        {tab === "knowledge" && (
          <MatterKnowledgePanel matterId={matterId} onChanged={reload} />
        )}

        {tab === "entities" && <MatterEntitiesPanel matterId={matterId} />}

        {tab === "evidence" && <MatterEvidencePanel matterId={matterId} />}

        {tab === "ai" && <MatterAIPanel matterId={matterId} />}

        {tab === "drafting" && <MatterDraftingPanel matterId={matterId} />}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 rounded-lg border bg-slate-50">
      <p className="text-[0.65rem] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-xl font-semibold text-navy mt-1">{value}</p>
    </div>
  );
}
