"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

type Props = {
  draftId: string;
  status: string;
  onStatusChange: (s: string) => void;
  onErr: (msg: string) => void;
  onOk: (msg: string) => void;
};

export default function ApprovalWorkflowPanel({
  draftId,
  status,
  onStatusChange,
  onErr,
  onOk,
}: Props) {
  const [assignments, setAssignments] = useState<Array<Record<string, unknown>>>([]);
  const [timeline, setTimeline] = useState<Array<Record<string, unknown>>>([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [assigneeName, setAssigneeName] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [a, hub] = await Promise.all([
      api.listDraftAssignments(draftId),
      api.getCollaborationHub(draftId).catch(() => null),
    ]);
    setAssignments(a.assignments || []);
    if (hub) setTimeline(hub.timeline || []);
  }, [draftId]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const assign = async () => {
    if (!assigneeId.trim()) {
      onErr("Enter assignee user ID");
      return;
    }
    setBusy(true);
    try {
      await api.assignDraftReviewer(draftId, assigneeId, assigneeName, dueDate);
      await load();
      onStatusChange("in_review");
      onOk("Reviewer assigned");
    } catch (e) {
      onErr(e instanceof Error ? e.message : "Assign failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-2 text-xs space-y-3 overflow-y-auto le-scroll">
      <h3 className="font-semibold text-navy">Approval workflow</h3>
      <p className="m-0">
        Status: <strong className="capitalize">{status.replace(/_/g, " ")}</strong>
      </p>
      <div className="flex flex-col gap-1">
        <button
          type="button"
          disabled={busy}
          className="py-1.5 border rounded-lg bg-white hover:bg-slate-50"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.sendPartnerReview(draftId);
              onStatusChange(r.document.status);
              onOk("Sent for partner review");
              await load();
            } catch (e) {
              onErr(e instanceof Error ? e.message : "Failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Send to partner review
        </button>
        <button
          type="button"
          disabled={busy}
          className="py-1.5 bg-navy text-white rounded-lg"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.partnerApproveDraft(draftId, note);
              onStatusChange(r.document.status);
              onOk("Partner approved");
              await load();
            } catch (e) {
              onErr(e instanceof Error ? e.message : "Failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Partner approve
        </button>
        <button
          type="button"
          disabled={busy}
          className="py-1.5 border border-red-200 text-red-800 rounded-lg"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api.partnerRevisionDraft(draftId, note);
              onStatusChange(r.document.status);
              onOk("Returned for revision");
              await load();
            } catch (e) {
              onErr(e instanceof Error ? e.message : "Failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Request revision
        </button>
      </div>
      <input className="w-full border rounded px-2 py-1" placeholder="Approval note" value={note} onChange={(e) => setNote(e.target.value)} />

      <div className="border-t pt-2">
        <p className="font-medium m-0 mb-1">Assign reviewer</p>
        <input className="w-full border rounded px-2 py-1 mb-1" placeholder="User ID" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} />
        <input className="w-full border rounded px-2 py-1 mb-1" placeholder="Name" value={assigneeName} onChange={(e) => setAssigneeName(e.target.value)} />
        <input type="date" className="w-full border rounded px-2 py-1 mb-1" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        <button type="button" disabled={busy} onClick={assign} className="w-full py-1.5 border rounded-lg">
          Assign
        </button>
      </div>

      <div>
        <p className="font-medium m-0 mb-1">Assignments</p>
        <ul className="space-y-1 m-0 p-0 list-none">
          {assignments.map((a) => (
            <li key={String(a.assignment_id)} className="border rounded p-1.5 bg-white">
              {String(a.assignee_name)} · {String(a.role)} · {String(a.status)}
            </li>
          ))}
          {assignments.length === 0 && <li className="text-slate-400">No assignments</li>}
        </ul>
      </div>

      <div>
        <p className="font-medium m-0 mb-1">Activity</p>
        <ul className="space-y-0.5 max-h-32 overflow-y-auto text-[10px] text-slate-600 m-0 p-0 list-none">
          {timeline.slice(0, 12).map((t, i) => (
            <li key={i}>
              <strong>{String(t.user_name)}</strong> {String(t.action)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
