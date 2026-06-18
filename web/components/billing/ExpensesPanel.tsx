"use client";

import { useState } from "react";
import * as api from "@/lib/api";

type Props = {
  expenses: Array<Record<string, unknown>>;
  expenseTypes: string[];
  matterId: string;
  busy: boolean;
  onRefresh: () => void;
};

export default function ExpensesPanel({ expenses, expenseTypes, matterId, busy, onRefresh }: Props) {
  const [type, setType] = useState("Miscellaneous");
  const [desc, setDesc] = useState("");
  const [amt, setAmt] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [billable, setBillable] = useState(true);

  const add = async () => {
    if (!matterId || !desc.trim()) return;
    await api.createBillingExpense({
      matter_id: matterId,
      expense_date: date,
      expense_type: type,
      description: desc,
      amount: parseFloat(amt) || 0,
      billable,
    });
    setDesc("");
    setAmt("");
    onRefresh();
  };

  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-navy">Expenses</h2>
      </div>
      <div className="p-4 grid sm:grid-cols-2 lg:grid-cols-6 gap-2 text-sm border-b border-slate-100 bg-slate-50/50">
        <input type="date" className="border rounded-lg px-2 py-1.5" value={date} onChange={(e) => setDate(e.target.value)} />
        <select className="border rounded-lg px-2 py-1.5" value={type} onChange={(e) => setType(e.target.value)}>
          {expenseTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input className="border rounded-lg px-2 py-1.5 lg:col-span-2" placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <input type="number" className="border rounded-lg px-2 py-1.5" placeholder="Amount" value={amt} onChange={(e) => setAmt(e.target.value)} />
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} />
          Billable
        </label>
        <button type="button" disabled={busy} onClick={add} className="px-3 py-1.5 bg-emerald-700 text-white rounded-lg text-sm font-medium">
          Add expense
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 text-slate-600 text-left">
              <th className="p-2">Date</th>
              <th className="p-2">Type</th>
              <th className="p-2">Description</th>
              <th className="p-2 text-right">Amount</th>
              <th className="p-2">Billable</th>
              <th className="p-2" />
            </tr>
          </thead>
          <tbody>
            {expenses.length === 0 && (
              <tr><td colSpan={6} className="p-4 text-center text-slate-500">No expenses recorded.</td></tr>
            )}
            {expenses.map((ex) => (
              <tr key={String(ex.expense_id)} className="border-t border-slate-100">
                <td className="p-2">{String(ex.date || "")}</td>
                <td className="p-2">{String(ex.expense_type || "")}</td>
                <td className="p-2">{String(ex.description || "")}</td>
                <td className="p-2 text-right">₹{Number(ex.amount || 0).toLocaleString("en-IN")}</td>
                <td className="p-2">{ex.billable ? "Yes" : "No"}</td>
                <td className="p-2">
                  <button
                    type="button"
                    className="text-red-600"
                    onClick={async () => {
                      await api.deleteBillingExpense(String(ex.expense_id));
                      onRefresh();
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
