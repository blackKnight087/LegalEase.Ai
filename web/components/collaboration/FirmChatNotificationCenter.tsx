"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { formatChatTime, notificationIcon } from "@/components/collaboration/firmChatUi";

export default function FirmChatNotificationCenter({
  onOpenRoom,
  totalUnreadRooms,
}: {
  onOpenRoom?: (roomId: string) => void;
  totalUnreadRooms?: number;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<api.CollabNotification[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.fetchCollabNotifications(false);
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

  const unreadNotifs = items.filter((n) => !n.read).length;
  const badge = Math.max(unreadNotifs, totalUnreadRooms ?? 0);

  return (
    <>
      <button
        type="button"
        className="relative h-10 w-10 flex items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 shadow-sm"
        aria-label={`Notifications${badge ? `, ${badge} new` : ""}`}
        onClick={() => {
          setOpen((v) => !v);
          if (!open) void load();
        }}
      >
        <span className="text-lg" aria-hidden>
          🔔
        </span>
        {badge > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-600 text-[10px] font-bold text-white flex items-center justify-center shadow-md ring-2 ring-white">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </button>

      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-[1px]"
            aria-label="Close notifications"
            onClick={() => setOpen(false)}
          />
          <div className="firm-chat-notif-panel fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-white shadow-2xl flex flex-col border-l border-slate-200">
            <header className="shrink-0 px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
              <div>
                <h2 className="text-base font-bold text-slate-900 m-0">Notifications</h2>
                <p className="text-xs text-slate-500 m-0 mt-0.5">
                  {unreadNotifs ? `${unreadNotifs} unread` : "All caught up"}
                </p>
              </div>
              <button
                type="button"
                className="h-9 w-9 rounded-lg hover:bg-slate-100 text-slate-500"
                onClick={() => setOpen(false)}
              >
                ✕
              </button>
            </header>
            <div className="flex-1 overflow-y-auto le-scroll divide-y divide-slate-100">
              {loading && items.length === 0 && (
                <p className="text-sm text-slate-400 p-6 text-center">Loading…</p>
              )}
              {!loading && items.length === 0 && (
                <p className="text-sm text-slate-500 p-8 text-center">No notifications yet.</p>
              )}
              {items.map((n) => (
                <button
                  key={n.notification_id}
                  type="button"
                  className={`w-full text-left px-5 py-4 hover:bg-slate-50 flex gap-3 ${
                    !n.read ? "bg-red-50/40" : ""
                  }`}
                  onClick={async () => {
                    await api.markCollabNotificationRead(n.notification_id).catch(() => undefined);
                    if (n.room_id && onOpenRoom) onOpenRoom(n.room_id);
                    setOpen(false);
                    load();
                  }}
                >
                  <span
                    className={`shrink-0 h-10 w-10 rounded-xl flex items-center justify-center text-sm font-bold ${
                      !n.read ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {notificationIcon(n.type)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900 truncate">{n.title}</span>
                      {!n.read && (
                        <span className="shrink-0 w-2 h-2 rounded-full bg-red-600" aria-label="Unread" />
                      )}
                    </span>
                    {n.body && (
                      <span className="block text-xs text-slate-600 mt-0.5 line-clamp-2">{n.body}</span>
                    )}
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      {formatChatTime(n.created_at)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}
