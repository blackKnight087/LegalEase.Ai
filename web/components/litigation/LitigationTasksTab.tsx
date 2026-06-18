"use client";



import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";



type Filter = "all" | "open" | "done";



export default function LitigationTasksTab() {

  const [tasks, setTasks] = useState<Array<Record<string, unknown>>>([]);

  const [templates, setTemplates] = useState<string[]>([]);

  const [matters, setMatters] = useState<api.Matter[]>([]);

  const [matterId, setMatterId] = useState("");

  const [title, setTitle] = useState("");

  const [dueDate, setDueDate] = useState("");

  const [assignee, setAssignee] = useState("");

  const [priority, setPriority] = useState("");

  const [filter, setFilter] = useState<Filter>("all");



  const load = useCallback(async () => {

    const [t, m] = await Promise.all([api.fetchLitigationTasks(), api.listMatters()]);

    setTasks(t.tasks || []);

    setTemplates(t.templates || []);

    setMatters(m.matters || []);

    if (m.matters?.[0] && !matterId) setMatterId(m.matters[0].matter_id);

  }, [matterId]);



  useEffect(() => {

    void load();

  }, [load]);



  const add = async (taskTitle: string) => {

    if (!matterId || !taskTitle) return;

    await api.createLitigationTask({

      matter_id: matterId,

      title: taskTitle,

      due_date: dueDate,

      assignee,

      priority,

    });

    setTitle("");

    setDueDate("");

    setAssignee("");

    setPriority("");

    await load();

  };



  const complete = async (taskId: string) => {

    await api.patchLitigationTask(taskId, { status: "done" });

    await load();

  };



  const remove = async (taskId: string) => {

    await api.deleteLitigationTask(taskId);

    await load();

  };



  const filtered = tasks.filter((t) => {

    const st = String(t.status || "").toLowerCase();

    if (filter === "open") return !["done", "completed", "cancelled"].includes(st);

    if (filter === "done") return ["done", "completed"].includes(st);

    return true;

  });



  return (

    <div className="p-4 sm:p-6 space-y-4">

      <h2 className="text-lg font-semibold text-navy">Litigation tasks</h2>

      <div className="flex flex-wrap gap-2">

        {(["all", "open", "done"] as Filter[]).map((f) => (

          <button

            key={f}

            type="button"

            onClick={() => setFilter(f)}

            className={`px-3 py-1 rounded-lg text-xs border ${filter === f ? "bg-navy text-white border-navy" : "border-slate-200"}`}

          >

            {f.charAt(0).toUpperCase() + f.slice(1)}

          </button>

        ))}

      </div>

      <div className="flex flex-wrap gap-2">

        <select className="border rounded-lg px-3 py-2 text-sm" value={matterId} onChange={(e) => setMatterId(e.target.value)}>

          {matters.map((m) => (

            <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>

          ))}

        </select>

        <input className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[10rem]" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title" />

        <input type="date" className="border rounded-lg px-3 py-2 text-sm" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />

        <input className="border rounded-lg px-3 py-2 text-sm" value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Assignee" />

        <select className="border rounded-lg px-3 py-2 text-sm" value={priority} onChange={(e) => setPriority(e.target.value)}>

          <option value="">Priority</option>

          <option value="low">Low</option>

          <option value="medium">Medium</option>

          <option value="high">High</option>

          <option value="urgent">Urgent</option>

        </select>

        <button type="button" onClick={() => add(title)} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Add</button>

      </div>

      <div className="flex flex-wrap gap-2">

        {templates.map((t) => (

          <button key={t} type="button" onClick={() => add(t)} className="text-xs border border-slate-200 rounded-full px-3 py-1 hover:bg-slate-50">

            + {t}

          </button>

        ))}

      </div>

      <ul className="space-y-2">

        {filtered.map((t) => {

          const done = ["done", "completed"].includes(String(t.status || "").toLowerCase());

          return (

            <li key={String(t.task_id)} className="border rounded-lg px-4 py-2 text-sm bg-white flex flex-wrap justify-between gap-2 items-center">

              <span className={done ? "line-through text-slate-400" : ""}>

                <b>{String(t.matter_name)}</b> — {String(t.title)}

                {t.assignee ? <span className="text-slate-500 ml-2">@{String(t.assignee)}</span> : null}

              </span>

              <div className="flex items-center gap-2">

                <span className="text-slate-500 text-xs">{String(t.due_date || t.status)}</span>

                {!done && (

                  <button type="button" className="text-xs text-emerald-700 font-medium" onClick={() => void complete(String(t.task_id))}>

                    Complete

                  </button>

                )}

                <button type="button" className="text-xs text-red-600" onClick={() => void remove(String(t.task_id))}>

                  Delete

                </button>

              </div>

            </li>

          );

        })}

      </ul>

    </div>

  );

}


