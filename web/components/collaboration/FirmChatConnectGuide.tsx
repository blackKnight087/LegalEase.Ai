"use client";

import Link from "next/link";
import { FIRM_CHAT_FREE_NOTE, FIRM_CHAT_NAME } from "@/lib/firmChat";

export default function FirmChatConnectGuide({
  onFindSomeone,
  onDismiss,
}: {
  onFindSomeone: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="mx-4 mt-3 mb-1 px-4 py-3 rounded-xl border border-slate-200/80 bg-gradient-to-r from-slate-50 to-blue-50/50 text-sm shrink-0 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 m-0 text-sm">Quick start</p>
          <p className="text-xs text-slate-600 m-0 mt-1 leading-relaxed">
            {FIRM_CHAT_FREE_NOTE} Channels, voice notes, DMs, and matter threads are all included.
          </p>
        </div>
        <button
          type="button"
          className="shrink-0 text-slate-400 hover:text-slate-600 p-1"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button
          type="button"
          onClick={onFindSomeone}
          className="text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
        >
          Find someone
        </button>
        <Link
          href="/settings/team"
          className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
        >
          Invite team
        </Link>
      </div>
    </div>
  );
}
