/** Session-scoped Firm Chat diagnostics (developer panel). */

export type FirmChatDiagnostics = {
  wsState: "disconnected" | "connecting" | "connected" | "error";
  wsLatencyMs: number | null;
  messagesSent: number;
  messagesReceived: number;
  rateLimit429Count: number;
  last429Source: string;
  last429At: number | null;
  limiterRule: string;
  reconnects: number;
  lastEventType: string;
  updatedAt: number;
};

const KEY = "legalease_firm_chat_diag";

const defaultState = (): FirmChatDiagnostics => ({
  wsState: "disconnected",
  wsLatencyMs: null,
  messagesSent: 0,
  messagesReceived: 0,
  rateLimit429Count: 0,
  last429Source: "",
  last429At: null,
  limiterRule: "",
  reconnects: 0,
  lastEventType: "",
  updatedAt: Date.now(),
});

export function getFirmChatDiagnostics(): FirmChatDiagnostics {
  if (typeof window === "undefined") return defaultState();
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return defaultState();
    return { ...defaultState(), ...JSON.parse(raw) };
  } catch {
    return defaultState();
  }
}

export function patchFirmChatDiagnostics(patch: Partial<FirmChatDiagnostics>) {
  if (typeof window === "undefined") return;
  const next = { ...getFirmChatDiagnostics(), ...patch, updatedAt: Date.now() };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore quota */
  }
  window.dispatchEvent(new CustomEvent("firm-chat-diag"));
}

export function recordFirmChat429(source: string, limiterRule = "") {
  const d = getFirmChatDiagnostics();
  patchFirmChatDiagnostics({
    rateLimit429Count: d.rateLimit429Count + 1,
    last429Source: source,
    last429At: Date.now(),
    limiterRule: limiterRule || d.limiterRule,
  });
}

export function clearFirmChat429() {
  patchFirmChatDiagnostics({
    rateLimit429Count: 0,
    last429Source: "",
    last429At: null,
    limiterRule: "",
  });
}
