"use client";

import Link from "next/link";

type ChatItem = {
  thread_id?: string;
  question?: string;
  preview?: string;
  mode?: string;
  created_at?: string;
};

type DocItem = {
  id?: string;
  filename?: string;
  pages?: number;
  uploaded_at?: string;
};

function formatWhen(iso?: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = Date.now();
    const diff = now - d.getTime();
    if (diff < 60_000) return "Just now";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function RecentActivityPanel({
  chats,
  documents,
}: {
  chats: ChatItem[];
  documents: DocItem[];
}) {
  return (
    <div className="border rounded-2xl bg-white overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-slate-100">
        <h3 className="text-sm font-semibold text-navy m-0">Recent activity</h3>
        <p className="text-xs text-slate-500 m-0 mt-0.5">Latest chats and uploads</p>
      </div>

      <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        <div className="p-4">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Conversations
          </p>
          {chats.length === 0 ? (
            <p className="text-sm text-slate-500 m-0">
              No chats yet.{" "}
              <Link href="/" className="text-blue-600 hover:underline">
                Start one
              </Link>
            </p>
          ) : (
            <ul className="space-y-2 m-0 p-0 list-none">
              {chats.slice(0, 5).map((c) => {
                const tid = c.thread_id || "";
                return (
                  <li key={tid || c.question}>
                    <Link
                      href={tid ? `/?thread=${encodeURIComponent(tid)}` : "/"}
                      className="block rounded-lg px-2 py-2 -mx-2 hover:bg-slate-50 no-underline"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium text-navy m-0 truncate flex-1">
                          {c.question || "Chat"}
                        </p>
                        <span className="text-[0.65rem] text-slate-400 shrink-0">
                          {formatWhen(c.created_at)}
                        </span>
                      </div>
                      {c.mode ? (
                        <span className="inline-block mt-1 text-[0.62rem] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                          {c.mode.replace(/_/g, " ")}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="p-4">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Documents
          </p>
          {documents.length === 0 ? (
            <p className="text-sm text-slate-500 m-0">
              No uploads yet.{" "}
              <Link href="/documents" className="text-blue-600 hover:underline">
                Upload PDFs
              </Link>
            </p>
          ) : (
            <ul className="space-y-2 m-0 p-0 list-none">
              {documents.slice(0, 5).map((d) => (
                <li key={d.id || d.filename}>
                  <Link
                    href="/documents"
                    className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 -mx-2 hover:bg-slate-50 no-underline"
                  >
                    <span className="text-sm text-navy truncate">{d.filename}</span>
                    <span className="text-[0.65rem] text-slate-400 shrink-0">
                      {d.pages != null ? `${d.pages} pg` : formatWhen(d.uploaded_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
