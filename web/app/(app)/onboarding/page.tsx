"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import * as api from "@/lib/api";

export default function OnboardingPage() {
  const [state, setState] = useState<api.OnboardingState | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api
      .fetchOnboarding()
      .then(setState)
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dismiss = async () => {
    await api.dismissOnboarding();
    load();
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader title="Get started" subtitle="Complete these steps to set up your workspace" />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-2xl mx-auto w-full space-y-4 sm:space-y-6">
        {err && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        {state && (
          <>
            <div className="bg-white border rounded-2xl p-6">
              <div className="flex justify-between text-sm mb-2">
                <span className="font-medium text-navy">Progress</span>
                <span>{state.percent}%</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 transition-all"
                  style={{ width: `${state.percent}%` }}
                />
              </div>
            </div>
            <ol className="space-y-3">
              {state.steps.map((step) => (
                <li
                  key={step.id}
                  className={`flex items-center gap-3 p-4 rounded-xl border ${
                    step.done ? "bg-green-50 border-green-200" : "bg-white border-slate-200"
                  }`}
                >
                  <span className="text-lg">{step.done ? "✓" : "○"}</span>
                  <div className="flex-1">
                    <p className="font-medium text-navy">{step.title}</p>
                  </div>
                  {!step.done && step.href && (
                    <Link
                      href={step.href}
                      className="text-sm font-medium text-blue-700 hover:underline"
                    >
                      Go
                    </Link>
                  )}
                </li>
              ))}
            </ol>
            {!state.dismissed && (
              <button
                type="button"
                onClick={() => void dismiss()}
                className="text-sm text-slate-600 hover:text-navy underline"
              >
                Dismiss checklist
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
