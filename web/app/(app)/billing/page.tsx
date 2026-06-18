"use client";

import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import InvoiceWizard from "@/components/billing/InvoiceWizard";
import ClientBillingProfile from "@/components/billing/ClientBillingProfile";
import CollectionsBar from "@/components/billing/CollectionsBar";
import TimeEntriesTable from "@/components/billing/TimeEntriesTable";
import ExpensesPanel from "@/components/billing/ExpensesPanel";
import InvoiceHistoryTable from "@/components/billing/InvoiceHistoryTable";
import TrustLedgerPanel from "@/components/billing/TrustLedgerPanel";
import BillingAIAssistant from "@/components/billing/BillingAIAssistant";
import BillingReportsPanel from "@/components/billing/BillingReportsPanel";
import MatterFinancialDashboard from "@/components/billing/MatterFinancialDashboard";
import * as api from "@/lib/api";

const TABS = ["Overview", "Time", "Expenses", "Invoices", "Trust", "Reports"] as const;

export default function BillingPage() {
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [workspace, setWorkspace] = useState<api.BillingWorkspaceData | null>(null);
  const [trust, setTrust] = useState<Record<string, unknown> | null>(null);
  const [trustTxns, setTrustTxns] = useState<Array<Record<string, unknown>>>([]);
  const [raw, setRaw] = useState("Reviewed bail provisions under Section 437 for 2 hours");
  const [units, setUnits] = useState("2");
  const [rate, setRate] = useState("5000");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [polishDictation, setPolishDictation] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const m = await api.listMatters();
      const list = m.matters || [];
      setMatters(list);
      const mid = matterId || list[0]?.matter_id || "";
      if (mid && !matterId) setMatterId(mid);

      if (mid) {
        const ws = await api.fetchBillingWorkspace(mid);
        setWorkspace(ws);
        try {
          setTrust(await api.getTrustAccount(mid));
          const tx = await api.listTrustTransactions(mid);
          setTrustTxns(tx.transactions || []);
        } catch {
          setTrust(null);
          setTrustTxns([]);
        }
      } else {
        const summary = await api.billingSummary();
        setWorkspace({
          summary,
          profile: {} as api.MatterBillingProfile,
          entries: [],
          expenses: [],
          invoices: [],
          matter_financials: {},
          expense_types: [],
        });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Load failed";
      if (msg.toLowerCase().includes("method not allowed") || msg.includes("405")) {
        setErr("Billing API unavailable — try again in a moment or contact support.");
      } else {
        setErr(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  const downloadPdf = async (invoiceId: string, invoiceNumber?: string) => {
    setBusy(true);
    try {
      const blob = await api.downloadInvoicePdf(invoiceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoice-${invoiceNumber || invoiceId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "PDF download failed");
    } finally {
      setBusy(false);
    }
  };

  const logEntry = async () => {
    if (!matterId) return;
    setBusy(true);
    try {
      await api.logBillingEntry({
        matter_id: matterId,
        raw_activity: raw,
        units_logged: parseFloat(units) || 1,
        rate_per_unit: parseFloat(rate) || 1000,
      });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const onPolish = async (text: string, hrs: number) => {
    const r = await api.previewBillingNarrative({
      raw_activity: text,
      units_logged: hrs,
      matter_id: matterId,
    });
    return r.narrative;
  };

  const trustDeposit = async (amount: number, narrative: string, txn_type: "DEPOSIT" | "TRANSFER_TO_OPERATING") => {
    setBusy(true);
    try {
      await api.postTrustTransaction({
        matter_id: matterId,
        ledger_type: "TRUST",
        txn_type,
        amount,
        narrative,
      });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Trust failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Practice billing & trust"
        subtitle="Legal finance workspace — time, expenses, invoices, trust, and collections"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-6xl mx-auto w-full space-y-4 sm:space-y-5 pb-8">
        {err && (
          <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">{err}</p>
        )}

        <div className="flex flex-wrap gap-3 items-center">
          <select
            className="flex-1 min-w-[12rem] border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white shadow-sm"
            value={matterId}
            onChange={(e) => setMatterId(e.target.value)}
            disabled={!matters.length}
          >
            {matters.map((m) => (
              <option key={m.matter_id} value={m.matter_id}>
                {m.matter_name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !matterId}
            onClick={() => setWizardOpen(true)}
            className="px-5 py-2 bg-emerald-700 text-white rounded-lg text-sm font-semibold shadow-sm"
          >
            Generate invoice
          </button>
        </div>

        <CollectionsBar summary={workspace?.summary ?? null} />

        <nav className="flex flex-wrap gap-1 border-b border-slate-200 pb-0">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 -mb-px ${
                tab === t
                  ? "bg-white border-slate-200 text-navy"
                  : "border-transparent text-slate-500 hover:text-navy"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === "Overview" && (
          <div className="space-y-4">
            <ClientBillingProfile profile={workspace?.profile ?? null} loading={loading} />
            <MatterFinancialDashboard financials={workspace?.matter_financials ?? null} />
            <section className="border border-slate-200 rounded-xl bg-white p-4 space-y-3 shadow-sm">
              <h2 className="text-sm font-semibold text-navy">Quick time entry</h2>
              <label className="flex items-center gap-2 text-xs text-slate-600">
                <input type="checkbox" checked={polishDictation} onChange={(e) => setPolishDictation(e.target.checked)} />
                Legal polish after voice dictation
              </label>
              <VoiceTextarea className="min-h-[4rem] text-sm" rows={3} value={raw} onChange={setRaw} polishOnStop={polishDictation} />
              <div className="flex gap-2">
                <input type="number" className="border rounded-lg px-3 py-2 text-sm w-24" value={units} onChange={(e) => setUnits(e.target.value)} placeholder="Hours" />
                <input type="number" className="border rounded-lg px-3 py-2 text-sm w-32" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="Rate/hr" />
                <button type="button" disabled={busy} onClick={logEntry} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">
                  Log time
                </button>
              </div>
            </section>
            <BillingAIAssistant matterId={matterId} onApply={(t) => setRaw(t)} />
          </div>
        )}

        {tab === "Time" && (
          <TimeEntriesTable
            entries={workspace?.entries ?? []}
            matterId={matterId}
            busy={busy}
            onRefresh={load}
            onPolish={onPolish}
          />
        )}

        {tab === "Expenses" && (
          <ExpensesPanel
            expenses={workspace?.expenses ?? []}
            expenseTypes={workspace?.expense_types ?? []}
            matterId={matterId}
            busy={busy}
            onRefresh={load}
          />
        )}

        {tab === "Invoices" && (
          <InvoiceHistoryTable
            invoices={workspace?.invoices ?? []}
            busy={busy}
            onDownload={downloadPdf}
            onRefresh={load}
            onDuplicate={() => setWizardOpen(true)}
          />
        )}

        {tab === "Trust" && (
          <TrustLedgerPanel
            trust={trust}
            transactions={trustTxns}
            matterId={matterId}
            busy={busy}
            onDeposit={trustDeposit}
          />
        )}

        {tab === "Reports" && <BillingReportsPanel />}
      </div>

      <InvoiceWizard open={wizardOpen} matterId={matterId} onClose={() => setWizardOpen(false)} onSaved={load} />
    </div>
  );
}
