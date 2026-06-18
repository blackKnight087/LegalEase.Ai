"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import InvoiceA4Preview from "@/components/billing/InvoiceA4Preview";
import { FIRM_DISPLAY_NAME } from "@/lib/brand";
import * as api from "@/lib/api";

const STEPS = [
  "Client",
  "Matter",
  "Billing",
  "Services",
  "Expenses",
  "Taxes",
  "Retainer",
  "Payment",
  "Notes",
  "Review",
] as const;

const BILLING_TYPES = ["Hourly", "Fixed", "Retainer", "Expense", "Mixed"] as const;

type ServiceLine = {
  record_id?: string;
  date: string;
  description: string;
  hours: number;
  rate: number;
  amount: number;
};

type ExpenseLine = {
  description: string;
  amount: number;
  taxable: boolean;
};

type Props = {
  open: boolean;
  matterId: string;
  onClose: () => void;
  onSaved?: () => void;
};

function emptyPayload(): Record<string, unknown> {
  const today = new Date().toISOString().slice(0, 10);
  const due = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
  return {
    client: { name: "", email: "", phone: "", address: "", gst: "", company: "" },
    matter: {
      matter_id: "",
      matter_name: "",
      matter_number: "",
      case_number: "",
      court: "",
      matter_type: "",
      lead_lawyer: "",
      assigned_lawyers: [] as string[],
      practice_area: "",
    },
    billing: {
      invoice_number: "",
      invoice_date: today,
      due_date: due,
      currency: "INR",
      billing_type: "Hourly",
    },
    services: [] as ServiceLine[],
    expenses: [] as ExpenseLine[],
    taxes: { gst_percent: 18, cgst: 0, sgst: 0, igst: 0, tax_exempt: false, intra_state: true },
    retainer: { current_retainer: 0, apply_amount: 0, remaining: 0, outstanding: 0 },
    payment: {
      firm_name: FIRM_DISPLAY_NAME,
      bank: "",
      account_holder: "",
      account_number: "",
      ifsc: "",
      upi: "",
      payment_link: "",
      razorpay_link: "",
      stripe_link: "",
    },
    notes: "",
    record_ids: [] as string[],
    totals: {},
  };
}

function recalcServices(services: ServiceLine[]): ServiceLine[] {
  return services.map((s) => ({
    ...s,
    amount: Math.round((Number(s.hours) || 0) * (Number(s.rate) || 0) * 100) / 100,
  }));
}

function computeLocalTotals(payload: Record<string, unknown>) {
  const services = (payload.services as ServiceLine[]) || [];
  const expenses = (payload.expenses as ExpenseLine[]) || [];
  const taxes = (payload.taxes as Record<string, unknown>) || {};
  const retainer = (payload.retainer as Record<string, number>) || {};

  const servicesSub = services.reduce((a, s) => a + (Number(s.amount) || 0), 0);
  const expSub = expenses.reduce((a, e) => a + (Number(e.amount) || 0), 0);
  const subtotal = Math.round((servicesSub + expSub) * 100) / 100;

  const taxExempt = Boolean(taxes.tax_exempt);
  const gstPct = Number(taxes.gst_percent) || 18;
  const intra = taxes.intra_state !== false;

  let taxable = servicesSub;
  if (!taxExempt) {
    taxable += expenses.filter((e) => e.taxable !== false).reduce((a, e) => a + (Number(e.amount) || 0), 0);
  }
  taxable = Math.round(taxable * 100) / 100;

  let cgst = 0,
    sgst = 0,
    igst = 0,
    taxAmount = 0;
  if (!taxExempt && taxable > 0) {
    taxAmount = Math.round(taxable * gstPct) / 100;
    if (intra) {
      cgst = Math.round(taxAmount * 50) / 100;
      sgst = Math.round((taxAmount - cgst) * 100) / 100;
    } else {
      igst = taxAmount;
    }
  }
  const grand = Math.round((subtotal + taxAmount) * 100) / 100;
  const apply = Math.min(
    Number(retainer.apply_amount) || 0,
    Number(retainer.current_retainer) || 0,
    grand
  );
  const balance = Math.round((grand - apply) * 100) / 100;
  const remaining = Math.round(((Number(retainer.current_retainer) || 0) - apply) * 100) / 100;

  return {
    services_subtotal: Math.round(servicesSub * 100) / 100,
    expenses_subtotal: Math.round(expSub * 100) / 100,
    subtotal,
    taxable_amount: taxable,
    gst_percent: gstPct,
    cgst,
    sgst,
    igst,
    tax_amount: taxAmount,
    grand_total: grand,
    retainer_applied: apply,
    remaining_retainer: remaining,
    balance_due: balance,
  };
}

function statusBadgeClass(status: string) {
  const s = status.toUpperCase();
  if (s === "PAID") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (s === "DRAFT") return "bg-slate-100 text-slate-700 border-slate-200";
  if (s === "OVERDUE") return "bg-red-100 text-red-800 border-red-200";
  if (s === "GENERATED" || s === "ISSUED") return "bg-blue-100 text-blue-800 border-blue-200";
  return "bg-amber-100 text-amber-800 border-amber-200";
}

export default function InvoiceWizard({ open, matterId, onClose, onSaved }: Props) {
  const [step, setStep] = useState(0);
  const [payload, setPayload] = useState<Record<string, unknown>>(emptyPayload());
  const [invoiceId, setInvoiceId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const totals = useMemo(() => computeLocalTotals(payload), [payload]);

  const setField = useCallback((section: string, field: string, value: unknown) => {
    setPayload((prev) => ({
      ...prev,
      [section]: { ...(prev[section] as Record<string, unknown>), [field]: value },
    }));
  }, []);

  const loadPrefill = useCallback(async () => {
    if (!matterId) return;
    setLoading(true);
    setErr("");
    try {
      const r = await api.prefillInvoice(matterId);
      setPayload({ ...emptyPayload(), ...r.payload, totals: r.payload.totals || {} });
      setInvoiceId(undefined);
      setStep(0);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load invoice data");
    } finally {
      setLoading(false);
    }
  }, [matterId]);

  useEffect(() => {
    if (open && matterId) loadPrefill();
  }, [open, matterId, loadPrefill]);

  const validateStep = (): string | null => {
    const client = payload.client as Record<string, string>;
    const matter = payload.matter as Record<string, string>;
    const billing = payload.billing as Record<string, string>;
    if (step === 0 && !client?.name?.trim()) return "Client name is required";
    if (step === 1 && !matter?.matter_name?.trim()) return "Matter name is required";
    if (step === 2) {
      if (!billing?.invoice_date) return "Invoice date is required";
      if (!billing?.due_date) return "Due date is required";
    }
    if (step === 3) {
      const svcs = (payload.services as ServiceLine[]) || [];
      if (!svcs.length) return "Add at least one service line";
    }
    return null;
  };

  const next = () => {
    const v = validateStep();
    if (v) {
      setErr(v);
      return;
    }
    setErr("");
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const prev = () => {
    setErr("");
    setStep((s) => Math.max(s - 1, 0));
  };

  const saveDraft = async () => {
    setBusy(true);
    setErr("");
    try {
      const body = { payload: { ...payload, totals }, invoice_id: invoiceId, status: "DRAFT" };
      const saved = invoiceId
        ? await api.updateInvoice(invoiceId, body)
        : await api.saveInvoiceDraft(body);
      setInvoiceId(saved.invoice_id);
      onSaved?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const finalizeAndPdf = async () => {
    setBusy(true);
    setErr("");
    try {
      let id = invoiceId;
      if (!id) {
        const saved = await api.saveInvoiceDraft({ payload: { ...payload, totals }, status: "DRAFT" });
        id = saved.invoice_id;
        setInvoiceId(id);
      } else {
        await api.updateInvoice(id, { payload: { ...payload, totals }, status: "DRAFT" });
      }
      await api.finalizeInvoice(id!);
      const blob = await api.downloadInvoicePdf(id!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoice-${(payload.billing as Record<string, string>)?.invoice_number || id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      onSaved?.();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Finalize failed");
    } finally {
      setBusy(false);
    }
  };

  const emailClient = () => {
    const client = payload.client as Record<string, string>;
    const billing = payload.billing as Record<string, string>;
    const subject = encodeURIComponent(`Invoice ${billing?.invoice_number || ""} — Legal Services`);
    const body = encodeURIComponent(
      `Dear ${client?.name || "Client"},\n\nPlease find attached invoice ${billing?.invoice_number || ""} for legal services rendered.\n\nBalance due: Rs. ${totals.balance_due?.toLocaleString("en-IN")}\nDue date: ${billing?.due_date || ""}\n\nRegards`
    );
    window.location.href = `mailto:${client?.email || ""}?subject=${subject}&body=${body}`;
  };

  if (!open) return null;

  const client = (payload.client || {}) as Record<string, string>;
  const matter = (payload.matter || {}) as Record<string, string | string[]>;
  const billing = (payload.billing || {}) as Record<string, string>;
  const services = ((payload.services as ServiceLine[]) || []).slice();
  const expenses = ((payload.expenses as ExpenseLine[]) || []).slice();
  const taxes = (payload.taxes || {}) as Record<string, unknown>;
  const retainer = (payload.retainer || {}) as Record<string, number>;
  const payment = (payload.payment || {}) as Record<string, string>;

  const inputCls = "mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm";
  const labelCls = "block text-xs font-semibold text-slate-500 uppercase tracking-wide";

  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-navy/50 backdrop-blur-[2px]" onClick={busy ? undefined : onClose} aria-hidden />
      <div className="relative bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-slate-200 w-full max-w-3xl max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="px-5 pt-5 pb-3 border-b border-slate-100 shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-navy">Create invoice</h2>
              <p className="text-xs text-slate-500 mt-0.5">Professional GST invoice wizard</p>
            </div>
            <button type="button" onClick={onClose} disabled={busy} className="text-slate-400 hover:text-slate-600 text-xl leading-none px-1">
              ×
            </button>
          </div>
          {/* Step indicator */}
          <div className="flex gap-1 mt-4 overflow-x-auto pb-1 le-scroll">
            {STEPS.map((name, i) => (
              <button
                key={name}
                type="button"
                onClick={() => i < step && setStep(i)}
                className={`shrink-0 text-[10px] font-semibold px-2 py-1 rounded-full border transition-colors ${
                  i === step
                    ? "bg-navy text-white border-navy"
                    : i < step
                      ? "bg-emerald-50 text-emerald-800 border-emerald-200 cursor-pointer"
                      : "bg-slate-50 text-slate-400 border-slate-200"
                }`}
              >
                {i + 1}. {name}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 le-scroll">
          {loading && <p className="text-sm text-slate-500">Loading matter data…</p>}
          {err && (
            <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">{err}</p>
          )}

          {/* Step 1: Client */}
          {step === 0 && (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className={labelCls}>
                Client name *
                <input className={inputCls} value={client.name || ""} onChange={(e) => setField("client", "name", e.target.value)} />
              </label>
              <label className={labelCls}>
                Email
                <input type="email" className={inputCls} value={client.email || ""} onChange={(e) => setField("client", "email", e.target.value)} />
              </label>
              <label className={labelCls}>
                Phone
                <input className={inputCls} value={client.phone || ""} onChange={(e) => setField("client", "phone", e.target.value)} />
              </label>
              <label className={labelCls}>
                GSTIN (optional)
                <input className={inputCls} value={client.gst || ""} onChange={(e) => setField("client", "gst", e.target.value)} />
              </label>
              <label className={`${labelCls} sm:col-span-2`}>
                Company (optional)
                <input className={inputCls} value={client.company || ""} onChange={(e) => setField("client", "company", e.target.value)} />
              </label>
              <label className={`${labelCls} sm:col-span-2`}>
                Address
                <textarea className={inputCls} rows={2} value={client.address || ""} onChange={(e) => setField("client", "address", e.target.value)} />
              </label>
            </div>
          )}

          {/* Step 2: Matter */}
          {step === 1 && (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className={labelCls}>
                Matter name *
                <input className={inputCls} value={String(matter.matter_name || "")} onChange={(e) => setField("matter", "matter_name", e.target.value)} />
              </label>
              <label className={labelCls}>
                Matter number
                <input className={inputCls} value={String(matter.matter_number || "")} onChange={(e) => setField("matter", "matter_number", e.target.value)} />
              </label>
              <label className={labelCls}>
                Case number
                <input className={inputCls} value={String(matter.case_number || "")} onChange={(e) => setField("matter", "case_number", e.target.value)} />
              </label>
              <label className={labelCls}>
                Court / venue
                <input className={inputCls} value={String(matter.court || "")} onChange={(e) => setField("matter", "court", e.target.value)} />
              </label>
              <label className={labelCls}>
                Matter type
                <input className={inputCls} value={String(matter.matter_type || "")} onChange={(e) => setField("matter", "matter_type", e.target.value)} />
              </label>
              <label className={labelCls}>
                Practice area
                <input className={inputCls} value={String(matter.practice_area || "")} onChange={(e) => setField("matter", "practice_area", e.target.value)} />
              </label>
              <label className={labelCls}>
                Lead lawyer
                <input className={inputCls} value={String(matter.lead_lawyer || "")} onChange={(e) => setField("matter", "lead_lawyer", e.target.value)} />
              </label>
              <label className={labelCls}>
                Assigned lawyers (comma-separated)
                <input
                  className={inputCls}
                  value={Array.isArray(matter.assigned_lawyers) ? matter.assigned_lawyers.join(", ") : ""}
                  onChange={(e) =>
                    setPayload((p) => ({
                      ...p,
                      matter: {
                        ...(p.matter as Record<string, unknown>),
                        assigned_lawyers: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      },
                    }))
                  }
                />
              </label>
            </div>
          )}

          {/* Step 3: Billing */}
          {step === 2 && (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className={labelCls}>
                Invoice number
                <input className={`${inputCls} bg-slate-50`} readOnly value={billing.invoice_number || ""} />
              </label>
              <label className={labelCls}>
                Billing type
                <select className={inputCls} value={billing.billing_type || "Hourly"} onChange={(e) => setField("billing", "billing_type", e.target.value)}>
                  {BILLING_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label className={labelCls}>
                Invoice date *
                <input type="date" className={inputCls} value={billing.invoice_date || ""} onChange={(e) => setField("billing", "invoice_date", e.target.value)} />
              </label>
              <label className={labelCls}>
                Due date *
                <input type="date" className={inputCls} value={billing.due_date || ""} onChange={(e) => setField("billing", "due_date", e.target.value)} />
              </label>
              <label className={labelCls}>
                Currency
                <select className={inputCls} value={billing.currency || "INR"} onChange={(e) => setField("billing", "currency", e.target.value)}>
                  <option value="INR">INR (₹)</option>
                  <option value="USD">USD ($)</option>
                </select>
              </label>
            </div>
          )}

          {/* Step 4: Services */}
          {step === 3 && (
            <div className="space-y-3">
              {services.map((s, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-3 grid sm:grid-cols-6 gap-2 text-sm">
                  <input type="date" className="border rounded px-2 py-1 sm:col-span-1" value={s.date} onChange={(e) => {
                    const next = recalcServices(services.map((x, j) => j === i ? { ...x, date: e.target.value } : x));
                    setPayload((p) => ({ ...p, services: next }));
                  }} />
                  <input className="border rounded px-2 py-1 sm:col-span-2" placeholder="Description" value={s.description} onChange={(e) => {
                    const next = services.map((x, j) => j === i ? { ...x, description: e.target.value } : x);
                    setPayload((p) => ({ ...p, services: next }));
                  }} />
                  <input type="number" step="0.25" className="border rounded px-2 py-1" placeholder="Hrs" value={s.hours} onChange={(e) => {
                    const next = recalcServices(services.map((x, j) => j === i ? { ...x, hours: parseFloat(e.target.value) || 0 } : x));
                    setPayload((p) => ({ ...p, services: next }));
                  }} />
                  <input type="number" className="border rounded px-2 py-1" placeholder="Rate" value={s.rate} onChange={(e) => {
                    const next = recalcServices(services.map((x, j) => j === i ? { ...x, rate: parseFloat(e.target.value) || 0 } : x));
                    setPayload((p) => ({ ...p, services: next }));
                  }} />
                  <div className="flex items-center gap-1">
                    <span className="text-slate-600 shrink-0">₹{s.amount?.toLocaleString("en-IN")}</span>
                    <button type="button" className="text-red-500 text-xs ml-auto" onClick={() => setPayload((p) => ({ ...p, services: services.filter((_, j) => j !== i) }))}>Remove</button>
                  </div>
                </div>
              ))}
              <button type="button" className="text-sm text-emerald-700 font-medium" onClick={() => setPayload((p) => ({
                ...p,
                services: [...services, { date: new Date().toISOString().slice(0, 10), description: "", hours: 1, rate: 5000, amount: 5000 }],
              }))}>
                + Add service line
              </button>
            </div>
          )}

          {/* Step 5: Expenses */}
          {step === 4 && (
            <div className="space-y-3">
              {expenses.map((ex, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-3 grid sm:grid-cols-4 gap-2 text-sm">
                  <input className="border rounded px-2 py-1 sm:col-span-2" placeholder="Description" value={ex.description} onChange={(e) => {
                    setPayload((p) => ({ ...p, expenses: expenses.map((x, j) => j === i ? { ...x, description: e.target.value } : x) }));
                  }} />
                  <input type="number" className="border rounded px-2 py-1" placeholder="Amount" value={ex.amount} onChange={(e) => {
                    setPayload((p) => ({ ...p, expenses: expenses.map((x, j) => j === i ? { ...x, amount: parseFloat(e.target.value) || 0 } : x) }));
                  }} />
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-1 text-xs">
                      <input type="checkbox" checked={ex.taxable !== false} onChange={(e) => {
                        setPayload((p) => ({ ...p, expenses: expenses.map((x, j) => j === i ? { ...x, taxable: e.target.checked } : x) }));
                      }} />
                      Taxable
                    </label>
                    <button type="button" className="text-red-500 text-xs ml-auto" onClick={() => setPayload((p) => ({ ...p, expenses: expenses.filter((_, j) => j !== i) }))}>Remove</button>
                  </div>
                </div>
              ))}
              <button type="button" className="text-sm text-emerald-700 font-medium" onClick={() => setPayload((p) => ({
                ...p,
                expenses: [...expenses, { description: "", amount: 0, taxable: true }],
              }))}>
                + Add expense
              </button>
            </div>
          )}

          {/* Step 6: Taxes */}
          {step === 5 && (
            <div className="space-y-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={Boolean(taxes.tax_exempt)} onChange={(e) => setField("taxes", "tax_exempt", e.target.checked)} />
                Tax exempt
              </label>
              {!taxes.tax_exempt && (
                <>
                  <label className={labelCls}>
                    GST %
                    <input type="number" className={inputCls} value={Number(taxes.gst_percent) || 18} onChange={(e) => setField("taxes", "gst_percent", parseFloat(e.target.value) || 0)} />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={taxes.intra_state !== false} onChange={(e) => setField("taxes", "intra_state", e.target.checked)} />
                    Intra-state (CGST + SGST) — uncheck for IGST
                  </label>
                  <div className="grid grid-cols-3 gap-3 p-3 bg-slate-50 rounded-lg text-sm">
                    <div><b>CGST</b><p>₹{totals.cgst?.toLocaleString("en-IN")}</p></div>
                    <div><b>SGST</b><p>₹{totals.sgst?.toLocaleString("en-IN")}</p></div>
                    <div><b>IGST</b><p>₹{totals.igst?.toLocaleString("en-IN")}</p></div>
                  </div>
                </>
              )}
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm">
                Tax amount: <b>₹{totals.tax_amount?.toLocaleString("en-IN")}</b> · Grand total: <b>₹{totals.grand_total?.toLocaleString("en-IN")}</b>
              </div>
            </div>
          )}

          {/* Step 7: Retainer */}
          {step === 6 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <b>Current retainer</b>
                  <p className="text-lg">₹{Number(retainer.current_retainer || 0).toLocaleString("en-IN")}</p>
                </div>
                <div className="p-3 bg-slate-50 border rounded-lg">
                  <b>Outstanding (after apply)</b>
                  <p className="text-lg">₹{totals.balance_due?.toLocaleString("en-IN")}</p>
                </div>
              </div>
              <label className={labelCls}>
                Apply from retainer
                <input
                  type="number"
                  className={inputCls}
                  value={retainer.apply_amount || 0}
                  max={Math.min(retainer.current_retainer || 0, totals.grand_total || 0)}
                  onChange={(e) => {
                    const apply = parseFloat(e.target.value) || 0;
                    setPayload((p) => ({
                      ...p,
                      retainer: {
                        ...(p.retainer as Record<string, number>),
                        apply_amount: apply,
                        remaining: (Number((p.retainer as Record<string, number>).current_retainer) || 0) - apply,
                      },
                    }));
                  }}
                />
              </label>
              <p className="text-xs text-slate-500">Remaining retainer after apply: ₹{totals.remaining_retainer?.toLocaleString("en-IN")}</p>
            </div>
          )}

          {/* Step 8: Payment */}
          {step === 7 && (
            <div className="grid sm:grid-cols-2 gap-3">
              {(["firm_name", "bank", "account_holder", "account_number", "ifsc", "upi", "payment_link", "razorpay_link", "stripe_link"] as const).map((f) => (
                <label key={f} className={`${labelCls} ${f === "payment_link" ? "sm:col-span-2" : ""}`}>
                  {f.replace(/_/g, " ")}
                  <input className={inputCls} value={payment[f] || ""} onChange={(e) => setField("payment", f, e.target.value)} />
                </label>
              ))}
            </div>
          )}

          {/* Step 9: Notes */}
          {step === 8 && (
            <label className={labelCls}>
              Professional narrative
              <textarea
                className={`${inputCls} min-h-[8rem]`}
                rows={6}
                value={String(payload.notes || "")}
                onChange={(e) => setPayload((p) => ({ ...p, notes: e.target.value }))}
              />
            </label>
          )}

          {/* Step 10: Review */}
          {step === 9 && (
            <div className="overflow-auto max-h-[60vh] bg-slate-100 p-4 rounded-xl print:p-0 print:bg-white">
              <InvoiceA4Preview
                firmName={payment.firm_name || FIRM_DISPLAY_NAME}
                client={client as Record<string, string>}
                matter={matter as Record<string, string>}
                billing={billing as Record<string, string>}
                services={services}
                expenses={expenses}
                totals={totals as Record<string, number>}
                taxes={taxes}
                payment={payment as Record<string, string>}
                notes={String(payload.notes || "")}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-100 flex flex-wrap gap-2 shrink-0">
          {step > 0 && (
            <button type="button" disabled={busy} onClick={prev} className="px-4 py-2 text-sm border border-slate-200 rounded-lg">
              Back
            </button>
          )}
          <div className="flex-1" />
          {step === 9 ? (
            <>
              <button type="button" disabled={busy} onClick={() => setStep(0)} className="px-3 py-2 text-sm border rounded-lg">
                Edit
              </button>
              <button type="button" disabled={busy} onClick={saveDraft} className="px-3 py-2 text-sm border border-emerald-300 text-emerald-800 rounded-lg">
                {busy ? "Saving…" : "Save draft"}
              </button>
              <button type="button" disabled={busy} onClick={finalizeAndPdf} className="px-3 py-2 text-sm bg-emerald-700 text-white rounded-lg">
                Download PDF
              </button>
              <button type="button" disabled={busy} onClick={emailClient} className="px-3 py-2 text-sm bg-navy text-white rounded-lg">
                Email
              </button>
              <button type="button" disabled={busy} onClick={() => window.print()} className="px-3 py-2 text-sm border rounded-lg">
                Print
              </button>
            </>
          ) : (
            <button type="button" disabled={busy || loading} onClick={next} className="px-5 py-2 text-sm bg-navy text-white rounded-lg">
              Continue
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export { statusBadgeClass };
