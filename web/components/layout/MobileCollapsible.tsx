"use client";

import { ReactNode, useState } from "react";

export default function MobileCollapsible({
  title,
  children,
  defaultOpen = false,
  className = "",
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`lg:hidden rounded-xl border border-slate-200 bg-white overflow-hidden ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-xs font-semibold text-slate-700 bg-slate-50/80"
        aria-expanded={open}
      >
        <span>{title}</span>
        <span className="text-slate-400 text-[10px]" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open ? <div className="px-3 pb-3 pt-2 space-y-3 border-t border-slate-100">{children}</div> : null}
    </div>
  );
}
