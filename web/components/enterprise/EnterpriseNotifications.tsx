"use client";

import { useState } from "react";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  urgency: string;
};

export default function EnterpriseNotifications({
  items,
  inHeader = false,
}: {
  items: Notification[];
  inHeader?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const urgent = items.filter((n) => n.urgency === "high" && n.id !== "none").length;
  const count = items.filter((n) => n.id !== "none").length;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`ent-notify-btn relative ${inHeader ? "ent-notify-btn--header" : ""}`}
        aria-label="Notifications"
      >
        🔔
        {urgent > 0 && (
          <span className="ent-notify-badge ent-notify-badge--urgent">{urgent}</span>
        )}
        {urgent === 0 && count > 0 && (
          <span className="ent-notify-badge">{count > 9 ? "9+" : count}</span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 top-full mt-2 z-50 w-[320px] rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden">
            <div className="px-4 py-3 border-b bg-slate-50 font-semibold text-sm text-navy">
              Notifications
            </div>
            <ul className="max-h-[360px] overflow-y-auto le-scroll list-none m-0 p-0">
              {items.map((n) => (
                <li key={n.id} className="px-4 py-3 border-b border-slate-50 text-sm">
                  <p className="font-medium text-navy m-0">{n.title}</p>
                  <p className="text-xs text-slate-500 m-0 mt-1">{n.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
