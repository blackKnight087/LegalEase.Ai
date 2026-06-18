"use client";

import type { InvoiceRecord } from "@/lib/api";
import { statusBadgeClass } from "@/components/billing/InvoiceWizard";
import * as api from "@/lib/api";

type Props = {
  invoices: InvoiceRecord[];
  busy: boolean;
  onDownload: (id: string, num?: string) => void;
  onRefresh: () => void;
  onDuplicate?: (inv: InvoiceRecord) => void;
  onView?: (inv: InvoiceRecord) => void;
};

export default function InvoiceHistoryTable({
  invoices,
  busy,
  onDownload,
  onRefresh,
  onDuplicate,
  onView,
}: Props) {
  const markPaid = async (id: string) => {
    await api.patchInvoiceStatus(id, "PAID");
    onRefresh();
  };

  const email = (inv: InvoiceRecord) => {
    const payload = inv.payload as Record<string, unknown> | undefined;
    const client = (payload?.client as Record<string, string>) || {};
    const emailTo = client.email || "";
    const subject = encodeURIComponent(`Invoice ${inv.invoice_number || inv.invoice_id}`);
    const body = encodeURIComponent(
      `Please find attached invoice ${inv.invoice_number || ""} for ₹${inv.balance_due ?? inv.total}.`
    );
    window.location.href = `mailto:${emailTo}?subject=${subject}&body=${body}`;
  };

  return (
    <section className="border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-navy">Invoice history</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 text-slate-600 text-left">
              <th className="p-2">Invoice #</th>
              <th className="p-2">Client</th>
              <th className="p-2 text-right">Amount</th>
              <th className="p-2">Status</th>
              <th className="p-2">Issued</th>
              <th className="p-2">Due</th>
              <th className="p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 && (
              <tr><td colSpan={7} className="p-6 text-center text-slate-500">No invoices yet.</td></tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.invoice_id} className="border-t border-slate-100">
                <td className="p-2 font-medium text-navy">{inv.invoice_number || inv.invoice_id.slice(0, 8)}</td>
                <td className="p-2">{inv.client_name}</td>
                <td className="p-2 text-right">₹{(inv.balance_due ?? inv.total)?.toLocaleString("en-IN")}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${statusBadgeClass(inv.status)}`}>
                    {inv.status}
                  </span>
                </td>
                <td className="p-2">{inv.invoice_date || "—"}</td>
                <td className="p-2">{inv.due_date || "—"}</td>
                <td className="p-2 whitespace-nowrap space-x-2">
                  {onView && (
                    <button type="button" className="text-navy font-medium" onClick={() => onView(inv)}>View</button>
                  )}
                  <button type="button" disabled={busy} className="text-emerald-700 font-medium" onClick={() => onDownload(inv.invoice_id, inv.invoice_number)}>PDF</button>
                  <button type="button" className="text-slate-600" onClick={() => email(inv)}>Email</button>
                  {onDuplicate && (
                    <button type="button" className="text-slate-600" onClick={() => onDuplicate(inv)}>Duplicate</button>
                  )}
                  {inv.status !== "PAID" && (
                    <button type="button" className="text-emerald-800" onClick={() => markPaid(inv.invoice_id)}>Paid</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
