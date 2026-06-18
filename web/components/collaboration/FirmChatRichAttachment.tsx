"use client";

import * as api from "@/lib/api";

function isPreviewable(mime?: string, name?: string): boolean {
  const m = (mime || "").toLowerCase();
  const n = (name || "").toLowerCase();
  return m.startsWith("image/") || m.includes("pdf") || n.endsWith(".pdf") || /\.(png|jpe?g|webp|gif)$/i.test(n);
}

export default function FirmChatRichAttachment({
  attachment,
  isMine,
}: {
  attachment: NonNullable<api.CollabMessage["attachments"]>[number];
  isMine?: boolean;
}) {
  const url = api.collabAttachmentUrl(attachment.attachment_id);
  const preview = isPreviewable(attachment.mime_type, attachment.filename);
  const cardClass = isMine
    ? "mt-2.5 rounded-xl border border-gray-400/60 bg-gray-500/40 overflow-hidden"
    : "mt-2.5 rounded-xl border border-gray-200 bg-gray-50 overflow-hidden";

  return (
    <div className={cardClass}>
      {preview && attachment.mime_type?.startsWith("image/") && (
        <a href={url} target="_blank" rel="noreferrer" className="block">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={attachment.filename}
            className="max-h-40 w-full object-cover bg-slate-100"
          />
        </a>
      )}
      <div className="px-3 py-2.5 text-left">
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className={`text-sm font-semibold truncate block hover:underline ${
            isMine ? "text-white" : "text-gray-900"
          }`}
        >
          {attachment.filename}
        </a>
        <dl className={`mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] ${isMine ? "text-gray-200" : "text-gray-500"}`}>
          {attachment.uploader_name && (
            <>
              <dt>Uploaded by</dt>
              <dd className={isMine ? "text-gray-100" : "text-gray-700"}>{attachment.uploader_name}</dd>
            </>
          )}
          {attachment.matter_name && (
            <>
              <dt>Matter</dt>
              <dd className={`truncate ${isMine ? "text-gray-100" : "text-gray-700"}`}>{attachment.matter_name}</dd>
            </>
          )}
          {attachment.version != null && (
            <>
              <dt>Version</dt>
              <dd className={isMine ? "text-gray-100" : "text-gray-700"}>v{attachment.version}</dd>
            </>
          )}
        </dl>
        {preview && !attachment.mime_type?.startsWith("image/") && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className={`mt-2 inline-flex text-[11px] font-medium ${isMine ? "text-gray-100" : "text-gray-700"}`}
          >
            Open preview →
          </a>
        )}
      </div>
    </div>
  );
}
