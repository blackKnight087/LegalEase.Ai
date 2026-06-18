"use client";

import { useCallback, useRef, useState } from "react";
import * as api from "@/lib/api";
import MatterChatHistory from "@/components/matters/MatterChatHistory";
import MarkdownBox from "@/components/ui/MarkdownBox";

const MODES: { id: string; label: string }[] = [
  { id: "matter_only", label: "Matter only" },
  { id: "hybrid", label: "Matter + law" },
  { id: "chronology", label: "Chronology" },
  { id: "hearing_prep", label: "Hearing prep" },
  { id: "evidence", label: "Evidence analysis" },
];

type Msg = { role: string; content: string };

export default function MatterAIPanel({ matterId }: { matterId: string }) {
  const [matterMode, setMatterMode] = useState("matter_only");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<Array<Record<string, unknown>>>([]);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setErr("");
    setBusy(true);
    setInput("");
    const userMsg: Msg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    let assistant = "";
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      await api.streamChat(
        {
          message: text,
          mode: "knowledge_base",
          lang: "English",
          matter_id: matterId,
          matter_mode: matterMode,
          session_id: sessionId,
          history: messages.slice(-12),
        },
        (token) => {
          assistant += token;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { role: "assistant", content: assistant };
            return next;
          });
        },
        (meta) => {
          if (meta.session_id) setSessionId(String(meta.session_id));
        },
        (msg) => setErr(msg),
        undefined,
        abortRef.current.signal
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setErr(e instanceof Error ? e.message : "Chat failed");
      }
    } finally {
      setBusy(false);
    }
  }, [input, busy, matterId, matterMode, messages, sessionId]);

  const runSearch = async () => {
    if (!searchQ.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.searchMatter(matterId, searchQ);
      setSearchHits(r.results || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <MatterChatHistory matterId={matterId} />

      <section className="rounded-xl border bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-navy m-0">Matter AI</h3>
        <p className="text-xs text-slate-500 m-0">
          Answers are scoped to this matter&apos;s uploaded documents only (mode: Matter only).
        </p>
        <div className="flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMatterMode(m.id)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${
                matterMode === m.id
                  ? "bg-navy text-white border-navy"
                  : "bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="max-h-72 overflow-y-auto space-y-3 border rounded-lg p-3 bg-slate-50 min-h-[120px]">
          {messages.length === 0 && (
            <p className="text-xs text-slate-500 m-0">
              Ask: &quot;Summarize murder case&quot;, &quot;Who is accused?&quot;, &quot;What evidence
              exists?&quot;
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`text-sm ${m.role === "user" ? "text-right" : "text-left"}`}
            >
              <span className="text-[0.65rem] uppercase text-slate-400 block mb-0.5">
                {m.role}
              </span>
              {m.role === "assistant" ? (
                <div className="text-left bg-white border rounded-lg p-2">
                  <MarkdownBox content={m.content || (busy ? "…" : "")} />
                </div>
              ) : (
                <span className="inline-block bg-navy text-white px-2 py-1 rounded-lg">
                  {m.content}
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="Ask about this matter…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            disabled={busy}
          />
          <button
            type="button"
            disabled={busy || !input.trim()}
            onClick={() => void send()}
            className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
        {err && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
            {err}
          </p>
        )}
      </section>

      <section className="rounded-xl border bg-white p-4 space-y-2">
        <h3 className="text-sm font-semibold text-navy m-0">Search in matter</h3>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="Search documents…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void runSearch()}
          />
          <button
            type="button"
            disabled={busy || !searchQ.trim()}
            onClick={() => void runSearch()}
            className="px-3 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            Search
          </button>
        </div>
        <ul className="space-y-2 text-xs max-h-40 overflow-y-auto m-0 p-0 list-none">
          {searchHits.map((h, i) => (
            <li key={i} className="p-2 bg-slate-50 rounded border">
              {h.filename ? (
                <span className="font-semibold text-navy block">{String(h.filename)}</span>
              ) : null}
              {String(h.content || "").slice(0, 280)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
