/** Lightweight STT debug logger (NDJSON to ingest + optional file). */

type LogPayload = {
  message: string;
  data?: Record<string, unknown>;
  hypothesisId?: string;
};

const SESSION = "cf6ca9";
const ENDPOINT = "http://127.0.0.1:7875/ingest/c3dd2ac2-3927-41bb-8511-dee0b46f3309";

export function speechLog(location: string, payload: LogPayload) {
  const entry = {
    sessionId: SESSION,
    location,
    message: payload.message,
    data: payload.data ?? {},
    hypothesisId: payload.hypothesisId ?? "stt",
    timestamp: Date.now(),
  };
  if (typeof window !== "undefined" && localStorage.getItem("legalease_speech_debug") === "1") {
    console.debug("[STT]", payload.message, payload.data);
  }
  fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": SESSION },
    body: JSON.stringify(entry),
  }).catch(() => {});
}
