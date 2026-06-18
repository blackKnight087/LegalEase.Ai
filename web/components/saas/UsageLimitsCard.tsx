"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";

type Props = {
  documentCount?: number;
  documentLimit?: number;
  geminiToday?: number;
  geminiLimit?: number;
  compact?: boolean;
};

const PLAN_LIMITS: Record<string, { docs: number; gemini: number }> = {
  Free: { docs: 5, gemini: 3 },
  Pro: { docs: 9999, gemini: 50 },
  "Legal Pro": { docs: 9999, gemini: 200 },
};

export default function UsageLimitsCard({
  documentCount = 0,
  documentLimit,
  geminiToday = 0,
  geminiLimit,
  compact = false,
}: Props) {
  const { user } = useAuth();
  const plan = user?.membership || "Free";
  const defaults = PLAN_LIMITS[plan] || PLAN_LIMITS.Free;
  const docMax = documentLimit ?? defaults.docs;
  const gemMax = geminiLimit ?? defaults.gemini;
  const docPct = docMax > 0 ? Math.min(100, Math.round((documentCount / docMax) * 100)) : 0;
  const gemPct = gemMax > 0 ? Math.min(100, Math.round((geminiToday / gemMax) * 100)) : 0;
  const atDocCap = documentCount >= docMax && plan === "Free";

  return (
    <section
      className={`bg-white rounded-2xl border border-slate-200 ${compact ? "p-4" : "p-6"}`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <h2 className={`font-semibold text-navy ${compact ? "text-sm" : ""}`}>
          Plan usage — {plan}
        </h2>
        {plan === "Free" && (
          <Link
            href="/settings/subscription"
            className="text-xs font-semibold text-blue-700 hover:underline"
          >
            Upgrade
          </Link>
        )}
      </div>
      <div className="space-y-3 text-sm">
        <div>
          <div className="flex justify-between text-slate-600 mb-1">
            <span>Documents</span>
            <span>
              {documentCount} / {docMax >= 9999 ? "∞" : docMax}
            </span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${atDocCap ? "bg-amber-500" : "bg-blue-600"}`}
              style={{ width: `${docPct}%` }}
            />
          </div>
          {atDocCap && (
            <p className="text-xs text-amber-700 mt-1">
              Document limit reached.{" "}
              <Link href="/settings/subscription" className="underline font-medium">
                Upgrade to Pro
              </Link>
            </p>
          )}
        </div>
        <div>
          <div className="flex justify-between text-slate-600 mb-1">
            <span>Web Intel today</span>
            <span>
              {geminiToday} / {gemMax}
            </span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-violet-600 rounded-full"
              style={{ width: `${gemPct}%` }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
