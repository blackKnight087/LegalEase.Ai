"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";

type Session = {
  thread_id: string;
  question: string;
  preview?: string;
  created_at?: string;
};

export default function MatterChatHistory({ matterId }: { matterId: string }) {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.getChatHistory(50, matterId);
      const items = (r.sessions || [])
        .map((s) => ({
          thread_id: String(s.thread_id || s.id || ""),
          question: String(s.question || "Chat"),
          preview: String(s.preview || ""),
          created_at: String(s.created_at || ""),
        }))
        .filter((s) => s.thread_id);
      setSessions(items);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load chat history");
      setSessions([]);
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const deleteOne = async (threadId: string, label: string) => {
    if (!window.confirm(`Delete chat "${label}"? This cannot be undone.`)) return;
    setBusy(true);
    setErr("");
    try {
      await api.deleteChatThread(threadId);
      setSessions((prev) => prev.filter((s) => s.thread_id !== threadId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const deleteAll = async () => {
    if (!sessions.length) return;
    if (
      !window.confirm(
        `Delete all ${sessions.length} chat(s) for this matter? This cannot be undone.`
      )
    ) {
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await api.deleteMatterChatHistory(matterId);
      setSessions([]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete all failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-navy m-0">Matter chat history</h3>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy || !sessions.length}
            onClick={() => void deleteAll()}
            className="text-xs px-3 py-1.5 rounded-lg border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            Delete all
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void load()}
            className="text-xs px-3 py-1.5 rounded-lg border hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>
      </div>
      {err && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}
      {sessions.length === 0 ? (
        <p className="text-xs text-slate-500 m-0">No saved chats for this matter yet.</p>
      ) : (
        <ul className="space-y-2 max-h-56 overflow-y-auto">
          {sessions.map((s) => (
            <li
              key={s.thread_id}
              className="flex items-center gap-2 text-sm p-2 border rounded-lg bg-slate-50"
            >
              <button
                type="button"
                className="flex-1 min-w-0 text-left hover:underline"
                onClick={() => router.push(`/?matter=${matterId}&thread=${encodeURIComponent(s.thread_id)}`)}
              >
                <span className="block truncate font-medium text-navy">{s.question}</span>
                {s.preview && (
                  <span className="block truncate text-xs text-slate-500">{s.preview}</span>
                )}
                {s.created_at && (
                  <span className="block text-[0.65rem] text-slate-400">{s.created_at}</span>
                )}
              </button>
              <button
                type="button"
                disabled={busy}
                title="Delete chat"
                onClick={() => void deleteOne(s.thread_id, s.question)}
                className="shrink-0 px-2 py-1 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      <Link
        href={`/?matter=${matterId}`}
        className="inline-block text-xs font-medium text-blue-700 hover:underline"
      >
        Start new matter chat
      </Link>
    </div>
  );
}
