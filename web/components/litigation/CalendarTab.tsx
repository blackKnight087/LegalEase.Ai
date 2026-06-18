"use client";



import { useCallback, useEffect, useMemo, useState } from "react";

import * as api from "@/lib/api";



type View = "month" | "week" | "day";



function shiftMonth(year: number, month: number, delta: number) {

  let m = month + delta;

  let y = year;

  while (m < 1) {

    m += 12;

    y -= 1;

  }

  while (m > 12) {

    m -= 12;

    y += 1;

  }

  return { year: y, month: m };

}



export default function CalendarTab() {

  const now = new Date();

  const [view, setView] = useState<View>("month");

  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);

  const [year, setYear] = useState(now.getFullYear());

  const [month, setMonth] = useState(now.getMonth() + 1);



  const load = useCallback(async () => {

    const r = await api.fetchLitigationCalendar(year, month);

    setEvents(r.events || []);

  }, [year, month]);



  useEffect(() => {

    void load();

  }, [load]);



  const today = now.toISOString().slice(0, 10);



  const filtered =

    view === "day"

      ? events.filter((e) => String(e.date) === today)

      : view === "week"

        ? events.filter((e) => {

            const d = String(e.date);

            const t = new Date(today);

            const end = new Date(t);

            end.setDate(end.getDate() + 7);

            return d >= today && d <= end.toISOString().slice(0, 10);

          })

        : events;



  const monthGrid = useMemo(() => {

    const first = new Date(year, month - 1, 1);

    const startPad = first.getDay();

    const daysInMonth = new Date(year, month, 0).getDate();

    const cells: Array<{ day: number | null; date: string }> = [];

    for (let i = 0; i < startPad; i++) cells.push({ day: null, date: "" });

    for (let d = 1; d <= daysInMonth; d++) {

      const date = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

      cells.push({ day: d, date });

    }

    return cells;

  }, [year, month]);



  const eventsByDate = useMemo(() => {

    const map: Record<string, Array<Record<string, unknown>>> = {};

    for (const ev of events) {

      const d = String(ev.date || "");

      if (!d) continue;

      map[d] = map[d] || [];

      map[d].push(ev);

    }

    return map;

  }, [events]);



  const prevMonth = () => {

    const next = shiftMonth(year, month, -1);

    setYear(next.year);

    setMonth(next.month);

  };



  const nextMonth = () => {

    const next = shiftMonth(year, month, 1);

    setYear(next.year);

    setMonth(next.month);

  };



  return (

    <div className="p-4 sm:p-6 space-y-4">

      <div className="flex flex-wrap gap-2 items-center justify-between">

        <h2 className="text-lg font-semibold text-navy">Court calendar</h2>

        <div className="flex gap-2">

          {(["month", "week", "day"] as View[]).map((v) => (

            <button

              key={v}

              type="button"

              onClick={() => setView(v)}

              className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${

                view === v ? "bg-navy text-white border-navy" : "border-slate-200"

              }`}

            >

              {v.charAt(0).toUpperCase() + v.slice(1)}

            </button>

          ))}

        </div>

      </div>

      <div className="flex gap-2 items-center text-sm">

        <button type="button" className="border px-2 py-1 rounded" onClick={prevMonth}>←</button>

        <span className="font-medium">{year} — {month.toString().padStart(2, "0")}</span>

        <button type="button" className="border px-2 py-1 rounded" onClick={nextMonth}>→</button>

        <a

          href="#"

          onClick={(e) => {

            e.preventDefault();

            void api.downloadHearingsCalendar(90);

          }}

          className="ml-auto text-emerald-700 font-medium text-xs"

        >

          Export ICS (Google / Outlook)

        </a>

      </div>



      {view === "month" && (

        <div className="border rounded-xl overflow-hidden bg-white">

          <div className="grid grid-cols-7 bg-slate-50 text-[10px] font-semibold text-slate-500">

            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (

              <div key={d} className="p-2 text-center border-b border-slate-100">{d}</div>

            ))}

          </div>

          <div className="grid grid-cols-7">

            {monthGrid.map((cell, i) => {

              const dayEvents = cell.date ? eventsByDate[cell.date] || [] : [];

              const isToday = cell.date === today;

              return (

                <div

                  key={i}

                  className={`min-h-[4.5rem] p-1 border-b border-r border-slate-100 text-xs ${isToday ? "bg-emerald-50/60" : ""}`}

                >

                  {cell.day != null && (

                    <>

                      <p className={`font-semibold m-0 mb-0.5 ${isToday ? "text-emerald-800" : "text-slate-600"}`}>{cell.day}</p>

                      {dayEvents.slice(0, 3).map((ev, j) => (

                        <p key={j} className={`m-0 truncate text-[10px] ${ev.type === "deadline" ? "text-rose-700" : "text-emerald-800"}`}>

                          {String(ev.title).slice(0, 18)}

                        </p>

                      ))}

                      {dayEvents.length > 3 && <p className="text-[10px] text-slate-400 m-0">+{dayEvents.length - 3}</p>}

                    </>

                  )}

                </div>

              );

            })}

          </div>

        </div>

      )}



      <ul className="space-y-2">

        {filtered.length === 0 && <li className="text-sm text-slate-500">No events in this view.</li>}

        {filtered.map((ev, i) => (

          <li key={i} className="border border-slate-200 rounded-lg px-4 py-3 text-sm flex gap-3 bg-white">

            <span className="font-mono text-slate-500 w-24 shrink-0">{String(ev.date)}</span>

            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded h-fit ${ev.type === "deadline" ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800"}`}>

              {String(ev.type)}

            </span>

            <div>

              <p className="font-medium text-navy">{String(ev.title)}</p>

              {ev.court ? <p className="text-slate-600">{String(ev.court)}</p> : null}

            </div>

          </li>

        ))}

      </ul>

    </div>

  );

}


