"use client";

import { useState } from "react";

type Props = {
  trust: Record<string, unknown> | null;
  transactions: Array<Record<string, unknown>>;
  matterId: string;
  busy: boolean;
  onDeposit: (amount: number, narrative: string, type: "DEPOSIT" | "TRANSFER_TO_OPERATING") => void;
};

export default function TrustLedgerPanel({ trust, transactions, matterId, busy, onDeposit }: Props) {
  const [amt, setAmt] = useState("50000");
  const [narr, setNarr] = useState("Client retainer deposit");

  if (!matterId || !trust) return null;

  const trustBal = Number(trust.trust_balance || 0);
  const opBal = Number(trust.operating_balance || 0);

  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-navy">Trust account</h2>
        <p className="text-xs text-slate-500">Segregated client funds — full audit trail</p>
      </div>
      <div className="p-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-xs text-amber-800 font-medium">Trust balance</p>
          <p className="text-xl font-semibold text-navy">₹{trustBal.toLocaleString("en-IN")}</p>
        </div>
        <div className="p-3 bg-slate-50 border rounded-lg">
          <p className="text-xs text-slate-500 font-medium">Operating</p>
          <p className="text-xl font-semibold">₹{opBal.toLocaleString("en-IN")}</p>
        </div>
        <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg sm:col-span-2">
          <p className="text-xs text-emerald-800">Pending replenishment when trust is applied on invoices</p>
        </div>
      </div>
      <div className="px-4 pb-4 flex flex-wrap gap-2">
        <input type="number" className="border rounded-lg px-3 py-2 text-sm w-28" value={amt} onChange={(e) => setAmt(e.target.value)} />
        <input className="flex-1 min-w-[10rem] border rounded-lg px-3 py-2 text-sm" value={narr} onChange={(e) => setNarr(e.target.value)} />
        <button type="button" disabled={busy} onClick={() => onDeposit(parseFloat(amt) || 0, narr, "DEPOSIT")} className="px-3 py-2 bg-amber-700 text-white rounded-lg text-sm">
          Trust deposit
        </button>
        <button type="button" disabled={busy} onClick={() => onDeposit(parseFloat(amt) || 0, narr, "TRANSFER_TO_OPERATING")} className="px-3 py-2 border rounded-lg text-sm">
          To operating
        </button>
      </div>
      <div className="border-t border-slate-100 max-h-48 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 text-slate-600">
              <th className="p-2 text-left">When</th>
              <th className="p-2">Type</th>
              <th className="p-2">Ledger</th>
              <th className="p-2 text-right">Amount</th>
              <th className="p-2 text-left">Narrative</th>
            </tr>
          </thead>
          <tbody>
            {transactions.length === 0 && (
              <tr><td colSpan={5} className="p-4 text-center text-slate-500">No trust movements yet.</td></tr>
            )}
            {transactions.map((t) => (
              <tr key={String(t.txn_id)} className="border-t border-slate-50">
                <td className="p-2">{String(t.created_at || "").slice(0, 16)}</td>
                <td className="p-2">{String(t.txn_type)}</td>
                <td className="p-2">{String(t.ledger_type)}</td>
                <td className="p-2 text-right">₹{Number(t.amount || 0).toLocaleString("en-IN")}</td>
                <td className="p-2 text-slate-600">{String(t.narrative ?? "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
