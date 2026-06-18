"use client";

import { useState } from "react";

type Message = { role: "user" | "assistant"; text: string };

const SUGGESTIONS = [
  "Add a confidentiality clause",
  "Add force majeure clause",
  "Rewrite for Indian jurisdiction",
  "Add arbitration clause",
  "Draft stronger indemnity for Party A",
  "Convert rough notes into formal petition language",
  "Generate clean execution page",
  "Explain risk in the selected clause",
];

type Props = {
  busy: boolean;
  onSend: (instruction: string) => Promise<string | null>;
  onApply: (html: string) => void;
};

export default function CopilotChatPanel({ busy, onSend, onApply }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setMessages((m) => [...m, { role: "user", text: trimmed }]);
    setInput("");
    const result = await onSend(trimmed);
    if (result) {
      setMessages((m) => [...m, { role: "assistant", text: result.slice(0, 2000) }]);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-2 py-2 border-b">
        <h3 className="text-xs font-semibold text-navy">AI Copilot</h3>
        <p className="text-[10px] text-slate-500 mt-0.5">Ask anything about this document.</p>
      </div>
      <div className="flex-1 overflow-y-auto le-scroll p-2 space-y-2 min-h-[8rem]">
        {messages.length === 0 && (
          <div className="text-[10px] text-slate-500 space-y-2">
            <p>Try:</p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                className="block w-full text-left px-2 py-1 border rounded-lg bg-white hover:bg-slate-50 text-navy"
                onClick={() => send(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`rounded-lg px-2 py-1.5 text-xs ${
              msg.role === "user" ? "bg-navy text-white ml-4" : "bg-white border mr-4"
            }`}
          >
            <p className="whitespace-pre-wrap line-clamp-[12]">{msg.text.replace(/<[^>]+>/g, " ").slice(0, 800)}</p>
            {msg.role === "assistant" && (
              <button
                type="button"
                className="mt-1 underline text-navy"
                onClick={() => onApply(msg.text)}
              >
                Insert into document
              </button>
            )}
          </div>
        ))}
      </div>
      <form
        className="p-2 border-t flex gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="flex-1 border rounded-lg px-2 py-1.5 text-xs"
          placeholder="Ask Copilot…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
