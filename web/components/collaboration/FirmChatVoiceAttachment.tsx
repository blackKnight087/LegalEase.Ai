"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";

export function pickVoiceAttachment(message: api.CollabMessage) {
  return message.attachments?.find(
    (a) =>
      (a.mime_type || "").startsWith("audio/") ||
      /\.(webm|ogg|mp3|m4a|wav)$/i.test(a.filename || "")
  );
}

export default function FirmChatVoiceAttachment({
  attachment,
  isMine,
}: {
  attachment: NonNullable<api.CollabMessage["attachments"]>[number];
  isMine?: boolean;
}) {
  const [src, setSrc] = useState("");
  const [err, setErr] = useState(false);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef("");

  useEffect(() => {
    let cancelled = false;
    setErr(false);
    void api
      .fetchCollabAttachmentObjectUrl(attachment.attachment_id)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setErr(true);
      });
    return () => {
      cancelled = true;
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = "";
      }
    };
  }, [attachment.attachment_id]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el || !src) return;
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      void el.play().then(() => setPlaying(true)).catch(() => setErr(true));
    }
  };

  const shell = isMine
    ? "border-gray-400/60 bg-gray-500/40 text-white"
    : "border-gray-200 bg-gray-50 text-gray-900";

  if (err) {
    return (
      <p className={`mt-2 text-xs m-0 ${isMine ? "text-gray-200" : "text-gray-500"}`}>
        Could not load voice message
      </p>
    );
  }

  return (
    <div className={`mt-2 flex items-center gap-2 rounded-xl border px-3 py-2 ${shell}`}>
      <button
        type="button"
        onClick={toggle}
        disabled={!src}
        className={`shrink-0 h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold ${
          isMine ? "bg-gray-400 hover:bg-gray-300 text-white" : "bg-gray-600 text-white hover:bg-gray-500"
        } disabled:opacity-40`}
        aria-label={playing ? "Pause voice message" : "Play voice message"}
      >
        {src ? (playing ? "❚❚" : "▶") : "…"}
      </button>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold m-0">Voice message</p>
        <p className={`text-[10px] m-0 truncate ${isMine ? "text-gray-200" : "text-gray-500"}`}>
          Tap to listen
        </p>
      </div>
      {src && (
        <audio
          ref={audioRef}
          src={src}
          className="hidden"
          onEnded={() => setPlaying(false)}
          onPause={() => setPlaying(false)}
        />
      )}
    </div>
  );
}
