"use client";

import { useAuth } from "@/components/providers/AuthProvider";

export type BillingPlan = {
  id: string;
  name: string;
  price_inr: number;
  interval: string;
  description: string;
  features: string[];
  stripe_price_id?: string;
};

type Props = {
  plans: BillingPlan[];
  stripeEnabled: boolean;
  mockBilling: boolean;
  busy?: boolean;
  onUpgrade: (planId: string) => void;
};

export default function SubscriptionPlans({
  plans,
  stripeEnabled,
  mockBilling,
  busy,
  onUpgrade,
}: Props) {
  const { user } = useAuth();
  const current = user?.membership || "Free";

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {plans.map((plan) => {
        const isCurrent = plan.id === current;
        const canUpgrade =
          !isCurrent &&
          ((plan.id === "Pro" && current === "Free") ||
            (plan.id === "Legal Pro" && current !== "Legal Pro"));
        const isFree = plan.id === "Free";

        return (
          <article
            key={plan.id}
            className={`rounded-2xl border p-5 flex flex-col ${
              isCurrent
                ? "border-blue-500 bg-blue-50/50 ring-1 ring-blue-500/30"
                : "border-slate-200 bg-white"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-bold text-slate-900 m-0">{plan.name}</h3>
              {isCurrent && (
                <span className="text-[10px] font-bold uppercase tracking-wide text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full">
                  Current
                </span>
              )}
            </div>
            <p className="text-2xl font-bold text-slate-900 mt-2 m-0">
              {plan.price_inr === 0 ? "Free" : `₹${plan.price_inr.toLocaleString("en-IN")}`}
              {plan.price_inr > 0 && (
                <span className="text-sm font-normal text-slate-500"> / {plan.interval}</span>
              )}
            </p>
            <p className="text-sm text-slate-600 mt-2 m-0 flex-1">{plan.description}</p>
            <ul className="mt-3 space-y-1.5 text-xs text-slate-600 m-0 pl-4 list-disc">
              {plan.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {canUpgrade && (
              <button
                type="button"
                disabled={busy}
                onClick={() => onUpgrade(plan.id)}
                className={`mt-4 w-full py-2.5 rounded-xl text-sm font-semibold disabled:opacity-50 transition-colors ${
                  plan.id === "Legal Pro"
                    ? "bg-amber-600 text-white hover:bg-amber-700"
                    : "bg-slate-900 text-white hover:bg-slate-800"
                }`}
              >
                {stripeEnabled
                  ? `Subscribe — ${plan.name}`
                  : mockBilling
                    ? `Activate ${plan.name} (dev)`
                    : `Subscribe — ${plan.name}`}
              </button>
            )}
            {isFree && !isCurrent && (
              <p className="text-xs text-slate-400 mt-4 m-0">Included for all accounts</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
