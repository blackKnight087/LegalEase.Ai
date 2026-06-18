"use client";



import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";

import MarkdownBox from "@/components/ui/MarkdownBox";



const HEARING_STATUSES = ["scheduled", "prepared", "attended", "order_awaited", "completed"];



export default function HearingsTab() {

  const [hearings, setHearings] = useState<Array<Record<string, unknown>>>([]);

  const [matters, setMatters] = useState<api.Matter[]>([]);

  const [busy, setBusy] = useState(false);

  const [prepMd, setPrepMd] = useState("");

  const [err, setErr] = useState("");

  const [msg, setMsg] = useState("");

  const [filterMatter, setFilterMatter] = useState("");

  const [filterStatus, setFilterStatus] = useState("");

  const [filterFrom, setFilterFrom] = useState("");

  const [filterTo, setFilterTo] = useState("");

  const [editId, setEditId] = useState("");

  const [editFields, setEditFields] = useState<Record<string, string>>({});

  const [showSchedule, setShowSchedule] = useState(false);

  const [newHearing, setNewHearing] = useState({

    matter_id: "",

    hearing_date: "",

    hearing_time: "",

    court_name: "",

    judge: "",

    purpose: "",

    status: "scheduled",

    assigned_lawyer: "",

  });



  const load = useCallback(async () => {

    try {

      const [r, m] = await Promise.all([

        api.fetchLitigationHearings({

          matter_id: filterMatter,

          status: filterStatus,

          from_date: filterFrom,

          to_date: filterTo,

        }),

        api.listMatters(),

      ]);

      setHearings(r.hearings || []);

      setMatters(m.matters || []);

      if (m.matters?.[0] && !newHearing.matter_id) {

        setNewHearing((h) => ({ ...h, matter_id: m.matters![0].matter_id }));

      }

    } catch (e) {

      setErr(e instanceof Error ? e.message : "Load failed");

    }

  }, [filterMatter, filterStatus, filterFrom, filterTo, newHearing.matter_id]);



  useEffect(() => {

    void load();

  }, [load]);



  const prep = async (matterId: string) => {

    setBusy(true);

    try {

      const r = await api.fetchCourtDayPrepPack(matterId, true);

      setPrepMd(r.markdown || "");

    } finally {

      setBusy(false);

    }

  };



  const downloadPrepPdf = async (matterId: string) => {

    setBusy(true);

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



  const startEdit = (h: Record<string, unknown>) => {

    setEditId(String(h.hearing_id));

    setEditFields({

      hearing_date: String(h.hearing_date || ""),

      hearing_time: String(h.hearing_time || ""),

      court_name: String(h.court_name || ""),

      judge: String(h.judge || ""),

      purpose: String(h.purpose || ""),

      stage: String(h.stage || ""),

      status: String(h.status || "scheduled"),

      assigned_lawyer: String(h.assigned_lawyer || ""),

    });

  };



  const saveEdit = async () => {

    if (!editId) return;

    setBusy(true);

    setErr("");

    try {

      await api.patchLitigationHearing(editId, editFields);

      setEditId("");

      setMsg("Hearing updated.");

      await load();

    } catch (e) {

      setErr(e instanceof Error ? e.message : "Update failed");

    } finally {

      setBusy(false);

    }

  };



  const schedule = async () => {

    if (!newHearing.matter_id || !newHearing.hearing_date) return;

    setBusy(true);

    setErr("");

    try {

      await api.createLitigationHearing(newHearing);

      setShowSchedule(false);

      setMsg("Hearing scheduled.");

      await load();

    } catch (e) {

      setErr(e instanceof Error ? e.message : "Schedule failed");

    } finally {

      setBusy(false);

    }

  };



  const quickStatus = async (hearingId: string, status: string) => {

    await api.patchLitigationHearing(hearingId, { status });

    await load();

  };



  return (

    <div className="p-4 sm:p-6 space-y-4">

      <div className="flex flex-wrap items-center justify-between gap-2">

        <h2 className="text-lg font-semibold text-navy">Hearing management</h2>

        <button

          type="button"

          className="text-xs px-3 py-1.5 bg-navy text-white rounded-lg"

          onClick={() => setShowSchedule((v) => !v)}

        >

          {showSchedule ? "Cancel" : "Schedule hearing"}

        </button>

      </div>

      {err && <p className="text-red-600 text-sm">{err}</p>}

      {msg && <p className="text-emerald-700 text-sm">{msg}</p>}



      <div className="flex flex-wrap gap-2 text-sm">

        <select className="border rounded-lg px-2 py-1.5" value={filterMatter} onChange={(e) => setFilterMatter(e.target.value)}>

          <option value="">All matters</option>

          {matters.map((m) => (

            <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>

          ))}

        </select>

        <select className="border rounded-lg px-2 py-1.5" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>

          <option value="">All statuses</option>

          {HEARING_STATUSES.map((s) => (

            <option key={s} value={s}>{s}</option>

          ))}

        </select>

        <input type="date" className="border rounded-lg px-2 py-1.5" value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)} />

        <input type="date" className="border rounded-lg px-2 py-1.5" value={filterTo} onChange={(e) => setFilterTo(e.target.value)} />

      </div>



      {showSchedule && (

        <section className="border rounded-xl p-4 bg-slate-50 space-y-2 text-sm">

          <h3 className="font-semibold text-navy m-0">New hearing</h3>

          <div className="grid sm:grid-cols-2 gap-2">

            <select className="border rounded-lg px-2 py-1.5" value={newHearing.matter_id} onChange={(e) => setNewHearing({ ...newHearing, matter_id: e.target.value })}>

              {matters.map((m) => (

                <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>

              ))}

            </select>

            <input type="date" className="border rounded-lg px-2 py-1.5" value={newHearing.hearing_date} onChange={(e) => setNewHearing({ ...newHearing, hearing_date: e.target.value })} />

            <input className="border rounded-lg px-2 py-1.5" placeholder="Time" value={newHearing.hearing_time} onChange={(e) => setNewHearing({ ...newHearing, hearing_time: e.target.value })} />

            <input className="border rounded-lg px-2 py-1.5" placeholder="Court" value={newHearing.court_name} onChange={(e) => setNewHearing({ ...newHearing, court_name: e.target.value })} />

            <input className="border rounded-lg px-2 py-1.5" placeholder="Judge" value={newHearing.judge} onChange={(e) => setNewHearing({ ...newHearing, judge: e.target.value })} />

            <input className="border rounded-lg px-2 py-1.5" placeholder="Purpose" value={newHearing.purpose} onChange={(e) => setNewHearing({ ...newHearing, purpose: e.target.value })} />

            <input className="border rounded-lg px-2 py-1.5" placeholder="Assigned lawyer" value={newHearing.assigned_lawyer} onChange={(e) => setNewHearing({ ...newHearing, assigned_lawyer: e.target.value })} />

          </div>

          <button type="button" disabled={busy} className="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm" onClick={() => void schedule()}>

            Save hearing

          </button>

        </section>

      )}



      <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white">

        <table className="w-full text-xs">

          <thead>

            <tr className="bg-slate-50 text-left text-slate-600">

              <th className="p-2">Date</th>

              <th className="p-2">Matter</th>

              <th className="p-2">Court</th>

              <th className="p-2">Judge</th>

              <th className="p-2">Purpose</th>

              <th className="p-2">Lawyer</th>

              <th className="p-2">Status</th>

              <th className="p-2" />

            </tr>

          </thead>

          <tbody>

            {hearings.map((h) => (

              <tr key={String(h.hearing_id)} className="border-t border-slate-100">

                <td className="p-2 whitespace-nowrap">{String(h.hearing_date || "")}</td>

                <td className="p-2 font-medium text-navy">{String(h.matter_name || "")}</td>

                <td className="p-2">{String(h.court_name || "")}</td>

                <td className="p-2">{String(h.judge || "")}</td>

                <td className="p-2 max-w-[10rem] truncate">{String(h.purpose || h.stage || "")}</td>

                <td className="p-2">{String(h.assigned_lawyer || "—")}</td>

                <td className="p-2">

                  <select

                    className="text-[10px] border rounded px-1 py-0.5"

                    value={String(h.status || "scheduled")}

                    onChange={(e) => void quickStatus(String(h.hearing_id), e.target.value)}

                  >

                    {HEARING_STATUSES.map((s) => (

                      <option key={s} value={s}>{s}</option>

                    ))}

                  </select>

                </td>

                <td className="p-2 whitespace-nowrap space-x-1">

                  <button type="button" className="text-emerald-700 font-semibold" disabled={busy} onClick={() => prep(String(h.matter_id))}>Prep</button>

                  <button type="button" className="text-blue-700 font-semibold" disabled={busy} onClick={() => void downloadPrepPdf(String(h.matter_id))}>PDF</button>

                  <button type="button" className="text-slate-600" onClick={() => startEdit(h)}>Edit</button>

                </td>

              </tr>

            ))}

          </tbody>

        </table>

      </div>



      {editId && (

        <section className="border rounded-xl p-4 bg-white space-y-2 text-sm">

          <h3 className="font-semibold text-navy m-0">Edit hearing</h3>

          <div className="grid sm:grid-cols-2 gap-2">

            {Object.entries(editFields).map(([k, v]) => (

              k === "status" ? (

                <select key={k} className="border rounded-lg px-2 py-1.5" value={v} onChange={(e) => setEditFields({ ...editFields, [k]: e.target.value })}>

                  {HEARING_STATUSES.map((s) => (

                    <option key={s} value={s}>{s}</option>

                  ))}

                </select>

              ) : (

                <input key={k} className="border rounded-lg px-2 py-1.5" placeholder={k.replace(/_/g, " ")} value={v} onChange={(e) => setEditFields({ ...editFields, [k]: e.target.value })} />

              )

            ))}

          </div>

          <div className="flex gap-2">

            <button type="button" disabled={busy} className="px-3 py-1.5 bg-navy text-white rounded-lg" onClick={() => void saveEdit()}>Save</button>

            <button type="button" className="px-3 py-1.5 border rounded-lg" onClick={() => setEditId("")}>Cancel</button>

          </div>

        </section>

      )}



      {prepMd && (

        <div className="border rounded-xl p-4 bg-slate-50 max-h-[24rem] overflow-y-auto">

          <MarkdownBox content={prepMd} />

        </div>

      )}

    </div>

  );

}


