"use client";

import type { CollabRoom } from "@/lib/api";
import FirmChatAvatar from "@/components/collaboration/FirmChatAvatar";
import { formatChatTime } from "@/components/collaboration/firmChatUi";

function UnreadBadge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="firm-chat-unread-badge shrink-0 min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white shadow-sm">
      {count > 99 ? "99+" : count}
    </span>
  );
}

function ConversationRow({
  room,
  active,
  online,
  onSelect,
}: {
  room: CollabRoom;
  active: boolean;
  online?: boolean;
  onSelect: (id: string) => void;
}) {
  const preview = room.last_message_preview || room.description || "No messages yet";
  const time = formatChatTime(room.last_message_at || room.updated_at);
  const unread = room.unread_count ?? 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(room.room_id)}
      className={`firm-chat-convo-row w-full text-left flex items-start gap-3 px-3 py-3 transition-colors border-l-[3px] ${
        active
          ? "bg-white border-l-blue-600 shadow-sm"
          : unread > 0
            ? "bg-blue-50/60 border-l-red-500 hover:bg-white"
            : "border-l-transparent hover:bg-white/80"
      }`}
    >
      <FirmChatAvatar
        name={room.name}
        seed={room.peer_user_id || room.room_id}
        online={room.room_type === "dm" ? online : undefined}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className={`truncate text-sm font-semibold ${unread ? "text-slate-900" : "text-slate-800"}`}>
            {room.name}
          </span>
          <span className="text-[10px] text-slate-400 shrink-0 tabular-nums">{time}</span>
        </span>
        <span className="flex items-center justify-between gap-2 mt-0.5">
          <span
            className={`block truncate text-xs ${
              unread ? "text-slate-700 font-medium" : "text-slate-500"
            }`}
          >
            {room.last_sender_name && room.room_type !== "dm"
              ? `${room.last_sender_name}: `
              : ""}
            {preview}
          </span>
          <UnreadBadge count={unread} />
        </span>
      </span>
    </button>
  );
}

export default function FirmChatRoomSidebar({
  sections,
  activeId,
  onlineUserIds,
  onSelect,
}: {
  sections: Array<{ title: string; rooms: CollabRoom[] }>;
  activeId: string;
  onlineUserIds: Set<string>;
  onSelect: (roomId: string) => void;
}) {
  const totalUnread = sections.reduce(
    (n, s) => n + s.rooms.reduce((a, r) => a + (r.unread_count ?? 0), 0),
    0
  );

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#f0f2f5]">
      {totalUnread > 0 && (
        <div className="px-3 py-2 bg-red-50 border-b border-red-100 flex items-center justify-between">
          <span className="text-xs font-semibold text-red-800">{totalUnread} unread</span>
          <span className="firm-chat-unread-badge px-2 py-0.5 rounded-full bg-red-600 text-[10px] text-white font-bold">
            New
          </span>
        </div>
      )}
      <div className="flex-1 overflow-y-auto le-scroll">
        {sections.map((sec) =>
          sec.rooms.length > 0 ? (
            <div key={sec.title} className="py-1">
              <p className="px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 sticky top-0 bg-[#f0f2f5]/95 backdrop-blur z-[1]">
                {sec.title}
              </p>
              <div className="divide-y divide-slate-200/50">
                {sec.rooms.map((room) => (
                  <ConversationRow
                    key={room.room_id}
                    room={room}
                    active={activeId === room.room_id}
                    online={room.peer_user_id ? onlineUserIds.has(room.peer_user_id) : undefined}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            </div>
          ) : null
        )}
      </div>
    </div>
  );
}
