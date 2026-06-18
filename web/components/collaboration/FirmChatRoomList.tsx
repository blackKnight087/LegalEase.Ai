"use client";

import type { CollabRoom } from "@/lib/api";

function roomIcon(room: CollabRoom) {
  if (room.room_type === "dm") return "💬";
  if (room.room_type === "matter") return "📁";
  return "#";
}

function roomSubtitle(room: CollabRoom): string {
  if (room.room_type === "channel") return "Channel";
  if (room.room_type === "matter") return "Case";
  if (room.is_private_dm || room.room_type === "dm") return "Private · 1-to-1";
  return "Direct";
}

export default function FirmChatRoomList({
  sections,
  activeId,
  onSelect,
}: {
  sections: Array<{ title: string; rooms: CollabRoom[] }>;
  activeId: string;
  onSelect: (roomId: string) => void;
}) {
  const hasAny = sections.some((s) => s.rooms.length > 0);

  return (
    <div className="flex-1 overflow-y-auto le-scroll py-2 px-2 space-y-4">
      {!hasAny && (
        <div className="px-3 py-8 text-center">
          <p className="text-xs font-semibold text-slate-700 m-0">Your legal workspace is ready</p>
          <p className="text-xs text-slate-500 mt-2 m-0 leading-relaxed">
            Open a <strong>matter channel</strong> (auto-created per case), join a practice team channel, or send a
            secure DM after they accept your request.
          </p>
        </div>
      )}
      {sections.map(
        (sec) =>
          sec.rooms.length > 0 && (
            <div key={sec.title}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 mb-1">
                {sec.title}
              </p>
              <div className="space-y-0.5">
                {sec.rooms.map((room) => {
                  const active = activeId === room.room_id;
                  const unread = (room.unread_count ?? 0) > 0 && !active;
                  return (
                    <button
                      key={room.room_id}
                      type="button"
                      onClick={() => onSelect(room.room_id)}
                      className={`w-full text-left rounded-xl px-2.5 py-2.5 transition-all flex items-center gap-3 ${
                        active
                          ? "bg-blue-600 text-white shadow-md shadow-blue-900/15"
                          : "text-slate-800 hover:bg-white"
                      }`}
                    >
                      <span
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg ${
                          active
                            ? "bg-white/20"
                            : "bg-slate-100 border border-slate-200/80"
                        }`}
                      >
                        {roomIcon(room)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className={`block truncate text-sm font-semibold ${active ? "" : "text-slate-900"}`}>
                            {room.name}
                          </span>
                          {unread && (
                            <span className="shrink-0 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white px-1">
                              {room.unread_count! > 9 ? "9+" : room.unread_count}
                            </span>
                          )}
                        </span>
                        <span className={`block text-[11px] truncate mt-0.5 ${active ? "text-blue-100" : "text-slate-500"}`}>
                          {roomSubtitle(room)}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )
      )}
    </div>
  );
}
