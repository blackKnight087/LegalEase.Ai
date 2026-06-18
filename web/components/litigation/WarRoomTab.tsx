"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as api from "@/lib/api";

export default function WarRoomTab() {
  const searchParams = useSearchParams();
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState(searchParams.get("matter") || "");
  const [room, setRoom] = useState<Record<string, unknown> | null>(null);
  const [newTask, setNewTask] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    if (!matterId) return;
    setRoom(await api.fetchLitigationWarRoom(matterId));
  }, [matterId]);

  useEffect(() => {
    void api.listMatters().then((r) => {
      setMatters(r.matters || []);
      const fromUrl = searchParams.get("matter") || "";
      const mid = fromUrl || r.matters?.[0]?.matter_id || "";
      if (mid) setMatterId(mid);
    });
  }, [searchParams]);

  useEffect(() => {
    void load();
  }, [load]);

  const m = (room?.matter as Record<string, unknown>) || {};
  const deadlines = (room?.deadlines as Array<Record<string, unknown>>) || [];

  const addTask = async () => {
    if (!matterId || !newTask.trim()) return;
    setBusy(true);
    try {
      await api.createLitigationTask({ matter_id: matterId, title: newTask.trim() });
      setNewTask("");
      setMsg("Task added.");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const downloadPrepPdf = async () => {
    if (!matterId) return;
    setBusy(true);
    setErr("");
    try {
      const blob = await api.downloadCourtDayPrepPdf(matterId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "hearing-prep.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "PDF download failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <h2 className="text-lg font-semibold text-navy">Matter war room</h2>
      <select className="w-full border rounded-lg px-3 py-2 text-sm max-w-md" value={matterId} onChange={(e) => setMatterId(e.target.value)}>
        {matters.map((m) => (
          <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>
        ))}
      </select>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      {msg && <p className="text-sm text-emerald-700">{msg}</p>}
      {!room ? (
        <p className="text-slate-500 text-sm">Select a matter.</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <Link href="/litigation?tab=hearings" className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50">Hearings tab →</Link>
            <Link href="/litigation?tab=tasks" className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50">Tasks tab →</Link>
            <Link href="/litigation?tab=orders" className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50">Orders tab →</Link>
            <button type="button" disabled={busy} className="text-xs px-3 py-1.5 bg-emerald-700 text-white rounded-lg" onClick={() => void downloadPrepPdf()}>
              Download prep pack PDF
            </button>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <section className="border rounded-xl p-4 bg-white space-y-2 text-sm">
              <h3 className="font-semibold text-navy">{String(m.matter_name)}</h3>
              <p>{String(m.client_name)} · {String(m.case_number)}</p>
              <p>{String(m.venue)}</p>
              <div className="flex flex-wrap gap-2 pt-2">
                <Link href={`/collaboration`} className="text-xs text-emerald-700 font-medium">Chat →</Link>
                <Link href={`/matters/${matterId}`} className="text-xs text-emerald-700 font-medium">Documents →</Link>
                <Link href={`/litigation?tab=evidence`} className="text-xs text-emerald-700 font-medium">Evidence →</Link>
              </div>
            </section>
            <section className="border rounded-xl p-4 bg-white">
              <h3 className="text-sm font-semibold mb-2">Deadlines ({deadlines.length})</h3>
              <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
                {deadlines.length === 0 ? (
                  <li className="text-slate-500">No deadlines on file.</li>
                ) : (
                  deadlines.map((d) => (
                    <li key={String(d.deadline_id)}>
                      <span className="font-mono text-slate-500">{String(d.due_date || "").slice(0, 10)}</span> — {String(d.title)}
                    </li>
                  ))
                )}
              </ul>
            </section>
            <section className="border rounded-xl p-4 bg-white">
              <h3 className="text-sm font-semibold mb-2">Hearings ({((room.hearings as unknown[]) || []).length})</h3>
              <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
                {((room.hearings as Array<Record<string, unknown>>) || []).map((h) => (
                  <li key={String(h.hearing_id)}>{String(h.hearing_date)} — {String(h.purpose)}</li>
                ))}
              </ul>
            </section>
            <section className="border rounded-xl p-4 bg-white">
              <h3 className="text-sm font-semibold mb-2">Quick add task</h3>
              <div className="flex gap-2">
                <input className="flex-1 border rounded-lg px-2 py-1.5 text-xs" value={newTask} onChange={(e) => setNewTask(e.target.value)} placeholder="Task title" />
                <button type="button" disabled={busy} className="text-xs px-3 py-1.5 bg-navy text-white rounded-lg" onClick={() => void addTask()}>Add</button>
              </div>
              <ul className="text-xs space-y-1 mt-2">
                {((room.tasks as Array<Record<string, unknown>>) || []).slice(0, 6).map((t) => (
                  <li key={String(t.task_id)}>{String(t.title)}</li>
                ))}
              </ul>
            </section>
            <section className="border rounded-xl p-4 bg-white md:col-span-2">
              <h3 className="text-sm font-semibold mb-2">Orders</h3>
              <ul className="text-xs space-y-1 grid sm:grid-cols-2 gap-1">
                {((room.orders as Array<Record<string, unknown>>) || []).slice(0, 8).map((o) => (
                  <li key={String(o.order_id)}>{String(o.title)}</li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
