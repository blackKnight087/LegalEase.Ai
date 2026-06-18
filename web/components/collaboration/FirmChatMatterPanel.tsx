"use client";

import Link from "next/link";
import type { CollabRoom } from "@/lib/api";
import FirmChatAvatar from "@/components/collaboration/FirmChatAvatar";
import { formatChatTime } from "@/components/collaboration/firmChatUi";

export type FirmChatRoomContext = {
  room_id?: string;
  room_type?: string;
  room_name?: string;
  matter_id?: string;
  matter_name?: string;
  open_tasks?: number;
  total_tasks?: number;
  documents?: number;
  evidence?: number;
  next_deadline?: string;
  participants?: Array<{ user_id: string; username: string; role?: string }>;
  timeline?: Array<{ title: string; event_type?: string; created_at?: string }>;
  pinned_files?: Array<{ attachment_id: string; filename: string }>;
  peer?: { user_id: string; username: string; online?: boolean; last_seen?: number };
  shared_files?: Array<{ attachment_id: string; filename: string }>;
};

export default function FirmChatMatterPanel({
  room,
  context,
  loading,
}: {
  room?: CollabRoom;
  context: FirmChatRoomContext | null;
  loading?: boolean;
}) {
  if (!room) {
    return (
      <aside className="firm-chat-rail hidden xl:flex flex-col w-[300px] shrink-0 border-l border-slate-200 bg-slate-50 p-5">
        <p className="text-sm text-slate-500 m-0 leading-relaxed">
          Select a conversation to see matter intelligence, participants, and activity.
        </p>
      </aside>
    );
  }

  return (
    <aside className="firm-chat-rail hidden xl:flex flex-col w-[300px] shrink-0 border-l border-slate-200 bg-white overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-blue-50/40">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 m-0">Context</p>
        <h3 className="text-sm font-bold text-slate-900 mt-1 m-0 truncate">
          {context?.matter_name || room.name}
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto le-scroll p-4 space-y-4">
        {loading && <p className="text-xs text-slate-400">Loading…</p>}

        {context?.peer && (
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-center gap-3">
              <FirmChatAvatar name={context.peer.username} online={context.peer.online} size="lg" />
              <div>
                <p className="text-sm font-bold text-slate-900 m-0">{context.peer.username}</p>
                <p className="text-xs m-0 mt-0.5 flex items-center gap-1.5">
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${
                      context.peer.online ? "bg-emerald-500" : "bg-slate-300"
                    }`}
                  />
                  {context.peer.online ? "Online now" : "Offline"}
                </p>
              </div>
            </div>
          </div>
        )}

        {context?.matter_id && (
          <>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Open tasks", value: context.open_tasks ?? 0, href: `/matters/${context.matter_id}/tasks` },
                { label: "Documents", value: context.documents ?? 0, href: `/matters/${context.matter_id}` },
                { label: "Evidence", value: context.evidence ?? 0, href: `/matters/${context.matter_id}` },
                {
                  label: "Next deadline",
                  value: context.next_deadline || "—",
                  href: `/matters/${context.matter_id}`,
                },
              ].map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  className="rounded-xl border border-slate-200 bg-slate-50/80 p-3 hover:border-blue-300 transition-colors"
                >
                  <p className="text-[10px] uppercase tracking-wide text-slate-500 m-0">{item.label}</p>
                  <p className="text-lg font-bold text-slate-900 m-0 mt-1 truncate">{item.value}</p>
                </Link>
              ))}
            </div>

            {context.participants && context.participants.length > 0 && (
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400 m-0 mb-2">Participants</p>
                <div className="space-y-2">
                  {context.participants.map((p) => (
                    <div key={p.user_id} className="flex items-center gap-2 text-xs">
                      <FirmChatAvatar name={p.username} seed={p.user_id} size="sm" />
                      <span className="font-medium text-slate-800">{p.username}</span>
                      <span className="text-slate-400 ml-auto">{p.role}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {context.timeline && context.timeline.length > 0 && (
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400 m-0 mb-2">Activity</p>
                <ul className="space-y-2 m-0 p-0 list-none">
                  {context.timeline.map((ev, i) => (
                    <li key={i} className="text-xs border-l-2 border-blue-200 pl-3 py-0.5">
                      <span className="text-[10px] text-slate-400 block">
                        {formatChatTime(ev.created_at)}
                      </span>
                      <span className="text-slate-800">{ev.title}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/matters/${context.matter_id}?tab=timeline`}
                  className="text-xs font-medium text-blue-600 hover:underline mt-2 inline-block"
                >
                  Full timeline →
                </Link>
              </div>
            )}
          </>
        )}

        {(context?.pinned_files?.length || context?.shared_files?.length) ? (
          <div>
            <p className="text-[10px] font-bold uppercase text-slate-400 m-0 mb-2">Recent files</p>
            <ul className="space-y-1 m-0 p-0 list-none">
              {(context.pinned_files || context.shared_files || []).map((f) => (
                <li key={f.attachment_id}>
                  <a
                    href={`/api/v1/collaboration/attachments/${f.attachment_id}/download`}
                    className="text-xs text-blue-600 hover:underline truncate block"
                    target="_blank"
                    rel="noreferrer"
                  >
                    📎 {f.filename}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
