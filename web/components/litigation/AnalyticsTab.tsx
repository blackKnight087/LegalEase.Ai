"use client";



import { useEffect, useState } from "react";

import * as api from "@/lib/api";



export default function AnalyticsTab() {

  const [data, setData] = useState<Record<string, unknown> | null>(null);



  useEffect(() => {

    void api.fetchLitigationAnalytics().then(setData);

  }, []);



  if (!data) return <p className="p-6 text-slate-500 text-sm">Loading analytics…</p>;



  const risk = (data.risk_score as Record<string, number>) || {};

  const factors = (data.risk_factors as Record<string, number>) || {};

  const courtWorkload = (data.court_workload as Array<{ court: string; hearings: number }>) || [];

  const lawyerWorkload = (data.lawyer_workload as Array<{ lawyer: string; hearings: number }>) || [];

  const maxCourt = Math.max(1, ...courtWorkload.map((c) => c.hearings));

  const maxLawyer = Math.max(1, ...lawyerWorkload.map((l) => l.hearings));



  return (

    <div className="p-4 sm:p-6 space-y-6">

      <h2 className="text-lg font-semibold text-navy">Litigation analytics</h2>

      {data.metrics_source === "computed" && (

        <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 w-fit">

          Metrics computed from live matter data

        </p>

      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">

        <div className="border rounded-xl p-4 bg-white"><p className="text-xs text-slate-500">Active cases</p><p className="text-2xl font-bold">{String(data.active_cases)}</p></div>

        <div className="border rounded-xl p-4 bg-white"><p className="text-xs text-slate-500">Disposed</p><p className="text-2xl font-bold">{String(data.disposed_cases)}</p></div>

        <div className="border rounded-xl p-4 bg-white"><p className="text-xs text-slate-500">Upcoming hearings</p><p className="text-2xl font-bold">{String(data.upcoming_hearings)}</p></div>

        <div className="border rounded-xl p-4 bg-emerald-50 border-emerald-200"><p className="text-xs text-emerald-800">Win rate</p><p className="text-2xl font-bold text-emerald-900">{String(data.win_rate_pct)}%</p></div>

      </div>

      <section className="border rounded-xl p-4 bg-slate-900 text-white">

        <h3 className="text-sm font-semibold mb-3">Litigation risk score</h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">

          {Object.entries(risk).map(([k, v]) => (

            <div key={k}>

              <p className="text-slate-400 capitalize">{k.replace(/_/g, " ")}</p>

              <p className="text-xl font-bold">{v}%</p>

            </div>

          ))}

        </div>

        {Object.keys(factors).length > 0 && (

          <p className="text-xs text-slate-400 mt-3 m-0">

            Based on: {Object.entries(factors).map(([k, v]) => `${k.replace(/_/g, " ")}=${v}`).join(" · ")}

          </p>

        )}

      </section>

      <div className="grid md:grid-cols-2 gap-4">

        <section className="border rounded-xl p-4 bg-white">

          <h3 className="text-sm font-semibold text-navy mb-3">Court workload (hearings)</h3>

          {courtWorkload.length === 0 ? (

            <p className="text-xs text-slate-500 m-0">No hearing data yet.</p>

          ) : (

            <ul className="space-y-2 m-0 p-0 list-none">

              {courtWorkload.map((c) => (

                <li key={c.court} className="text-xs">

                  <div className="flex justify-between mb-0.5">

                    <span className="truncate pr-2">{c.court}</span>

                    <span className="font-semibold tabular-nums">{c.hearings}</span>

                  </div>

                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">

                    <div className="h-full bg-emerald-600 rounded-full" style={{ width: `${(c.hearings / maxCourt) * 100}%` }} />

                  </div>

                </li>

              ))}

            </ul>

          )}

        </section>

        <section className="border rounded-xl p-4 bg-white">

          <h3 className="text-sm font-semibold text-navy mb-3">Lawyer workload (hearings)</h3>

          {lawyerWorkload.length === 0 ? (

            <p className="text-xs text-slate-500 m-0">No assigned lawyers on hearings.</p>

          ) : (

            <ul className="space-y-2 m-0 p-0 list-none">

              {lawyerWorkload.map((l) => (

                <li key={l.lawyer} className="text-xs">

                  <div className="flex justify-between mb-0.5">

                    <span className="truncate pr-2">{l.lawyer}</span>

                    <span className="font-semibold tabular-nums">{l.hearings}</span>

                  </div>

                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">

                    <div className="h-full bg-navy rounded-full" style={{ width: `${(l.hearings / maxLawyer) * 100}%` }} />

                  </div>

                </li>

              ))}

            </ul>

          )}

        </section>

      </div>

    </div>

  );

}


