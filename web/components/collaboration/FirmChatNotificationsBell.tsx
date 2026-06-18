"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

export default function FirmChatNotificationsBell({
  onOpenRoom,
}: {
  onOpenRoom?: (roomId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<api.CollabNotification[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.fetchCollabNotifications(true);
      setItems(r.notifications || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 45000);
    const onRefresh = () => load();
    window.addEventListener("legalease:firm-chat-notify", onRefresh);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("legalease:firm-chat-notify", onRefresh);
    };
  }, [load]);

  const unread = items.filter((n) => !n.read).length;

  return (
    <div className="relative">
      <button
        type="button"
        className="relative h-9 w-9 flex items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        onClick={() => {
          setOpen((v) => !v);
          if (!open) void load();
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-[9px] font-bold text-white flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-label="Close notifications"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full mt-2 z-50 w-80 max-h-[70vh] overflow-y-auto le-scroll rounded-xl border border-slate-200 bg-white shadow-xl">
            <div className="sticky top-0 px-3 py-2 border-b border-slate-100 bg-white flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-800">Notifications</span>
              {loading && <span className="text-[10px] text-slate-400">…</span>}
            </div>
            {items.length === 0 ? (
              <p className="text-xs text-slate-500 px-4 py-8 text-center">You&apos;re all caught up.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {items.map((n) => (
                  <li key={n.notification_id}>
                    <button
                      type="button"
                      className="w-full text-left px-3 py-2.5 hover:bg-slate-50"
                      onClick={async () => {
                        await api.markCollabNotificationRead(n.notification_id).catch(() => undefined);
                        if (n.room_id && onOpenRoom) onOpenRoom(n.room_id);
                        setOpen(false);
                        load();
                      }}
                    >
                      <p className="text-xs font-semibold text-slate-900 m-0 truncate">{n.title}</p>
                      {n.body && (
                        <p className="text-[11px] text-slate-500 m-0 mt-0.5 line-clamp-2">{n.body}</p>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
