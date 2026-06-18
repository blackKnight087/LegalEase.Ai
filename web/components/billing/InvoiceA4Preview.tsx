"use client";

import InvoiceBrandHeader from "@/components/billing/InvoiceBrandHeader";
import { FIRM_DISPLAY_NAME } from "@/lib/brand";

type ServiceLine = { date?: string; description?: string; hours?: number; rate?: number; amount?: number };
type ExpenseLine = { description?: string; amount?: number };

type Props = {
  firmName: string;
  client: Record<string, string>;
  matter: Record<string, string>;
  billing: Record<string, string>;
  services: ServiceLine[];
  expenses: ExpenseLine[];
  totals: Record<string, number>;
  taxes: Record<string, unknown>;
  payment: Record<string, string>;
  notes?: string;
};

export default function InvoiceA4Preview({
  firmName,
  client,
  matter,
  billing,
  services,
  expenses,
  totals,
  taxes,
  payment,
  notes,
}: Props) {
  const displayFirm =
    !firmName || firmName.toLowerCase().replace(/\s/g, "") === "legaleasechambers"
      ? FIRM_DISPLAY_NAME
      : firmName;

  return (
    <div
      className="mx-auto bg-white text-slate-900 shadow-lg border border-slate-300 print:shadow-none overflow-hidden"
      style={{ width: "210mm", minHeight: "297mm", fontFamily: "Georgia, 'Times New Roman', serif" }}
    >
      <InvoiceBrandHeader
        invoiceNumber={billing.invoice_number}
        invoiceDate={billing.invoice_date}
        dueDate={billing.due_date}
      />
      <div className="px-[16mm] pt-6 pb-[18mm]">

      <div className="grid grid-cols-2 gap-6 mb-6 text-sm">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-1">Bill to</p>
          <p className="font-semibold">{client.name}</p>
          {client.company && <p>{client.company}</p>}
          {client.address && <p className="text-slate-600">{client.address}</p>}
          {client.email && <p className="text-slate-600">{client.email}</p>}
          {client.gst && <p className="text-slate-600">GSTIN: {client.gst}</p>}
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-1">Matter</p>
          <p className="font-semibold">{matter.matter_name}</p>
          <p className="text-slate-600">Ref: {matter.matter_number || matter.case_number}</p>
          {matter.court && <p className="text-slate-600">{matter.court}</p>}
        </div>
      </div>

      {notes && (
        <p className="text-xs text-slate-700 mb-4 leading-relaxed border-l-2 border-emerald-600 pl-3">{notes}</p>
      )}

      <table className="w-full text-xs mb-4 border-collapse">
        <thead>
          <tr className="bg-slate-100 border-y border-slate-300">
            <th className="text-left py-2 px-1">Date</th>
            <th className="text-left py-2 px-1">Professional services</th>
            <th className="text-right py-2 px-1">Hrs</th>
            <th className="text-right py-2 px-1">Rate</th>
            <th className="text-right py-2 px-1">Amount</th>
          </tr>
        </thead>
        <tbody>
          {services.map((s, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-1.5 px-1">{s.date}</td>
              <td className="py-1.5 px-1">{s.description}</td>
              <td className="py-1.5 px-1 text-right">{s.hours}</td>
              <td className="py-1.5 px-1 text-right">₹{Number(s.rate || 0).toLocaleString("en-IN")}</td>
              <td className="py-1.5 px-1 text-right">₹{Number(s.amount || 0).toLocaleString("en-IN")}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {expenses.length > 0 && (
        <>
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-1">Disbursements</p>
          <table className="w-full text-xs mb-4">
            <tbody>
              {expenses.map((e, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1">{e.description}</td>
                  <td className="py-1 text-right">₹{Number(e.amount || 0).toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="flex justify-end mb-8">
        <div className="w-56 text-sm space-y-1">
          <div className="flex justify-between"><span>Subtotal</span><span>₹{totals.subtotal?.toLocaleString("en-IN")}</span></div>
          {!taxes.tax_exempt && (
            <>
              {Number(totals.cgst) > 0 && <div className="flex justify-between"><span>CGST</span><span>₹{totals.cgst?.toLocaleString("en-IN")}</span></div>}
              {Number(totals.sgst) > 0 && <div className="flex justify-between"><span>SGST</span><span>₹{totals.sgst?.toLocaleString("en-IN")}</span></div>}
              {Number(totals.igst) > 0 && <div className="flex justify-between"><span>IGST</span><span>₹{totals.igst?.toLocaleString("en-IN")}</span></div>}
            </>
          )}
          {Number(totals.retainer_applied) > 0 && (
            <div className="flex justify-between text-emerald-800"><span>Retainer applied</span><span>-₹{totals.retainer_applied?.toLocaleString("en-IN")}</span></div>
          )}
          <div className="flex justify-between font-bold text-base border-t border-navy pt-2 text-navy">
            <span>Balance due</span><span>₹{totals.balance_due?.toLocaleString("en-IN")}</span>
          </div>
        </div>
      </div>

      <div className="text-xs border-t border-slate-200 pt-4 space-y-2">
        <p className="font-semibold text-navy">Payment instructions</p>
        {payment.bank && <p>Bank: {payment.bank} · A/C: {payment.account_number} · IFSC: {payment.ifsc}</p>}
        {payment.upi && <p>UPI: {payment.upi}</p>}
        {payment.razorpay_link && <p>Razorpay: {payment.razorpay_link}</p>}
        {payment.stripe_link && <p>Stripe: {payment.stripe_link}</p>}
        {payment.payment_link && <p>Pay online: {payment.payment_link}</p>}
      </div>

      <div className="mt-12 grid grid-cols-2 gap-8 text-xs">
        <div>
          <p className="border-t border-slate-400 pt-2 mt-16">Authorised signatory — {displayFirm}</p>
        </div>
        <div className="text-slate-500">
          <p className="font-semibold text-slate-700 mb-1">Terms</p>
          <p>Payment due within 30 days. Late payments may attract interest at 18% p.a. All amounts in INR unless stated.</p>
        </div>
      </div>
      </div>
    </div>
  );
}
