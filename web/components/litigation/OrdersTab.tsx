"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import * as api from "@/lib/api";



const ORDER_TYPES = ["order", "judgment", "interim_order", "application", "reply", "affidavit"];



export default function OrdersTab() {
  const searchParams = useSearchParams();
  const urlMatter = searchParams.get("matter") || "";

  const [orders, setOrders] = useState<Array<Record<string, unknown>>>([]);

  const [matters, setMatters] = useState<api.Matter[]>([]);

  const [matterId, setMatterId] = useState("");

  const [title, setTitle] = useState("");

  const [summary, setSummary] = useState("");

  const [orderDate, setOrderDate] = useState("");

  const [judge, setJudge] = useState("");

  const [orderType, setOrderType] = useState("order");

  const [q, setQ] = useState("");

  const [awaitingOnly, setAwaitingOnly] = useState(false);

  const [editId, setEditId] = useState("");

  const [editFields, setEditFields] = useState<Record<string, string>>({});



  const load = useCallback(async () => {

    const [o, m] = await Promise.all([api.fetchLitigationOrders("", q), api.listMatters()]);

    let list = o.orders || [];

    if (awaitingOnly) {

      list = list.filter((row) => !String(row.summary || "").trim());

    }

    setOrders(list);

    setMatters(m.matters || []);

  }, [q, awaitingOnly]);



  useEffect(() => {
    if (urlMatter) setMatterId(urlMatter);
  }, [urlMatter]);

  useEffect(() => {
    void load();
  }, [load]);



  const save = async () => {

    if (!matterId || !title) return;

    await api.saveLitigationOrder({

      matter_id: matterId,

      title,

      summary,

      order_type: orderType,

      order_date: orderDate,

      judge,

    });

    setTitle("");

    setSummary("");

    setOrderDate("");

    setJudge("");

    await load();

  };



  const startEdit = (o: Record<string, unknown>) => {

    setEditId(String(o.order_id));

    setEditFields({

      title: String(o.title || ""),

      summary: String(o.summary || ""),

      order_date: String(o.order_date || ""),

      judge: String(o.judge || ""),

      order_type: String(o.order_type || "order"),

    });

  };



  const saveEdit = async () => {

    if (!editId) return;

    await api.patchLitigationOrder(editId, editFields);

    setEditId("");

    await load();

  };



  const remove = async (orderId: string) => {

    await api.deleteLitigationOrder(orderId);

    await load();

  };



  return (

    <div className="p-4 sm:p-6 space-y-4">

      <h2 className="text-lg font-semibold text-navy">Orders & judgments repository</h2>

      <div className="flex flex-wrap gap-2 items-center">

        <input className="flex-1 min-w-[12rem] border rounded-lg px-3 py-2 text-sm" placeholder="Search orders…" value={q} onChange={(e) => setQ(e.target.value)} />

        <label className="flex items-center gap-2 text-sm cursor-pointer">

          <input type="checkbox" checked={awaitingOnly} onChange={(e) => setAwaitingOnly(e.target.checked)} />

          Awaiting review (empty summary)

        </label>

      </div>

      <div className="grid sm:grid-cols-2 gap-2">

        <select className="border rounded-lg px-3 py-2 text-sm" value={matterId} onChange={(e) => setMatterId(e.target.value)}>

          <option value="">Select matter</option>

          {matters.map((m) => (

            <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>

          ))}

        </select>

        <select className="border rounded-lg px-3 py-2 text-sm" value={orderType} onChange={(e) => setOrderType(e.target.value)}>

          {ORDER_TYPES.map((t) => (

            <option key={t} value={t}>{t.replace(/_/g, " ")}</option>

          ))}

        </select>

        <input className="border rounded-lg px-3 py-2 text-sm" placeholder="Order title" value={title} onChange={(e) => setTitle(e.target.value)} />

        <input type="date" className="border rounded-lg px-3 py-2 text-sm" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />

        <input className="border rounded-lg px-3 py-2 text-sm" placeholder="Judge" value={judge} onChange={(e) => setJudge(e.target.value)} />

        <textarea className="border rounded-lg px-3 py-2 text-sm sm:col-span-2" rows={2} placeholder="Summary" value={summary} onChange={(e) => setSummary(e.target.value)} />

        <button type="button" onClick={() => void save()} className="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm w-fit">Save order</button>

      </div>

      <ul className="space-y-2">

        {orders.map((o) => (

          <li key={String(o.order_id)} className="border rounded-lg p-4 bg-white text-sm">

            <div className="flex flex-wrap justify-between gap-2">

              <div>

                <p className="font-semibold text-navy m-0">{String(o.title)}</p>

                <p className="text-slate-600 m-0">{String(o.matter_name)} · {String(o.order_date || "—")} · {String(o.order_type)}</p>

                {o.judge ? <p className="text-slate-500 m-0 text-xs">Judge: {String(o.judge)}</p> : null}

                {o.summary ? <p className="text-slate-500 mt-1 m-0">{String(o.summary)}</p> : (

                  <p className="text-amber-700 text-xs mt-1 m-0">Awaiting summary review</p>

                )}
                {o.linked_draft_id ? (
                  <p className="mt-1 m-0">
                    <Link
                      href={String(o.draft_editor_url || `/drafting/${o.linked_draft_id}`)}
                      className="text-xs text-navy font-medium underline"
                    >
                      Open linked draft →
                    </Link>
                  </p>
                ) : null}

              </div>

              <div className="flex gap-2 text-xs shrink-0">

                <button type="button" className="text-blue-700" onClick={() => startEdit(o)}>Edit</button>

                <button type="button" className="text-red-600" onClick={() => void remove(String(o.order_id))}>Delete</button>

              </div>

            </div>

          </li>

        ))}

      </ul>

      {editId && (

        <section className="border rounded-xl p-4 bg-slate-50 space-y-2 text-sm">

          <h3 className="font-semibold m-0">Edit order</h3>

          <select className="border rounded-lg px-2 py-1.5 w-full" value={editFields.order_type} onChange={(e) => setEditFields({ ...editFields, order_type: e.target.value })}>

            {ORDER_TYPES.map((t) => (

              <option key={t} value={t}>{t}</option>

            ))}

          </select>

          <input className="border rounded-lg px-2 py-1.5 w-full" placeholder="Title" value={editFields.title} onChange={(e) => setEditFields({ ...editFields, title: e.target.value })} />

          <input type="date" className="border rounded-lg px-2 py-1.5 w-full" value={editFields.order_date?.slice(0, 10)} onChange={(e) => setEditFields({ ...editFields, order_date: e.target.value })} />

          <input className="border rounded-lg px-2 py-1.5 w-full" placeholder="Judge" value={editFields.judge} onChange={(e) => setEditFields({ ...editFields, judge: e.target.value })} />

          <textarea className="border rounded-lg px-2 py-1.5 w-full" rows={3} placeholder="Summary" value={editFields.summary} onChange={(e) => setEditFields({ ...editFields, summary: e.target.value })} />

          <div className="flex gap-2">

            <button type="button" className="px-3 py-1.5 bg-navy text-white rounded-lg" onClick={() => void saveEdit()}>Save</button>

            <button type="button" className="px-3 py-1.5 border rounded-lg" onClick={() => setEditId("")}>Cancel</button>

          </div>

        </section>

      )}

    </div>

  );

}


