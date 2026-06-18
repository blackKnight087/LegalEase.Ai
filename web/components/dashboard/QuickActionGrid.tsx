"use client";

import Link from "next/link";

export type QuickAction = {
  href: string;
  title: string;
  description: string;
  icon: string;
  accent?: string;
  /** Hidden from dashboard when learner mode is on */
  lawyerOnly?: boolean;
};

export default function QuickActionGrid({ actions }: { actions: QuickAction[] }) {
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      {actions.map((a) => (
        <Link
          key={a.href}
          href={a.href}
          className="group flex gap-3 p-4 rounded-xl border border-slate-200/80 bg-white hover:border-blue-200 hover:shadow-card-hover transition-all duration-200 no-underline hover:-translate-y-px"
        >
          <span
            className={`flex items-center justify-center w-10 h-10 rounded-lg text-lg shrink-0 ${
              a.accent || "bg-blue-50 text-blue-700"
            }`}
          >
            {a.icon}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-navy m-0 group-hover:text-blue-700">
              {a.title}
            </p>
            <p className="text-xs text-slate-500 m-0 mt-0.5 leading-snug">{a.description}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}
