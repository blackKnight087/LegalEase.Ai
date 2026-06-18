"use client";

import * as api from "@/lib/api";
import FirmChatRichAttachment from "@/components/collaboration/FirmChatRichAttachment";
import FirmChatVoiceAttachment, {
  pickVoiceAttachment,
} from "@/components/collaboration/FirmChatVoiceAttachment";

function avatarColor(seed: string): string {
  const colors = ["#475569", "#64748b", "#334155", "#57534e", "#4b5563", "#374151"];
  let n = 0;
  for (let i = 0; i < seed.length; i++) n += seed.charCodeAt(i);
  return colors[n % colors.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (name.slice(0, 2) || "?").toUpperCase();
}

function formatMessageTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function firmChatDayKey(iso: string): string {
  try {
    return new Date(iso).toDateString();
  } catch {
    return iso;
  }
}

export function formatDayLabel(iso: string): string {
  try {
    const d = new Date(iso);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export function FirmChatDayDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-5" role="separator">
      <div className="h-px flex-1 bg-gray-200" />
      <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 shrink-0 px-2">
        {label}
      </span>
      <div className="h-px flex-1 bg-gray-200" />
    </div>
  );
}

function ReactionBar({
  reactions,
  isMine,
}: {
  reactions?: api.CollabMessage["reactions"];
  isMine?: boolean;
}) {
  if (!reactions?.length) return null;
  const grouped: Record<string, number> = {};
  for (const r of reactions) {
    grouped[r.emoji] = (grouped[r.emoji] || 0) + 1;
  }
  return (
    <div className={`flex flex-wrap gap-1 mt-1.5 ${isMine ? "justify-end" : "justify-start"}`}>
      {Object.entries(grouped).map(([emoji, count]) => (
        <span
          key={emoji}
          className={`text-[10px] px-2 py-0.5 rounded-full border shadow-sm ${
            isMine
              ? "border-gray-400 bg-gray-500 text-white"
              : "border-gray-200 bg-white text-gray-600"
          }`}
        >
          {emoji} {count > 1 ? count : ""}
        </span>
      ))}
    </div>
  );
}

function DeliveryStatus({
  seenBy,
  delivered = true,
}: {
  seenBy?: string[];
  delivered?: boolean;
}) {
  const read = (seenBy?.length ?? 0) > 0;
  return (
    <span
      className="inline-flex items-center gap-1 firm-chat-meta text-slate-400"
      title={read ? `Read by ${seenBy!.join(", ")}` : delivered ? "Delivered" : "Sending"}
    >
      <span className={`inline-flex ${read ? "text-slate-500" : "text-slate-400"}`} aria-hidden>
        {read ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="shrink-0">
            <path
              d="M4 12.5l4 4L16 7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M9 12.5l4 4L21 7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="shrink-0">
            <path
              d="M5 12.5l4 4L19 7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>
      {read && (
        <span className="text-slate-500 max-w-[140px] truncate">
          Read{seenBy!.length === 1 ? ` · ${seenBy![0]}` : ""}
        </span>
      )}
      {!read && delivered && <span>Delivered</span>}
    </span>
  );
}

function MessageMeta({
  time,
  isMine,
  seenBy,
}: {
  time: string;
  isMine: boolean;
  seenBy?: string[];
}) {
  return (
    <div
      className={`flex items-center gap-2 mt-1.5 px-0.5 firm-chat-meta ${
        isMine ? "justify-end flex-row-reverse" : "justify-start"
      }`}
    >
      <span className="text-gray-400 tabular-nums">{time}</span>
      {isMine && <DeliveryStatus seenBy={seenBy} />}
    </div>
  );
}

const QUICK_REACTIONS = ["👍", "❤️", "✅", "🙏"];

function MessageBody({
  message,
  isMine,
}: {
  message: api.CollabMessage;
  isMine?: boolean;
}) {
  const isTask = message.message_type === "task_ref";
  const voiceAtt = pickVoiceAttachment(message);
  const isVoice = message.message_type === "voice" || Boolean(voiceAtt);
  const showText =
    !isVoice || (message.body && !/^🎤?\s*voice note/i.test(message.body.trim()));

  return (
    <>
      {isTask && (
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide block mb-1.5 ${
            isMine ? "text-gray-200" : "text-gray-500"
          }`}
        >
          Task linked
        </span>
      )}
      {isVoice && voiceAtt && <FirmChatVoiceAttachment attachment={voiceAtt} isMine={isMine} />}
      {showText && message.body && (
        <p className="m-0 whitespace-pre-wrap break-words text-[13px] leading-[1.55]">{message.body}</p>
      )}
      {message.attachments
        ?.filter((a) => a.attachment_id !== voiceAtt?.attachment_id)
        .map((a) => (
          <FirmChatRichAttachment key={a.attachment_id} attachment={a} isMine={isMine} />
        ))}
    </>
  );
}

function MessageActions({
  onReact,
  onCreateTask,
  onCreateDeadline,
}: {
  onReact?: (emoji: string) => void;
  onCreateTask?: () => void;
  onCreateDeadline?: () => void;
}) {
  if (!onReact && !onCreateTask && !onCreateDeadline) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 mt-1 px-0.5 opacity-0 group-hover/firm-msg:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
      {onReact &&
        QUICK_REACTIONS.map((em) => (
          <button
            key={em}
            type="button"
            className="h-7 w-7 flex items-center justify-center rounded-md border border-gray-200 bg-white text-sm hover:bg-gray-50 hover:border-gray-300 transition-colors"
            onClick={() => onReact(em)}
            aria-label={`React ${em}`}
          >
            {em}
          </button>
        ))}
      {onCreateTask && (
        <button
          type="button"
          className="text-[11px] font-medium text-gray-500 hover:text-gray-900 px-2 py-1 rounded-md hover:bg-gray-100 transition-colors"
          onClick={onCreateTask}
        >
          Create task
        </button>
      )}
      {onCreateDeadline && (
        <button
          type="button"
          className="text-[11px] font-medium text-gray-500 hover:text-gray-900 px-2 py-1 rounded-md hover:bg-gray-100 transition-colors"
          onClick={onCreateDeadline}
        >
          Add deadline
        </button>
      )}
    </div>
  );
}

export default function FirmChatMessage({
  message,
  isMine,
  showAvatar,
  showSenderLabel,
  isGroupRoom,
  onReact,
  onCreateTask,
  onCreateDeadline,
}: {
  message: api.CollabMessage;
  isMine: boolean;
  showAvatar: boolean;
  showSenderLabel: boolean;
  isGroupRoom?: boolean;
  onReact?: (emoji: string) => void;
  onCreateTask?: () => void;
  onCreateDeadline?: () => void;
}) {
  const name = message.sender_name || "Colleague";
  const time = formatMessageTime(message.created_at);

  if (isMine) {
    return (
      <div className="flex w-full justify-end py-1.5 firm-chat-row-mine group/firm-msg">
        <div className="flex max-w-[min(75%,420px)] flex-col items-end">
          <div className="firm-chat-bubble-mine px-4 py-3">
            <MessageBody message={message} isMine />
          </div>
          <ReactionBar reactions={message.reactions} isMine />
          <MessageMeta time={time} isMine seenBy={message.seen_by} />
          <MessageActions
            onReact={onReact}
            onCreateTask={onCreateTask}
            onCreateDeadline={onCreateDeadline}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full justify-start gap-3 py-1.5 firm-chat-row-theirs group/firm-msg">
      {showAvatar ? (
        <div
          className="mt-6 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white shadow-sm"
          style={{ backgroundColor: avatarColor(message.sender_id || name) }}
          title={name}
        >
          {initials(name)}
        </div>
      ) : (
        <div className="w-8 shrink-0" aria-hidden />
      )}
      <div className="flex max-w-[min(75%,420px)] flex-col items-start min-w-0">
        {(showSenderLabel || isGroupRoom) && (
          <span className="px-1 mb-1 text-[11px] font-semibold text-gray-600">
            {name}
          </span>
        )}
        <div className="firm-chat-bubble-theirs px-4 py-3 w-full">
          <MessageBody message={message} />
        </div>
        <ReactionBar reactions={message.reactions} />
        <MessageMeta time={time} isMine={false} />
        <MessageActions
          onReact={onReact}
          onCreateTask={onCreateTask}
          onCreateDeadline={onCreateDeadline}
        />
      </div>
    </div>
  );
}
