"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { getFirmChatDiagnostics, type FirmChatDiagnostics } from "@/lib/firmChatDiagnostics";

export default function FirmChatDebugPanel() {
  const [diag, setDiag] = useState<FirmChatDiagnostics>(getFirmChatDiagnostics);
  const [server, setServer] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const refresh = () => setDiag(getFirmChatDiagnostics());
    window.addEventListener("firm-chat-diag", refresh);
    return () => window.removeEventListener("firm-chat-diag", refresh);
  }, []);

  useEffect(() => {
    void api.fetchCollabRealtimeDebug().then(setServer).catch(() => setServer(null));
  }, [diag.updatedAt]);

  if (process.env.NEXT_PUBLIC_FIRM_CHAT_DEBUG !== "1") {
    return null;
  }

  return (
    <details className="mt-2 rounded-lg border border-dashed border-slate-300 bg-slate-50/80 text-[10px] text-slate-600">
      <summary className="cursor-pointer px-3 py-2 font-semibold uppercase tracking-wide">
        Firm Chat diagnostics
      </summary>
      <div className="px-3 pb-3 grid gap-2 sm:grid-cols-2">
        <div>
          <p className="font-semibold text-slate-700 m-0 mb-1">WebSocket</p>
          <ul className="m-0 pl-4 space-y-0.5">
            <li>State: {diag.wsState}</li>
            <li>Latency: {diag.wsLatencyMs != null ? `${diag.wsLatencyMs}ms` : "—"}</li>
            <li>Reconnects: {diag.reconnects}</li>
            <li>Last event: {diag.lastEventType || "—"}</li>
          </ul>
        </div>
        <div>
          <p className="font-semibold text-slate-700 m-0 mb-1">Traffic</p>
          <ul className="m-0 pl-4 space-y-0.5">
            <li>Messages received (WS): {diag.messagesReceived}</li>
            <li>Messages sent: {diag.messagesSent}</li>
            <li>429 count: {diag.rateLimit429Count}</li>
            <li>Limiter source: {diag.last429Source || "—"}</li>
            <li>Limiter rule: {diag.limiterRule || server?.rate_limits ? "see server" : "—"}</li>
          </ul>
        </div>
        {server && (
          <div className="sm:col-span-2 font-mono text-[9px] overflow-x-auto">
            <pre className="m-0 whitespace-pre-wrap">
              {JSON.stringify(server, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}
