"use client";



import Link from "next/link";

import type { CollabRoom } from "@/lib/api";



export type FirmChatRoomStats = {

  message_count: number;

  documents_shared: number;

  tasks_created: number;

  matter_id?: string;

  matter_name?: string;

};



export default function FirmChatContextRail({

  room,

  stats,

  summary,

  onSummarize,

  busy,

}: {

  room?: CollabRoom;

  stats: FirmChatRoomStats | null;

  summary: Record<string, unknown> | null;

  onSummarize: () => void;

  busy?: boolean;

}) {

  if (!room) {

    return (

      <aside className="firm-chat-rail hidden xl:flex flex-col w-[260px] shrink-0 border-l border-slate-200/80 bg-slate-50/80 p-4">

        <p className="text-xs text-slate-500 leading-relaxed m-0">

          Select a conversation to see matter context, shared documents, tasks, and a quick thread digest.

        </p>

      </aside>

    );

  }



  const actionItems = (summary?.action_items as string[]) || [];

  const deadlines = (summary?.deadlines as string[]) || [];



  return (

    <aside className="firm-chat-rail hidden xl:flex flex-col w-[260px] shrink-0 border-l border-slate-200/80 bg-slate-50/80 overflow-y-auto le-scroll">

      <div className="p-4 space-y-4">

        <div>

          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 m-0">Active chat</p>

          <h3 className="text-sm font-semibold text-slate-900 mt-1 m-0 truncate">{room.name}</h3>

          <p className="text-[11px] text-slate-500 m-0 mt-0.5">

            {room.room_type === "matter"

              ? "Matter channel — tied to case timeline"

              : room.room_type === "channel"

                ? "Practice / firm channel"

                : "Direct message"}

          </p>

        </div>



        {stats && (

          <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2">

            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 m-0">Activity</p>

            <div className="grid grid-cols-2 gap-2 text-center">

              <div className="rounded-lg bg-slate-50 py-2">

                <p className="text-lg font-bold text-slate-900 m-0">{stats.documents_shared}</p>

                <p className="text-[10px] text-slate-500 m-0">Documents</p>

              </div>

              <div className="rounded-lg bg-slate-50 py-2">

                <p className="text-lg font-bold text-slate-900 m-0">{stats.tasks_created}</p>

                <p className="text-[10px] text-slate-500 m-0">Tasks</p>

              </div>

            </div>

            <p className="text-[11px] text-slate-500 m-0">{stats.message_count} messages in view</p>

          </div>

        )}



        {room.matter_id && (

          <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3">

            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-700/80 m-0">Matter</p>

            <p className="text-xs font-semibold text-slate-900 mt-1 m-0 truncate">

              {stats?.matter_name || "Case"}

            </p>

            <Link

              href={`/matters/${room.matter_id}`}

              className="text-[11px] font-medium text-blue-600 hover:underline mt-2 inline-block"

            >

              Open matter →

            </Link>

            <Link

              href={`/matters/${room.matter_id}?tab=timeline`}

              className="text-[11px] font-medium text-blue-600 hover:underline mt-1 block"

            >

              View timeline →

            </Link>

          </div>

        )}



        <div className="rounded-xl border border-slate-200 bg-white p-3">

          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 m-0">Thread digest</p>

          <p className="text-[11px] text-slate-600 mt-1 m-0 leading-relaxed">

            Pulls recent messages and flags likely action items and deadlines — no AI.

          </p>

          <button

            type="button"

            disabled={busy}

            onClick={onSummarize}

            className="mt-2 w-full text-xs font-semibold rounded-lg bg-slate-800 text-white py-2 hover:bg-slate-900 disabled:opacity-50"

          >

            {busy ? "Loading…" : "Refresh digest"}

          </button>

        </div>



        {summary && (

          <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs space-y-2 max-h-64 overflow-y-auto le-scroll">

            <p className="font-semibold text-amber-950 m-0">Recent discussion</p>

            <p className="text-slate-700 whitespace-pre-wrap m-0 leading-relaxed">

              {String(summary.summary_text || "")}

            </p>

            {actionItems.length > 0 && (

              <div>

                <p className="font-semibold text-slate-800 m-0 mb-1">Possible action items</p>

                <ul className="m-0 pl-4 text-slate-600 space-y-0.5">

                  {actionItems.map((a, i) => (

                    <li key={i}>{a}</li>

                  ))}

                </ul>

              </div>

            )}

            {deadlines.length > 0 && (

              <div>

                <p className="font-semibold text-slate-800 m-0 mb-1">Date mentions</p>

                <ul className="m-0 pl-4 text-slate-600 space-y-0.5">

                  {deadlines.map((a, i) => (

                    <li key={i}>{a}</li>

                  ))}

                </ul>

              </div>

            )}

          </div>

        )}



        <p className="text-[10px] text-slate-400 m-0 leading-relaxed">

          Internal firm chat (free on all accounts). Client portal chat is separate.

        </p>

      </div>

    </aside>

  );

}

