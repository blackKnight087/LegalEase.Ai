"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import UsageLimitsCard from "@/components/saas/UsageLimitsCard";
import SubscriptionPlans, { type BillingPlan } from "@/components/billing/SubscriptionPlans";
import { useAuth } from "@/components/providers/AuthProvider";
import * as api from "@/lib/api";

function SubscriptionPageInner() {
  const { user, refreshUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const checkout = searchParams.get("checkout");

  const [payments, setPayments] = useState<
    Array<{ plan: string; amount: number; status: string; date?: string }>
  >([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [stripeEnabled, setStripeEnabled] = useState(false);
  const [mockBilling, setMockBilling] = useState(true);
  const [docCount, setDocCount] = useState(0);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [payRes, statusRes, docsRes] = await Promise.all([
        api.fetchBillingPayments(),
        api.fetchSubscriptionStatus(),
        api.fetchDocuments().catch(() => ({ documents: [] })),
      ]);
      setPayments(payRes.payments || []);
      setPlans((statusRes.plans as BillingPlan[]) || []);
      setStripeEnabled(Boolean(statusRes.stripe_enabled));
      setMockBilling(Boolean(statusRes.mock_billing));
      setDocCount((docsRes.documents || []).length);
    } catch {
      setPayments([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (checkout === "success") {
      void refreshUser().then(() => {
        setMsg("Payment successful — your plan is now active.");
        void load();
        router.replace("/settings/subscription");
      });
    } else if (checkout === "cancel") {
      setMsg("Checkout cancelled. No charge was made.");
      router.replace("/settings/subscription");
    }
  }, [checkout, refreshUser, load, router]);

  const upgrade = async (plan: string) => {
    setBusy(true);
    setMsg("");
    try {
      const result = await api.upgradePlan(plan);
      if (result.success) {
        await refreshUser();
        setMsg(
          stripeEnabled
            ? `Redirecting to secure checkout for ${plan}…`
            : `Plan updated to ${result.membership || plan}.`
        );
        await load();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Upgrade failed");
    } finally {
      setBusy(false);
    }
  };

  const openPortal = async () => {
    setBusy(true);
    setMsg("");
    try {
      await api.openBillingPortal();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Billing portal unavailable");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Subscription & billing"
        subtitle="Secure payments via Stripe — upgrade your LegalEase workspace"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-5xl mx-auto w-full space-y-6 pb-8">
        <p className="text-sm text-slate-600">
          For client invoices and trust accounts, use{" "}
          <Link href="/billing" className="text-blue-700 font-medium hover:underline">
            Practice billing
          </Link>
          .
        </p>

        {msg && (
          <p
            className={`text-sm rounded-xl px-4 py-3 border ${
              msg.includes("successful") || msg.includes("updated")
                ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                : "bg-slate-50 border-slate-200 text-slate-700"
            }`}
          >
            {msg}
          </p>
        )}

        {!stripeEnabled && mockBilling && (
          <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Stripe is not configured — upgrades apply instantly in dev mode. Add{" "}
            <code className="text-[11px]">STRIPE_SECRET_KEY</code> and price IDs in{" "}
            <code className="text-[11px]">.env</code> for live payments.
          </p>
        )}

        <UsageLimitsCard documentCount={docCount} />

        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-900 m-0">Choose a plan</h2>
            <span className="text-xs font-medium text-slate-500">
              Signed in as {user?.username} · {user?.membership}
            </span>
          </div>
          {plans.length > 0 ? (
            <SubscriptionPlans
              plans={plans}
              stripeEnabled={stripeEnabled}
              mockBilling={mockBilling}
              busy={busy}
              onUpgrade={(id) => void upgrade(id)}
            />
          ) : (
            <p className="text-sm text-slate-500">Loading plans…</p>
          )}
        </section>

        {(user?.membership === "Pro" || user?.membership === "Legal Pro") && stripeEnabled && (
          <section className="bg-white rounded-2xl border border-slate-200 p-6">
            <h2 className="font-semibold text-slate-900 mb-2 m-0">Manage subscription</h2>
            <p className="text-sm text-slate-600 mb-4 m-0">
              Update payment method, download invoices, or cancel via the Stripe customer portal.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void openPortal()}
              className="px-4 py-2.5 border border-slate-300 rounded-xl text-sm font-semibold hover:bg-slate-50 disabled:opacity-50"
            >
              Open billing portal
            </button>
          </section>
        )}

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-900 mb-3 m-0">Payment history</h2>
          {payments.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-100">
                    <th className="pb-2 font-medium">Plan</th>
                    <th className="pb-2 font-medium">Amount</th>
                    <th className="pb-2 font-medium">Status</th>
                    <th className="pb-2 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((p, i) => (
                    <tr key={i} className="border-t border-slate-50">
                      <td className="py-2.5">{p.plan}</td>
                      <td className="py-2.5">₹{p.amount?.toLocaleString("en-IN")}</td>
                      <td className="py-2.5 capitalize">{p.status}</td>
                      <td className="py-2.5 text-slate-500">
                        {p.date ? new Date(p.date).toLocaleDateString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-400 m-0">No payments yet</p>
          )}
        </section>
      </div>
    </div>
  );
}

export default function SubscriptionPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 text-sm text-slate-500">Loading subscription…</div>
      }
    >
      <SubscriptionPageInner />
    </Suspense>
  );
}
