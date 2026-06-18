"use client";

import type { CollabRoom } from "@/lib/api";
import FirmChatAvatar from "@/components/collaboration/FirmChatAvatar";
import { formatChatTime } from "@/components/collaboration/firmChatUi";
import { Button } from "@/components/ui/Button";

export default function FirmChatInboxHome({
  rooms,
  onSelect,
  onNewMessage,
}: {
  rooms: CollabRoom[];
  onSelect: (id: string) => void;
  onNewMessage: () => void;
}) {
  const recent = [...rooms]
    .sort((a, b) => {
      const ta = a.last_message_at || a.updated_at || "";
      const tb = b.last_message_at || b.updated_at || "";
      return tb.localeCompare(ta);
    })
    .slice(0, 12);

  return (
    <div className="flex-1 overflow-y-auto le-scroll firm-chat-inbox-home p-6">
      <div className="max-w-2xl mx-auto">
        <h2 className="text-xl font-bold text-slate-900 m-0">Recent conversations</h2>
        <p className="text-sm text-slate-500 mt-1 mb-6">
          Pick a thread below — your firm runs here, not on WhatsApp.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {recent.map((room) => (
            <button
              key={room.room_id}
              type="button"
              onClick={() => onSelect(room.room_id)}
              className="firm-chat-inbox-card text-left flex items-start gap-3 p-4 rounded-xl border border-slate-200/90 bg-white hover:border-blue-300 hover:shadow-md transition-all"
            >
              <FirmChatAvatar name={room.name} seed={room.peer_user_id || room.room_id} />
              <span className="min-w-0 flex-1">
                <span className="flex justify-between gap-2">
                  <span className="font-semibold text-sm text-slate-900 truncate">{room.name}</span>
                  {(room.unread_count ?? 0) > 0 && (
                    <span className="shrink-0 min-w-[18px] h-[18px] rounded-full bg-red-600 text-[10px] font-bold text-white flex items-center justify-center px-1">
                      {room.unread_count! > 9 ? "9+" : room.unread_count}
                    </span>
                  )}
                </span>
                <span className="block text-xs text-slate-500 truncate mt-1">
                  {room.last_message_preview || "Start chatting"}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">
                  {formatChatTime(room.last_message_at || room.updated_at)}
                </span>
              </span>
            </button>
          ))}
        </div>
        {recent.length === 0 && (
          <div className="text-center py-12 rounded-2xl border border-dashed border-slate-300 bg-white">
            <p className="text-slate-600 m-0">No conversations yet.</p>
            <Button className="mt-4" onClick={onNewMessage}>
              Start a message
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
