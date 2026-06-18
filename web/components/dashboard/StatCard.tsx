"use client";

import Link from "next/link";

type Props = {
  label: string;
  value: string | number;
  sublabel?: string;
  icon?: string;
  href?: string;
  accent?: "navy" | "blue" | "emerald" | "amber" | "violet" | "slate";
  loading?: boolean;
};

const ACCENTS: Record<NonNullable<Props["accent"]>, string> = {
  navy: "from-[#0f172a] to-[#1e3a5f]",
  blue: "from-[#1e40af] to-[#2563eb]",
  emerald: "from-emerald-700 to-emerald-500",
  amber: "from-amber-700 to-amber-500",
  violet: "from-violet-700 to-violet-500",
  slate: "from-slate-700 to-slate-500",
};

export default function StatCard({
  label,
  value,
  sublabel,
  icon,
  href,
  accent = "blue",
  loading,
}: Props) {
  const inner = (
    <div
      className={`le-interactive relative overflow-hidden rounded-2xl bg-gradient-to-br ${ACCENTS[accent]} text-white p-5 shadow-md hover:shadow-lg ${
        href ? "cursor-pointer hover:scale-[1.01]" : ""
      }`}
    >
      <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full bg-white/10" />
      <div className="relative flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-white/75 m-0">
            {label}
          </p>
          {loading ? (
            <div className="h-9 w-20 mt-2 rounded-lg bg-white/20 animate-pulse" />
          ) : (
            <p className="text-3xl font-bold m-0 mt-1 tabular-nums">{value}</p>
          )}
          {sublabel && !loading && (
            <p className="text-xs text-white/70 m-0 mt-1">{sublabel}</p>
          )}
        </div>
        {icon ? (
          <span className="text-2xl opacity-90 shrink-0" aria-hidden>
            {icon}
          </span>
        ) : null}
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block no-underline">
        {inner}
      </Link>
    );
  }
  return inner;
}
