import { uiLangToCode } from "./speechLang";
import { backendUnreachableMessage } from "./runtimeEnv";

function normalizeApiBase(raw: string): string {
  const trimmed = raw.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    try {
      const u = new URL(trimmed);
      if (u.hostname === "localhost") u.hostname = "127.0.0.1";
      return u.toString().replace(/\/$/, "");
    } catch {
      return trimmed;
    }
  }
  return trimmed.replace(/localhost/gi, "127.0.0.1");
}

const SERVER_API_BASE = normalizeApiBase(
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
);

/** Browser uses same-origin proxy (next.config rewrites); SSR uses direct backend URL. */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    return "";
  }
  return SERVER_API_BASE;
}

export const API_BASE = SERVER_API_BASE;

/** Primary + localhost/127.0.0.1 alternate for Windows dev (server-side / fallback). */
export function apiBaseCandidates(): string[] {
  const browserBase = typeof window !== "undefined" ? getApiBase() : "";
  if (browserBase === "") {
    return [""];
  }
  const primary = SERVER_API_BASE;
  const alt = primary.includes("127.0.0.1")
    ? primary.replace("127.0.0.1", "localhost")
    : primary.replace(/localhost/gi, "127.0.0.1");
  return [...new Set([primary, alt].filter(Boolean))];
}

const DEFAULT_TIMEOUT_MS = 30000;
/** Align with next.config.js proxyTimeout for prep packs and evidence scans. */
const LONG_TIMEOUT_MS = 180_000;
/** Chat stream absolute cap — matches backend LLM_LEGAL_TIMEOUT_SEC. */
const STREAM_TIMEOUT_MS = 180_000;
const PING_TIMEOUT_MS = 5000;
const MAX_RETRIES = 3;
const RETRY_BASE_MS = 400;

function isRetryableError(err: unknown): boolean {
  if (!(err instanceof Error)) return true;
  const m = err.message.toLowerCase();
  return (
    err.name === "AbortError" ||
    m.includes("connection failed") ||
    m.includes("cannot reach api") ||
    m.includes("failed to fetch") ||
    m.includes("network") ||
    m.includes("load failed")
  );
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Read response body once — avoids "body stream already read" when JSON parse fails. */
async function readResponseError(
  res: Response,
  fallback = "Request failed"
): Promise<string> {
  const text = await res.text();
  if (!text.trim()) {
    return fallback;
  }
  try {
    const err = JSON.parse(text) as {
      detail?: string | Array<{ msg?: string }>;
      message?: string;
    };
    const detail = err.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0];
      return (
        (typeof first === "object" && first?.msg) ||
        (typeof first === "string" ? first : "") ||
        fallback
      );
    }
    return err.message || text.slice(0, 500);
  } catch {
    return text.slice(0, 500);
  }
}

async function fetchWithTimeout(
  path: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${getApiBase()}${path}`, {
      ...options,
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(backendUnreachableMessage());
    }
    throw new Error(backendUnreachableMessage());
  } finally {
    clearTimeout(timer);
  }
}

async function fetchWithRetry(
  path: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
  retries = MAX_RETRIES
): Promise<Response> {
  let lastErr: unknown;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await fetchWithTimeout(path, options, timeoutMs);
      if (res.status === 429 && attempt < retries - 1) {
        await sleep(1500 * (attempt + 1));
        continue;
      }
      if (res.status >= 500 && attempt < retries - 1) {
        await sleep(RETRY_BASE_MS * (attempt + 1));
        continue;
      }
      return res;
    } catch (err) {
      lastErr = err;
      if (!isRetryableError(err) || attempt >= retries - 1) break;
      await sleep(RETRY_BASE_MS * (attempt + 1));
    }
  }
  throw lastErr instanceof Error
    ? lastErr
    : new Error(`Connection failed (${API_BASE})`);
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("legalease_token");
}

/** SSE URL for collaboration room stream (EventSource cannot send Authorization header). */
export function collabStreamUrl(roomId: string): string {
  const token = getToken();
  const base = getApiBase();
  const path = `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/stream`;
  const q = token ? `?access_token=${encodeURIComponent(token)}` : "";
  return base ? `${base}${path}${q}` : `${path}${q}`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
  retries = MAX_RETRIES
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const res = await fetchWithRetry(path, { ...options, headers }, timeoutMs, retries);
  if (!res.ok) {
    throw new Error(
      await readResponseError(res, `HTTP ${res.status}: ${res.statusText}`)
    );
  }
  return res.json() as Promise<T>;
}

/** Lightweight liveness — tries 127.0.0.1 and localhost; survives background indexing. */
export async function pingApiLive(timeoutMs = PING_TIMEOUT_MS) {
  let lastErr: unknown;
  for (const base of apiBaseCandidates()) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${base}/api/v1/health/live`, {
        signal: controller.signal,
        cache: "no-store",
      });
      if (res.ok) {
        return (await res.json()) as { status: string; live?: boolean };
      }
      lastErr = new Error(`API live check failed (${res.status}) at ${base}`);
    } catch (err) {
      lastErr = err;
    } finally {
      clearTimeout(timer);
    }
  }
  if (lastErr instanceof Error && lastErr.name === "AbortError") {
    throw new Error(backendUnreachableMessage());
  }
  throw new Error(backendUnreachableMessage());
}

export async function pingApi() {
  return pingApiLive();
}

export async function login(username: string, password: string) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const res = await fetchWithRetry(
    "/api/v1/auth/login",
    { method: "POST", headers, body: JSON.stringify({ username, password }) },
    15000
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Login failed");
  }
  return res.json() as Promise<{ token: string; user: Record<string, unknown> }>;
}

export async function register(
  username: string,
  password: string,
  confirm_password: string,
  accept_terms = true,
  email = ""
) {
  return apiFetch<{ token: string; user: Record<string, unknown> }>(
    "/api/v1/auth/register",
    {
      method: "POST",
      body: JSON.stringify({ username, password, confirm_password, accept_terms, email }),
    }
  );
}

export async function requestPasswordReset(username: string) {
  return apiFetch<{ ok: boolean; message?: string }>("/api/v1/account/forgot-password", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export async function resetPassword(
  token: string,
  password: string,
  confirm_password: string
) {
  return apiFetch<{ ok: boolean; message?: string }>(
    `/api/v1/account/reset-password/${encodeURIComponent(token)}`,
    {
      method: "POST",
      body: JSON.stringify({ password, confirm_password }),
    }
  );
}

export type OnboardingStep = {
  id: string;
  title: string;
  done: boolean;
  href?: string;
};

export type OnboardingState = {
  steps: OnboardingStep[];
  completed: number;
  total: number;
  percent: number;
  dismissed: boolean;
  complete: boolean;
};

export async function fetchOnboarding() {
  return apiFetch<OnboardingState>("/api/v1/account/onboarding");
}

export async function dismissOnboarding() {
  return apiFetch<{ ok: boolean }>("/api/v1/account/onboarding/dismiss", {
    method: "POST",
  });
}

export async function exportAccountZip(): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithRetry("/api/v1/account/export", { headers }, 120000);
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Export failed"));
  }
  return res.blob();
}

export async function deleteAccount(confirm_username: string, password: string) {
  return apiFetch<{ ok: boolean }>("/api/v1/account", {
    method: "DELETE",
    body: JSON.stringify({ confirm_username, password }),
  });
}

export async function openBillingPortal() {
  const r = await apiFetch<{ portal_url: string }>("/api/v1/subscriptions/portal");
  if (r.portal_url) window.location.href = r.portal_url;
  return r;
}

export async function fetchMyOrg() {
  return apiFetch<{
    org: Record<string, unknown>;
    members: Array<Record<string, unknown>>;
    member_count: number;
  }>("/api/v1/orgs/me");
}

export async function inviteOrgMember(email: string, role = "member") {
  return apiFetch<{ ok: boolean; invite: Record<string, unknown> }>("/api/v1/orgs/invite", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function fetchOrgInvites() {
  return apiFetch<{ invites: Array<Record<string, unknown>> }>("/api/v1/orgs/invites");
}

export async function adminListUsers(q = "") {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return apiFetch<{ users: Array<Record<string, unknown>> }>(`/api/v1/admin/users${qs}`);
}

export async function adminAudit(limit = 100) {
  return apiFetch<{ events: Array<Record<string, unknown>> }>(
    `/api/v1/admin/audit?limit=${limit}`
  );
}

export async function adminUsage() {
  return apiFetch<Record<string, number>>("/api/v1/admin/usage");
}

export async function adminHealth() {
  return apiFetch<Record<string, string>>("/api/v1/admin/health");
}

export async function adminSuspend(userId: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/admin/users/${encodeURIComponent(userId)}/suspend`, {
    method: "POST",
  });
}

export async function adminUnsuspend(userId: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/unsuspend`,
    { method: "POST" }
  );
}

export async function adminSetPlan(userId: string, plan: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/plan`,
    { method: "POST", body: JSON.stringify({ plan }) }
  );
}

export async function getMe() {
  return apiFetch<{ user: Record<string, unknown> }>(
    "/api/v1/auth/me",
    {},
    8000,
    1
  );
}

export async function getHealthPublic() {
  const res = await fetchWithRetry("/api/v1/health/public", {}, 8000, 2);
  if (!res.ok) throw new Error("Health check failed");
  return res.json() as Promise<{ llm_ready: boolean; llm_label?: string }>;
}

/** Fast LLM-only probe — does not load embeddings (safe during indexing). */
export async function getHealthLlm() {
  const res = await fetchWithRetry("/api/v1/health/llm", {}, 6000, 2);
  if (!res.ok) throw new Error("LLM health check failed");
  return res.json() as Promise<{
    llm_ready: boolean;
    llm_label?: string;
    backend?: string;
    model?: string;
  }>;
}

export async function getHealth() {
  return apiFetch<{
    llm_ready: boolean;
    vector_db_ready: boolean;
    indexed_docs: number;
    chunks: number;
  }>("/api/v1/health");
}

export async function getChatHistory(limit = 20, matterId = "") {
  const mq = matterId ? `&matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{ sessions: Array<Record<string, string>> }>(
    `/api/v1/sessions/history?limit=${limit}${mq}`
  );
}

export async function getChatThread(threadId: string) {
  return apiFetch<{
    thread_id: string;
    mode: string;
    language: string;
    messages: ChatMessage[];
    matter_id?: string;
  }>(`/api/v1/sessions/threads/${encodeURIComponent(threadId)}`);
}

export async function deleteChatThread(threadId: string) {
  return apiFetch<{ status: string; thread_id: string; deleted_rows: number }>(
    `/api/v1/sessions/threads/${encodeURIComponent(threadId)}`,
    { method: "DELETE" }
  );
}

export async function getThreadAttachment(threadId: string) {
  return apiFetch<{
    has_attachment: boolean;
    filename?: string;
    preview?: string;
    char_count?: number;
  }>(`/api/v1/sessions/threads/${encodeURIComponent(threadId)}/attachment`);
}

export async function uploadThreadAttachment(
  threadId: string,
  file: File,
  ocr = false
) {
  const fd = new FormData();
  fd.append("file", file);
  const token = getToken();
  const res = await fetchWithRetry(
    `/api/v1/sessions/threads/${encodeURIComponent(threadId)}/attachment?ocr=${ocr ? "1" : "0"}`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    },
    300000,
    2
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Attachment upload failed"));
  }
  return res.json() as Promise<{
    status: string;
    filename: string;
    char_count: number;
    preview: string;
    method: string;
    message: string;
  }>;
}

export async function removeThreadAttachment(threadId: string) {
  return apiFetch<{ status: string }>(
    `/api/v1/sessions/threads/${encodeURIComponent(threadId)}/attachment`,
    { method: "DELETE" }
  );
}

export type ChatMessage = { role: string; content: string };

export async function sendChat(body: {
  message: string;
  mode: string;
  lang: string;
  session_id?: string;
  matter_id?: string;
  history: ChatMessage[];
  attachment?: Record<string, unknown> | null;
}) {
  return apiFetch<{
    content: string;
    similar_cases: Record<string, unknown>[];
    web_sources: Record<string, unknown>[];
    follow_ups: string[];
    session_id: string;
  }>("/api/v1/chat", { method: "POST", body: JSON.stringify(body) });
}

export async function streamChat(
  body: {
    message: string;
    mode: string;
    lang: string;
    session_id?: string;
    thread_id?: string;
    matter_id?: string;
    matter_mode?: string;
    history: ChatMessage[];
    attachment?: Record<string, unknown> | null;
  },
  onToken: (text: string) => void,
  onMeta: (meta: Record<string, unknown>) => void,
  onError: (msg: string) => void,
  onStatus?: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const streamAbort = new AbortController();
  const timeoutId = setTimeout(() => streamAbort.abort(), STREAM_TIMEOUT_MS);
  if (signal) {
    signal.addEventListener("abort", () => streamAbort.abort(), { once: true });
  }
  let res: Response;
  try {
    res = await fetch(`${getApiBase()}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: streamAbort.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === "AbortError") {
      if (!signal?.aborted) {
        onError("Response timed out. Try a shorter question or check Ollama.");
      }
      return;
    }
    throw err;
  }
  clearTimeout(timeoutId);
  if (!res.ok || !res.body) {
    const err = await res.text();
    onError(err || `HTTP ${res.status}`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let gotMeta = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") {
          if (!gotMeta) {
            gotMeta = true;
            onMeta({
              type: "meta",
              follow_ups: [],
              similar_cases: [],
              web_sources: [],
            });
          }
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.type === "token" && parsed.content) {
            const t = String(parsed.content);
            if (t.trim() !== "{}" && t.trim() !== "[]") onToken(t);
          }
          if (parsed.type === "status" && parsed.content) {
            onStatus?.(String(parsed.content));
          }
          if (parsed.type === "meta") {
            gotMeta = true;
            onMeta(parsed);
          }
          if (parsed.type === "error") {
            const msg = String(parsed.content || "Chat failed");
            if (!/^\[Errno 22\]/i.test(msg)) {
              onError(msg);
            } else {
              onStatus?.("Open Law — retrying search…");
            }
          }
        } catch {
          /* ignore */
        }
      }
    }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") return;
    throw err;
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* ignore */
    }
  }
  if (!gotMeta) {
    onMeta({ type: "meta", follow_ups: [], similar_cases: [], web_sources: [] });
  }
}

export type DocumentsListResponse = {
  documents: Array<{
    id: string;
    filename: string;
    pages: number;
    uploaded_at?: string;
  }>;
  count: number;
  membership: string;
  free_limit: number;
  max_upload_mb?: number;
};

export async function fetchDocuments() {
  return apiFetch<DocumentsListResponse>("/api/v1/documents");
}

export async function syncKbStatus() {
  return apiFetch<{
    ok: boolean;
    fixed?: boolean;
    total_chunks: number;
    status: string;
  }>("/api/v1/documents/kb/sync-status", { method: "POST" }, 30000, 1);
}

/** Shown when KB health is loading or failed — keeps the green status panel visible. */
export const EMPTY_KB_HEALTH = {
  status: "loading",
  healthy: false,
  ready_for_kb_query: false,
  documents: 0,
  chunks: 0,
  index_exists: false,
  index_vectors: 0,
  faiss_chunks: 0,
  faiss_chunks_total: 0,
  index_scope: "unlinked",
  index_scope_label: "unlinked (global KB)",
  embeddings_ok: false,
  embeddings: { ready: false, loading: true, model: "", error: "" },
  issues: [] as Array<{ severity: string; message: string; fix?: string; code?: string }>,
} as const;

export type KbHealthSnapshot = typeof EMPTY_KB_HEALTH & {
  recommended_actions?: string[];
};

export async function fetchKbHealth(matterId = "") {
  const mq = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{
    status: string;
    healthy?: boolean;
    ready_for_kb_query?: boolean;
    documents: number;
    chunks: number;
    index_exists: boolean;
    index_vectors: number;
    faiss_chunks?: number;
    faiss_chunks_total?: number;
    index_scope?: string;
    index_scope_label?: string;
    embeddings_ok?: boolean;
    embeddings?: {
      ready: boolean;
      loading?: boolean;
      error?: string;
      model?: string;
      device?: string;
    };
    issues?: Array<{ severity: string; code?: string; message: string; fix?: string }>;
    recommended_actions?: string[];
    index_scopes?: Array<{ scope: string; faiss_chunks: number; index_exists: boolean; label?: string }>;
    sla?: Record<string, unknown>;
    health?: Record<string, unknown>;
  }>(`/api/v1/documents/kb/health${mq}`, {}, 20000, 1);
}

export async function kbDebugQuery(query: string, sessionId?: string) {
  const params = new URLSearchParams({ q: query });
  if (sessionId) params.set("session_id", sessionId);
  return apiFetch<Record<string, unknown>>(
    `/api/v1/kb/debug-query?${params.toString()}`,
    {},
    60000,
    1
  );
}

export type KbSmokeTestResult = {
  ok: boolean;
  kb_pass?: boolean;
  training_pass?: boolean | null;
  skipped?: boolean;
  reason?: string;
  index_path?: string;
  index_scope?: string;
  index_scope_label?: string;
  faiss_vectors?: number;
  passed?: number;
  failed?: number;
  total_latency_ms?: number;
  error?: string;
  embeddings_ok?: boolean;
  scheduler?: {
    memory?: { percent?: number; available_mb?: number };
    low_priority_paused?: boolean;
  };
  queries?: Array<{
    id: string;
    query: string;
    status: string;
    found?: boolean;
    chunk_count?: number;
    latency_ms?: number;
    answer_preview?: string;
    reason?: string;
  }>;
};

export async function runKbSmokeTest(matterId = "") {
  const mq = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<KbSmokeTestResult>(
    `/api/v1/documents/kb/smoke-test${mq}`,
    { method: "POST" },
    120000
  );
}

export async function autoReindexKb() {
  return apiFetch<{
    ok: boolean;
    reindexed: boolean;
    message?: string;
    stale?: unknown[];
    index_job_id?: string;
  }>("/api/v1/documents/kb/reindex-auto", { method: "POST" }, 60000);
}

export type IndexJobStatus = {
  job_id: string;
  status: string;
  message?: string;
  ok?: boolean;
  indexing_ok?: boolean;
  chunks_added?: number;
  filename?: string;
};

export async function fetchIndexJob(jobId: string): Promise<IndexJobStatus> {
  return apiFetch<IndexJobStatus>(
    `/api/v1/documents/jobs/${encodeURIComponent(jobId)}`,
    {},
    15000,
    1
  );
}

export async function waitForIndexJob(
  jobId: string,
  onProgress?: (msg: string) => void,
  maxMs = 900000
): Promise<IndexJobStatus> {
  const start = Date.now();
  let errors = 0;
  while (Date.now() - start < maxMs) {
    try {
      const row = await fetchIndexJob(jobId);
      errors = 0;
      if (row.message && onProgress) onProgress(row.message);
      if (row.status === "completed" || row.status === "failed") return row;
    } catch {
      errors += 1;
      if (onProgress) {
        onProgress(
          errors < 5
            ? "API busy while indexing — still working in background…"
            : "Could not reach job status — indexing may still be running."
        );
      }
    }
    await sleep(5000);
  }
  throw new Error("Indexing timed out — check Documents page or retry Re-index.");
}

export async function fetchEmbeddingHealth() {
  return apiFetch<{
    ready: boolean;
    loading?: boolean;
    model?: string;
    device?: string;
    error?: string;
  }>("/api/v1/health/embeddings", {}, 8000, 1);
}

export async function uploadDocument(file: File, ocr = true, matterId = "") {
  const fd = new FormData();
  fd.append("file", file);
  const token = getToken();
  const matterQ = matterId ? `&matter_id=${encodeURIComponent(matterId)}` : "";
  const uploadTimeoutMs = 900000;
  const res = await fetchWithRetry(
    `/api/v1/documents/upload?ocr=${ocr ? "1" : "0"}${matterQ}`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    },
    uploadTimeoutMs,
    2
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Upload failed"));
  }
  return res.json() as Promise<{
    status: string;
    document_name: string;
    pages: number;
    chunks_added: number;
    indexed: boolean;
    indexing_ok?: boolean;
    index_vectors?: number;
    index_scope?: string;
    error_code?: string;
    severity?: string;
    user_action?: string;
    index_message?: string;
    index_job_id?: string;
    indexing_async?: boolean;
  }>;
}

export async function reindexDocuments(ocr = false, matterId = "") {
  const mq = matterId ? `&matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{
    status: string;
    indexed: boolean;
    chunks_added: number;
    message?: string;
    index_job_id?: string;
  }>(`/api/v1/documents/index?ocr=${ocr ? "1" : "0"}${mq}`, { method: "POST" }, 15000, 1);
}

export async function deleteDocument(id: string) {
  return apiFetch<{ status: string }>(`/api/v1/documents/${id}`, {
    method: "DELETE",
  });
}

export async function fetchDocTimeline(id: string) {
  return apiFetch<{ events: Array<{ date: string; text: string; page?: number }> }>(
    `/api/v1/documents/${id}/timeline`
  );
}

export async function fetchDocEntities(id: string) {
  return apiFetch<{
    entities: Record<string, string> | null;
  }>(`/api/v1/documents/${id}/entities`);
}

export async function ocrImage(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const token = getToken();
  const res = await fetchWithRetry(
    "/api/v1/ocr",
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    },
    120000,
    2
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ---------- Legal tools (legacy /api routes) ----------

export async function ipcConvert(section: string) {
  return apiFetch<Record<string, unknown>>("/api/tools/ipc-bns/convert", {
    method: "POST",
    body: JSON.stringify({ section }),
  });
}

export async function ipcBulk(sections: string[]) {
  return apiFetch<{ results: Record<string, unknown>[] }>("/api/tools/ipc-bns/bulk", {
    method: "POST",
    body: JSON.stringify({ sections }),
  });
}

export async function ipcCategories() {
  return apiFetch<{ categories: string[] }>("/api/tools/ipc-bns/categories");
}

export async function ipcCategory(category: string) {
  return apiFetch<{ sections: unknown }>(`/api/tools/ipc-bns/category/${category}`);
}

// ---------- IPC-BNS Intelligence Engine V3 (deterministic dataset) ----------

export async function ipcBnsV3Meta() {
  return apiFetch<Record<string, unknown>>("/api/v1/ipc-bns/v3/meta");
}

export async function ipcBnsV3Search(q: string) {
  return apiFetch<{ results: Array<Record<string, unknown>>; count: number }>(
    `/api/v1/ipc-bns/v3/search?q=${encodeURIComponent(q)}`
  );
}

export async function ipcBnsV3LookupIpc(section: string, matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<Record<string, unknown>>(`/api/v1/ipc-bns/v3/ipc/${encodeURIComponent(section)}${q}`);
}

export async function ipcBnsV3LookupBns(section: string, matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<Record<string, unknown>>(`/api/v1/ipc-bns/v3/bns/${encodeURIComponent(section)}${q}`);
}

export async function ipcBnsV3Compare(ipcSection: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/ipc-bns/v3/compare/${encodeURIComponent(ipcSection)}`);
}

export async function ipcBnsV3Bulk(sections: string[], matterId = "") {
  return apiFetch<Record<string, unknown>>("/api/v1/ipc-bns/v3/bulk", {
    method: "POST",
    body: JSON.stringify({ sections, matter_id: matterId }),
  });
}

export async function ipcBnsV3UploadDocument(file: File, caseName = "", matterId = "") {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams();
  if (caseName) params.set("case_name", caseName);
  if (matterId) params.set("matter_id", matterId);
  const qs = params.toString() ? `?${params}` : "";
  const token = getToken();
  const res = await fetch(`${getApiBase()}/api/v1/ipc-bns/v3/document/upload${qs}`, {
    method: "POST",
    body: form,
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(await readResponseError(res, "Upload failed"));
  return res.json() as Promise<Record<string, unknown>>;
}

export async function ipcBnsV3MatterMigration(matterId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/ipc-bns/v3/matters/${encodeURIComponent(matterId)}/migration`);
}

// ---------- Legal Conversion (IPC↔BNS — official dataset) ----------

const IPC_BNS_NOT_FOUND =
  "Official mapping not found. Manual legal verification required.";

/** Normalize v3 / legacy lookup payloads for Legal Tools UI. */
export function normalizeIpcBnsConversion(
  raw: Record<string, unknown>
): Record<string, unknown> {
  const found = Boolean(raw.found) || raw.status === "mapped";
  return {
    ...raw,
    found,
    old_section: raw.old_section ?? raw.ipc_key,
    new_section: raw.new_section ?? raw.bns_key,
    old_section_label: raw.old_section_label ?? raw.ipc_section,
    new_section_label: raw.new_section_label ?? raw.bns_section,
    old_title: raw.old_title ?? raw.offence_title,
    new_title: raw.new_title ?? raw.short_description ?? raw.description,
    mapping_type: raw.mapping_type ?? raw.mapping_status,
    status_label: raw.status_label ?? (found ? "Active" : undefined),
    message: found ? raw.message : raw.message ?? IPC_BNS_NOT_FOUND,
  };
}

export async function legalConversionMeta() {
  try {
    return await apiFetch<Record<string, unknown>>("/api/v1/legal-conversion/meta");
  } catch {
    return ipcBnsV3Meta();
  }
}

export async function legalConversionConvert(
  section: string,
  direction: "forward" | "reverse" = "forward",
  matterId = "",
  pair: "ipc_bns" | "crpc_bnss" = "ipc_bns"
) {
  const s = section.trim();
  if (!s) throw new Error("Enter a section number");
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";

  if (pair === "crpc_bnss") {
    try {
      const params = new URLSearchParams({ section: s, direction, pair });
      if (matterId) params.set("matter_id", matterId);
      return normalizeIpcBnsConversion(
        await apiFetch<Record<string, unknown>>(`/api/v1/legal-conversion/convert?${params}`)
      );
    } catch {
      /* fall through to v3 not applicable */
    }
    throw new Error("CrPC↔BNSS lookup unavailable — restart backend to load official dataset.");
  }

  const tryV3 = async () => {
    if (direction === "reverse") {
      return normalizeIpcBnsConversion(
        await apiFetch<Record<string, unknown>>(
          `/api/v1/ipc-bns/v3/bns/${encodeURIComponent(s)}${q}`
        )
      );
    }
    return normalizeIpcBnsConversion(
      await apiFetch<Record<string, unknown>>(
        `/api/v1/ipc-bns/v3/ipc/${encodeURIComponent(s)}${q}`
      )
    );
  };

  try {
    return await tryV3();
  } catch {
    /* Legacy /api/tools routes — always registered on older backends */
  }

  if (direction === "forward") {
    const legacy = await ipcConvert(s);
    return normalizeIpcBnsConversion({
      found: legacy.status === "mapped",
      status: legacy.status,
      ipc_section: legacy.ipc_section,
      bns_section: legacy.bns_section,
      offence_title: legacy.description,
      short_description: legacy.description,
      message: legacy.status === "mapped" ? null : legacy.description,
    });
  }

  return normalizeIpcBnsConversion(
    await apiFetch<Record<string, unknown>>(`/api/tools/ipc-bns/bns/${encodeURIComponent(s)}`)
  );
}

export async function legalConversionSearch(q: string, pair: "ipc_bns" | "crpc_bnss" = "ipc_bns") {
  try {
    const params = new URLSearchParams({ q, pair });
    return await apiFetch<{ results: Array<Record<string, unknown>>; count: number }>(
      `/api/v1/legal-conversion/search?${params}`
    );
  } catch {
    const r = await ipcBnsV3Search(q);
    return {
      ...r,
      results: (r.results || []).map((x) => normalizeIpcBnsConversion(x)),
    };
  }
}

export async function ipcBnsV3ExportReport(body: {
  case_name: string;
  conversions: Array<Record<string, unknown>>;
  format: "pdf" | "docx";
}) {
  const token = getToken();
  const res = await fetch(`${getApiBase()}/api/v1/ipc-bns/v3/report/export`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readResponseError(res, "Export failed"));
  return res.blob();
}

export async function courtFeeRegions() {
  return apiFetch<{ regions: string[] }>("/api/tools/court-fee/regions");
}

export async function courtFeeCalc(body: {
  suit_value: number;
  region: string;
  suit_type: string;
  court_level: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/tools/court-fee", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function contractReview(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const token = getToken();
  const res = await fetchWithRetry(
    "/api/tools/contract-review",
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    },
    300000,
    2
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Contract review failed");
  }
  return res.json() as Promise<{ analysis: string }>;
}

export async function casePrediction(body: {
  case_details: string;
  court_type: string;
}) {
  return apiFetch<{ prediction: string }>("/api/tools/case-prediction", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function checkCitations(citations: string[]) {
  return apiFetch<{ result: string }>("/api/tools/citations", {
    method: "POST",
    body: JSON.stringify({ citations }),
  });
}

export async function odrProposal(body: Record<string, unknown>) {
  return apiFetch<{ proposal: string }>("/api/tools/odr", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------- Settings ----------

export type SettingsPayload = {
  user: Record<string, unknown>;
  llm: Record<string, unknown>;
  web_search: Record<string, unknown>;
  ocr: Record<string, unknown>;
};

export async function fetchSettings() {
  return apiFetch<SettingsPayload>("/api/settings");
}

export async function subscribePlan(plan: string) {
  return apiFetch<{
    mode: string;
    checkout_url?: string;
    membership?: string;
    message?: string;
  }>("/api/v1/subscriptions/subscribe", {
    method: "POST",
    body: JSON.stringify({ plan }),
  });
}

export async function upgradePlan(plan: string) {
  const result = await subscribePlan(plan);
  if (result.mode === "stripe" && result.checkout_url) {
    window.location.href = result.checkout_url;
    return { membership: plan, success: true };
  }
  return {
    membership: result.membership || plan,
    success: true,
  };
}

export type OrgInvitePreview = {
  org_name: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
};

export async function fetchOrgInvitePreview(token: string) {
  const res = await fetchWithRetry(
    `/api/v1/orgs/invites/${encodeURIComponent(token)}`,
    {},
    15000
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Invite not found"));
  }
  return res.json() as Promise<OrgInvitePreview>;
}

export async function acceptOrgInvite(token: string) {
  return apiFetch<{ ok: boolean; org_id: string; org_name?: string; role?: string }>(
    `/api/v1/orgs/invites/${encodeURIComponent(token)}/accept`,
    { method: "POST" }
  );
}

export type BillingPlanInfo = {
  id: string;
  name: string;
  price_inr: number;
  interval: string;
  description: string;
  features: string[];
  stripe_price_id?: string;
};

export async function fetchBillingPlans() {
  return apiFetch<{
    stripe_enabled: boolean;
    mock_billing: boolean;
    currency: string;
    plans: BillingPlanInfo[];
  }>("/api/v1/subscriptions/plans");
}

export async function fetchSubscriptionStatus() {
  return apiFetch<{
    membership: string;
    stripe_enabled: boolean;
    mock_billing: boolean;
    currency: string;
    plans: BillingPlanInfo[];
  }>("/api/v1/subscriptions/status");
}

export async function fetchBillingPayments() {
  return apiFetch<{
    payments: Array<{
      plan: string;
      amount: number;
      status: string;
      date?: string;
      expires?: string;
      payment_id?: string;
    }>;
  }>("/api/v1/subscriptions/payments");
}

/** @deprecated Use fetchBillingPayments */
export async function fetchPayments() {
  return fetchBillingPayments();
}

export async function testLlm() {
  return apiFetch<{ reply: string }>("/api/settings/llm-test", { method: "POST" });
}

export async function recheckLlm() {
  return apiFetch<Record<string, unknown>>("/api/settings/llm-recheck", {
    method: "POST",
  });
}

// ---------- Drafting redline ----------

export async function draftingRedline(document: string, instruction: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/drafting/redline", {
    method: "POST",
    body: JSON.stringify({ document, instruction }),
  });
}

export async function redlineFeedback(body: {
  instruction: string;
  before: string;
  after: string;
  accepted?: boolean;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/drafting/redline/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------- E-discovery PII ----------

export async function piiDetect(text: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/ediscovery/pii/detect", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function piiWhitelist(phrase: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/ediscovery/pii/whitelist", {
    method: "POST",
    body: JSON.stringify({ phrase }),
  });
}

export type LearningSignal =
  | "thumbs_up"
  | "thumbs_down"
  | "copy"
  | "regenerate"
  | "helpful"
  | "follow_up_click"
  | "export_docx"
  | "export_pdf"
  | "export_client_safe"
  | "save_to_matter"
  | "edit_diff"
  | "dwell_time"
  | "mode_switch";

export async function learningFeedback(body: {
  signal: LearningSignal;
  interaction_id?: string;
  chat_id?: string;
  comment?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}) {
  return apiFetch<{
    ok: boolean;
    error?: string;
    coach?: Record<string, unknown>;
    training_pipeline?: Record<string, unknown>;
  }>("/api/v1/learning/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  }, 8000);
}

export async function learningSignal(body: {
  signal: LearningSignal;
  interaction_id?: string;
  chat_id?: string;
  comment?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}) {
  return apiFetch<{ ok: boolean; error?: string }>("/api/v1/learning/signals", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function learningFeedbackTags() {
  return apiFetch<{ tags: { id: string; label: string }[] }>("/api/v1/learning/signals/tags");
}

export async function learningSignalStats() {
  return apiFetch<Record<string, unknown>>("/api/v1/learning/signals/stats");
}

export async function exportResearchReport(body: {
  content: string;
  title?: string;
  format: "docx" | "pdf" | "md";
  client_safe?: boolean;
}) {
  const token = getToken();
  const res = await fetchWithRetry(
    "/api/v1/chat/export-report",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
    60000,
    1
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disp);
  const filename = match?.[1] || `report.${body.format}`;
  return { blob, filename };
}

export type EngineStatusPayload = {
  gemini?: { ok?: boolean; label?: string; model?: string };
  llm?: { ok?: boolean; label?: string; backend?: string };
  kb?: { ok?: boolean; label?: string; doc_count?: number; vectors?: number };
  embeddings?: { ok?: boolean; label?: string; model?: string };
  learning?: { ok?: boolean; label?: string };
  usage?: {
    gemini_calls_today?: number;
    gemini_limit?: number;
    gemini_remaining?: number;
  };
  strict_citations?: boolean;
  legacy_web?: boolean;
  membership?: string;
};

export async function fetchEngineStatus(matterId?: string) {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<EngineStatusPayload>(`/api/v1/engines/status${q}`);
}

export async function fetchMatterAutopilot(matterId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/autopilot`);
}

export async function learningStats() {
  return apiFetch<LearningStatsPayload>("/api/v1/learning/stats");
}

export type LearningModeStats = {
  mode: string;
  turns: number;
  positive: number;
  negative: number;
  not_found_rate: number;
  threshold_delta?: number;
  avg_retrieval_score?: number;
  positive_rate?: number | null;
  accuracy_pct?: number | null;
  hit_rate_pct?: number;
};

export type LearningSummary = {
  total_turns: number;
  total_positive: number;
  total_negative: number;
  feedback_count: number;
  positive_rate?: number | null;
  accuracy_pct?: number | null;
  avg_hit_rate_pct?: number | null;
};

export type NeuralTuningStatus = {
  enabled: boolean;
  auto_train: boolean;
  rapid_mode: boolean;
  unused_pairs: number;
  min_pairs_required: number;
  active_model_path?: string | null;
  active_model_loaded: boolean;
  last_run?: {
    id: string;
    status: string;
    pair_count: number;
    base_model?: string;
    output_path?: string;
    metrics?: Record<string, unknown>;
    error?: string | null;
    started_at?: string;
    finished_at?: string | null;
  } | null;
};

export type LearningEngineStatus = {
  enabled: boolean;
  memory_enabled: boolean;
  answer_memory_count: number;
  top_memories?: Array<{ query: string; hits: number; confidence: number }>;
  rescue_stats?: Record<string, { successes: number; attempts: number }>;
  neural_finetuning?: NeuralTuningStatus;
  adaptive_learning?: {
    modes?: LearningModeStats[];
    summary?: LearningSummary;
    learned_queries?: Array<{ query: string; expansion: string; success: number }>;
    top_chunks?: Array<{ key: string; boost: number; hits: number }>;
    auto_improve_enabled?: boolean;
  };
  performance?: LearningSummary;
  ollama_coach?: OllamaCoachStatus;
  improvement_automation?: ImprovementAutomationStatus;
};

export type ImprovementAutomationStatus = {
  enabled: boolean;
  auto_reindex: boolean;
  auto_ollama_create: boolean;
  auto_use_tuned_model: boolean;
  min_thumbs_for_export: number;
  thumbs_up: number;
  active_tuned_model: string;
  export_ready: boolean;
  can_export_modelfile?: boolean;
  quality_gate?: {
    passed?: boolean;
    reasons?: string[];
    checks?: Record<string, unknown>;
  };
  log_path?: string;
};

export type LearningProgressPayload = {
  thumbs_up: number;
  min_thumbs_for_export: number;
  thumbs_progress_pct: number;
  export_ready_count: boolean;
  can_export_modelfile: boolean;
  next_milestone: string;
  automation?: ImprovementAutomationStatus;
  quality_gate?: Record<string, unknown>;
  signals?: Record<string, unknown>;
  training_pipeline?: Record<string, unknown>;
  coach_schedule?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
};

export async function fetchLearningProgress() {
  return apiFetch<LearningProgressPayload>("/api/v1/learning/progress");
}

export async function runHoldoutEval() {
  return apiFetch<Record<string, unknown>>("/api/v1/learning/eval/holdout", { method: "POST" });
}

export type OllamaCoachStatus = {
  global_enabled: boolean;
  gemini_configured: boolean;
  available: boolean;
  user_enabled: boolean;
  last_run_at?: string | null;
  last_insights?: Record<string, unknown>;
  directives_text?: string;
  memory_count?: number;
  recent_memories?: Array<{ id: string; source: string; content: string; created_at: string }>;
  schedule?: {
    auto_schedule_enabled?: boolean;
    last_auto_coach_at?: string | null;
    new_feedback_since_last?: number;
    interval_days?: number;
    min_new_feedback?: number;
    due?: boolean;
  };
  ollama_export?: {
    has_export?: boolean;
    export_dir?: string;
    modelfile_path?: string;
    jsonl_path?: string;
    modelfile_preview?: string;
  };
  model?: string;
  scope?: string;
  gemini_usage?: Record<string, unknown>;
};

export type OllamaCoachResult = {
  ok: boolean;
  error?: string;
  trigger?: string;
  neural?: Record<string, unknown>;
  ollama?: Record<string, unknown>;
  coach?: Record<string, unknown>;
  thumbs_up?: number;
  run_id?: string;
  feedback_count?: number;
  insights?: Record<string, unknown>;
  applied?: Record<string, unknown>;
  collect?: Record<string, unknown>;
  training?: Record<string, unknown> | null;
  ollama_export?: Record<string, unknown>;
  message?: string;
  create_command?: string;
  suggested_model_name?: string;
  modelfile_path?: string;
  export_dir?: string;
};

export type LearningStatsPayload = {
  modes?: LearningModeStats[];
  summary?: LearningSummary;
  learned_queries?: Array<{ query: string; expansion: string; success: number }>;
  top_chunks?: Array<{ key: string; boost: number; hits: number }>;
  auto_improve_enabled?: boolean;
};

export async function fetchLearningEngineStatus() {
  return apiFetch<LearningEngineStatus>("/api/v1/learning/engine/status");
}

export async function neuralTuningStatus() {
  return apiFetch<NeuralTuningStatus>("/api/v1/learning/tuning/neural/status");
}

export async function neuralCollectPairs() {
  return apiFetch<{ ok: boolean; pairs_added: number }>(
    "/api/v1/learning/tuning/neural/collect",
    { method: "POST" }
  );
}

export async function neuralTrainEmbeddings() {
  return apiFetch<{
    ok: boolean;
    error?: string;
    pair_count?: number;
    run_id?: string;
    output_path?: string;
    message?: string;
    reindex_recommended?: boolean;
    metrics?: Record<string, unknown>;
  }>("/api/v1/learning/tuning/neural/train", { method: "POST" });
}

export async function learningAutoImprove() {
  return apiFetch<{
    ok: boolean;
    pairs_added: number;
    training_started: boolean;
    training?: Record<string, unknown> | null;
    unused_pairs_before: number;
    unused_pairs_after: number;
    status: LearningEngineStatus;
  }>("/api/v1/learning/engine/auto-improve", { method: "POST" });
}

export async function fetchOllamaCoachStatus() {
  return apiFetch<OllamaCoachStatus>("/api/v1/learning/tuning/coach/status");
}

export async function toggleOllamaCoach(enabled: boolean) {
  return apiFetch<{ enabled: boolean; last_run_at?: string | null; last_insights?: Record<string, unknown> }>(
    "/api/v1/learning/tuning/coach/toggle",
    { method: "POST", body: JSON.stringify({ enabled }) }
  );
}

export async function runOllamaCoachCycle() {
  return apiFetch<OllamaCoachResult>("/api/v1/learning/tuning/coach/run", { method: "POST" });
}

export async function analyzeOllamaCoachFeedback() {
  return apiFetch<OllamaCoachResult>("/api/v1/learning/tuning/coach/analyze", { method: "POST" });
}

export async function applyOllamaCoachInsights() {
  return apiFetch<OllamaCoachResult>("/api/v1/learning/tuning/coach/apply", { method: "POST" });
}

export async function fetchOllamaCoachDirectives() {
  return apiFetch<{
    directives_text: string;
    memories: Array<{ id: string; source: string; content: string; created_at: string }>;
  }>("/api/v1/learning/tuning/coach/directives");
}

export async function saveOllamaCoachDirectives(text: string, apply = true) {
  return apiFetch<OllamaCoachResult & { saved?: boolean; coach_applied?: boolean }>(
    "/api/v1/learning/tuning/coach/directives",
    { method: "POST", body: JSON.stringify({ text, apply }) }
  );
}

export async function toggleOllamaCoachSchedule(enabled: boolean) {
  return apiFetch<Record<string, unknown>>("/api/v1/learning/tuning/coach/schedule/toggle", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export async function exportOllamaModelfile() {
  return apiFetch<OllamaCoachResult>("/api/v1/learning/tuning/ollama/export-modelfile", {
    method: "POST",
  });
}

export async function fetchImprovementAutomationStatus() {
  return apiFetch<ImprovementAutomationStatus>("/api/v1/learning/automation/status");
}

export type MlJob = {
  job_id: string;
  job_type: string;
  status: string;
  progress: number;
  created_at?: string;
  updated_at?: string;
  error_message?: string;
  result?: Record<string, unknown>;
};

export async function fetchMlJobs(limit = 10) {
  return apiFetch<{ jobs: MlJob[] }>(
    `/api/v1/learning/automation/jobs?limit=${limit}`
  );
}

export async function fetchMlJob(jobId: string) {
  return apiFetch<MlJob>(`/api/v1/learning/automation/jobs/${encodeURIComponent(jobId)}`);
}

export async function runImprovementAutomation() {
  return apiFetch<
    OllamaCoachResult & { queued?: boolean; job_id?: string; worker?: string }
  >("/api/v1/learning/automation/run-now", { method: "POST" });
}

export async function fetchOllamaExportStatus() {
  return apiFetch<{
    has_export: boolean;
    export_dir?: string;
    modelfile_path?: string;
    jsonl_path?: string;
    modelfile_preview?: string;
  }>("/api/v1/learning/tuning/ollama/export-status");
}

export type DashboardFull = {
  username?: string;
  membership?: string;
  documents?: number;
  queries?: number;
  kb_status?: string;
  kb_chunks?: number;
  kb_documents?: number;
  kb_last_updated?: string | null;
  llm_online?: boolean;
  embedding?: {
    state?: string;
    ready?: boolean;
    model?: string;
    device?: string;
  };
  recent_queries?: Array<{
    thread_id?: string;
    question?: string;
    preview?: string;
    mode?: string;
    language?: string;
    created_at?: string;
  }>;
  recent_documents?: Array<{
    id?: string;
    filename?: string;
    pages?: number;
    uploaded_at?: string;
  }>;
  practice?: {
    matters_total?: number;
    matters_active?: number;
    billing?: {
      unbilled_amount_inr?: number;
      unbilled_entries?: number;
      invoiced_total_inr?: number;
    };
    crm?: {
      leads_total?: number;
      pipeline_stages?: Record<string, number>;
    };
    ediscovery?: { batches_total?: number };
    modules_ready?: Record<string, boolean>;
  };
  learning?: {
    total_turns?: number;
    total_positive?: number;
    total_negative?: number;
    feedback_count?: number;
    accuracy_pct?: number | null;
    avg_hit_rate_pct?: number | null;
    modes_count?: number;
  };
};

export async function dashboardFull() {
  return apiFetch<DashboardFull>("/api/v1/dashboard/full");
}

export async function analyticsFull() {
  return apiFetch<Record<string, unknown>>("/api/v1/learning/analytics/full");
}

export type ProductKpi = {
  generated_at: string;
  users_total: number;
  dau: number;
  mau: number;
  new_users_7d: number;
  chat_turns_7d: number;
  chat_turns_30d: number;
  documents_total: number;
  matters_total: number;
  retention_proxy_pct: number;
  plans: Record<string, number>;
  subscriptions_by_plan: Record<string, number>;
  ai: {
    feedback_positive: number;
    feedback_negative: number;
    hit_rate_pct: number;
    not_found_rate_pct: number;
  };
};

export async function productKpi() {
  return apiFetch<ProductKpi>("/api/v1/saas-metrics/kpi");
}

export type OrgBranding = {
  org_id?: string;
  name?: string;
  custom_domain?: string;
  logo_url?: string;
  primary_color?: string;
  support_email?: string;
  plan?: string;
};

export async function fetchEnterpriseBranding() {
  return apiFetch<{ branding: OrgBranding }>("/api/v1/enterprise/branding");
}

export async function patchOrgBranding(
  orgId: string,
  body: Partial<OrgBranding>
) {
  return apiFetch<{ branding: OrgBranding }>(
    `/api/v1/enterprise/orgs/${encodeURIComponent(orgId)}/branding`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
}

export async function fetchSsoStatus() {
  return apiFetch<{
    enabled: boolean;
    oidc_configured: boolean;
    dev_mock: boolean;
  }>("/api/v1/sso/status");
}

export async function ssoLoginStart() {
  return apiFetch<{ authorize_url: string }>("/api/v1/sso/login");
}

export async function ssoCallback(body: {
  code?: string;
  state?: string;
  email?: string;
  name?: string;
}) {
  return apiFetch<{ token: string; user: Record<string, unknown> }>(
    "/api/v1/sso/callback",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function fetchEnterpriseAgents() {
  return apiFetch<{ agents: Array<{ id: string; name: string; description: string }> }>(
    "/api/v1/enterprise/agents"
  );
}

export async function runEnterpriseAgent(
  agentType: string,
  payload: Record<string, unknown>,
  asyncQueue = true
) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/agents/run", {
    method: "POST",
    body: JSON.stringify({ agent_type: agentType, payload, async_queue: asyncQueue }),
  });
}

export async function syncCourtCauseList(body: {
  source?: string;
  text?: string;
  auto_schedule?: boolean;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/court/sync", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchCourtIntegrationStatus() {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/court/status");
}

// ---------- Enterprise V2 workspace ----------

export async function fetchEnterpriseDashboard() {
  return apiFetch<{
    metrics: Record<string, number>;
    kpi_strip?: Record<string, number>;
    snapshot?: Record<string, number>;
    action_queues?: Record<string, Array<Record<string, unknown>>>;
    activity_feed?: Array<Record<string, unknown>>;
    priorities_today?: Array<Record<string, unknown>>;
    agents?: Array<{
      id: string;
      name: string;
      description: string;
      schedule?: string;
      mode?: string;
      status: string;
    }>;
    notifications?: Array<Record<string, unknown>>;
    is_empty?: boolean;
    analytics?: Record<string, unknown>;
    permission_roles?: Array<Record<string, unknown>>;
    permissions?: Record<string, boolean>;
    practice_areas?: string[];
  }>("/api/v1/enterprise/workspace/dashboard");
}

export async function enterpriseGlobalSearch(q: string) {
  return apiFetch<{
    query: string;
    results: Array<Record<string, unknown>>;
    groups: Record<string, Array<Record<string, unknown>>>;
  }>(`/api/v1/enterprise/workspace/search?q=${encodeURIComponent(q)}`);
}

export async function fetchEnterpriseMattersHub() {
  return apiFetch<{ matters: Array<Record<string, unknown>> }>(
    "/api/v1/enterprise/workspace/matters"
  );
}

export async function fetchEnterpriseMatterHub(matterId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/enterprise/workspace/matters/${encodeURIComponent(matterId)}/hub`
  );
}

export async function fetchEnterpriseAnalytics() {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/workspace/analytics");
}

export async function fetchEnterpriseFolders(matterId = "", practiceArea = "") {
  const q = new URLSearchParams();
  if (matterId) q.set("matter_id", matterId);
  if (practiceArea) q.set("practice_area", practiceArea);
  return apiFetch<{ folders: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/folders?${q}`
  );
}

export async function seedEnterpriseMatterFolders(
  matterId: string,
  matterName: string,
  practiceArea = "Litigation"
) {
  const q = new URLSearchParams({
    matter_id: matterId,
    matter_name: matterName,
    practice_area: practiceArea,
  });
  return apiFetch<{ ok: boolean; folders: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/folders/seed-matter?${q}`,
    { method: "POST" }
  );
}

export async function fetchEnterpriseDocuments(params?: {
  matter_id?: string;
  folder_id?: string;
  practice_area?: string;
}) {
  const q = new URLSearchParams();
  if (params?.matter_id) q.set("matter_id", params.matter_id);
  if (params?.folder_id) q.set("folder_id", params.folder_id);
  if (params?.practice_area) q.set("practice_area", params.practice_area);
  return apiFetch<{ documents: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/documents?${q}`
  );
}

export async function searchEnterpriseDocuments(
  q: string,
  opts?: { matter_id?: string; doc_type?: string; tag?: string }
) {
  const params = new URLSearchParams({ q });
  if (opts?.matter_id) params.set("matter_id", opts.matter_id);
  if (opts?.doc_type) params.set("doc_type", opts.doc_type);
  if (opts?.tag) params.set("tag", opts.tag);
  return apiFetch<{ results: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/documents/search?${params}`
  );
}

export async function uploadEnterpriseDocument(body: {
  title: string;
  content_text: string;
  filename?: string;
  matter_id?: string;
  folder_id?: string;
  practice_area?: string;
  doc_type?: string;
  tags?: string[];
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/workspace/documents", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchEnterpriseCourtOrders(matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{ orders: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/court-orders${q}`
  );
}

export async function searchEnterpriseCourtOrders(
  q: string,
  opts?: { judge?: string; court?: string; matter_id?: string; order_type?: string }
) {
  const params = new URLSearchParams({ q });
  if (opts?.judge) params.set("judge", opts.judge);
  if (opts?.court) params.set("court", opts.court);
  if (opts?.matter_id) params.set("matter_id", opts.matter_id);
  if (opts?.order_type) params.set("order_type", opts.order_type);
  return apiFetch<{ results: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/court-orders/search?${params}`
  );
}

export async function fetchEnterpriseCourtOrder(orderId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/enterprise/workspace/court-orders/${encodeURIComponent(orderId)}`
  );
}

export async function uploadEnterpriseCourtOrder(body: {
  content_text: string;
  filename?: string;
  matter_id?: string;
  client_name?: string;
  order_type?: string;
  practice_area?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/workspace/court-orders", {
    method: "POST",
    body: JSON.stringify({ ...body, run_analysis: true }),
  });
}

export async function searchEnterpriseKnowledge(q: string) {
  return apiFetch<{ results: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/knowledge?q=${encodeURIComponent(q)}`
  );
}

export async function createEnterpriseKnowledge(body: {
  title: string;
  content_text?: string;
  entry_type?: string;
  practice_area?: string;
  matter_id?: string;
  court?: string;
  tags?: string[];
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/workspace/knowledge", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchEnterpriseClientPortal() {
  return apiFetch<{
    portals: Array<Record<string, unknown>>;
    document_requests: Array<Record<string, unknown>>;
    approvals: Array<Record<string, unknown>>;
  }>("/api/v1/enterprise/workspace/client-portal");
}

export async function createEnterpriseDocRequest(body: {
  matter_id: string;
  request_type: string;
  client_email?: string;
  notes?: string;
}) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/enterprise/workspace/client-portal/document-request",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function requestEnterpriseClientReview(body: {
  matter_id: string;
  title: string;
  draft_id?: string;
  client_email?: string;
}) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/enterprise/workspace/client-portal/request-review",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function fetchEnterpriseAudit(q = "") {
  return apiFetch<{ entries: Array<Record<string, unknown>> }>(
    `/api/v1/enterprise/workspace/audit?q=${encodeURIComponent(q)}`
  );
}

export async function fetchEnterpriseStorage() {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/workspace/storage");
}

export async function fetchPilotSummary() {
  return apiFetch<{
    total: number;
    active: number;
    target: number;
    on_track: boolean;
    firms: Array<Record<string, unknown>>;
  }>("/api/v1/enterprise/pilot/summary");
}

export async function registerPilotFirm(body: {
  firm_name: string;
  contact_email: string;
  plan?: string;
  org_id?: string;
  notes?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/enterprise/pilot/firms", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updatePilotFirm(
  pilotId: string,
  body: { status: string; notes?: string }
) {
  return apiFetch<{ ok: boolean }>(
    `/api/v1/enterprise/pilot/firms/${encodeURIComponent(pilotId)}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
}

export type MemoryFact = {
  id: string;
  key: string;
  value: string;
  source: string;
  confidence?: number;
};

export type MemoryProfile = {
  user_id?: string;
  persona: string;
  practice_area?: string;
  communication_notes?: string;
  memory_enabled?: boolean;
  facts?: MemoryFact[];
};

export async function fetchMemoryProfile() {
  return apiFetch<MemoryProfile>("/api/v1/memory/profile");
}

export async function updateMemoryProfile(body: Partial<MemoryProfile>) {
  return apiFetch<MemoryProfile>("/api/v1/memory/profile", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function addMemoryFact(key: string, value: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/memory/facts", {
    method: "POST",
    body: JSON.stringify({ key, value }),
  });
}

export async function updateMemoryFact(id: string, key: string, value: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/memory/facts/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ key, value }),
  });
}

export async function deleteMemoryFact(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/memory/facts/${id}`, {
    method: "DELETE",
  });
}

export async function reindexChatMemory() {
  return apiFetch<{ threads_indexed: number; chunks_added: number }>(
    "/api/v1/memory/facts/reindex-chats",
    { method: "POST" }
  );
}

export async function tuningExport() {
  return apiFetch<{ status: string; record_count: number; path: string }>(
    "/api/v1/learning/tuning/export",
    { method: "POST" }
  );
}

// ---------- Phase 1: Matters & document automation ----------

export type Matter = {
  matter_id: string;
  matter_name: string;
  practice_area: string;
  matter_type?: string;
  case_number?: string;
  status_tier?: string;
  client_name?: string;
  opposing_party?: string;
  venue?: string;
  police_station?: string;
  fir_number?: string;
  filing_date?: string;
  next_hearing_date?: string;
  priority?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  document_count?: number;
  kb_ready?: boolean;
  vector_count?: number;
  notes?: Array<{ note_id: string; raw_content: string; timestamp: string }>;
  documents?: Array<{ document_id: string; filename: string }>;
};

export type MatterMetaTypes = {
  matter_types: string[];
  status_tiers: string[];
  priorities: string[];
};

export async function listMatters(status = "") {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<{ matters: Matter[] }>(`/api/v1/matters${q}`);
}

export async function fetchMatterMetaTypes() {
  return apiFetch<MatterMetaTypes>("/api/v1/matters/meta/types");
}

export async function deleteMatter(matterId: string, hard = true) {
  const q = hard ? "?hard=true" : "";
  return apiFetch<{ deleted: boolean; archived?: boolean; matter_id: string }>(
    `/api/v1/matters/${encodeURIComponent(matterId)}${q}`,
    { method: "DELETE" }
  );
}

export async function deleteMatterChatHistory(matterId: string) {
  return apiFetch<{ ok: boolean; matter_id: string; deleted_rows: number }>(
    `/api/v1/sessions/history?matter_id=${encodeURIComponent(matterId)}`,
    { method: "DELETE" }
  );
}

export async function createMatter(body: {
  matter_name: string;
  practice_area?: string;
  matter_type?: string;
  case_number?: string;
  client_name?: string;
  opposing_party?: string;
  venue?: string;
  status_tier?: string;
  police_station?: string;
  fir_number?: string;
  filing_date?: string;
  next_hearing_date?: string;
  priority?: string;
  description?: string;
}) {
  return apiFetch<Matter>("/api/v1/matters", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getMatter(matterId: string) {
  return apiFetch<Matter>(`/api/v1/matters/${matterId}`);
}

export async function addMatterNote(matterId: string, raw_content: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/notes`, {
    method: "POST",
    body: JSON.stringify({ raw_content }),
  });
}

export async function listMattersSummary() {
  return apiFetch<{ matters: Array<Matter & { document_count?: number }> }>(
    "/api/v1/matters?summary=1"
  );
}

export type MatterDocumentUploadResponse = {
  status: string;
  document_id?: string;
  document_name?: string;
  pages?: number;
  chunks_added?: number;
  indexed?: boolean;
  index_message?: string;
  index_job_id?: string;
};

export type MatterDraftingOverview = {
  matter_id?: string;
  total?: number;
  drafts?: number;
  awaiting_review?: number;
  filed_or_ready?: number;
  control_center_url?: string;
  awaiting_documents?: Array<{ draft_id: string; title: string; status: string }>;
  recent_timeline?: Array<Record<string, unknown>>;
};

export type MatterDashboard = {
  matter: Matter;
  drafting?: MatterDraftingOverview;
  documents: Array<{
    document_id: string;
    filename: string;
    privileged?: number | boolean;
    index_status?: string;
  }>;
  notes: Matter["notes"];
  timeline: Array<Record<string, string>>;
  hearings: Array<Record<string, string>>;
  tasks: Array<Record<string, string>>;
  deadlines: Array<Record<string, string>>;
  stats: Record<string, number>;
  kb_health: Record<string, unknown>;
  autopilot: Record<string, unknown>;
  smoke?: { tests?: Array<{ name?: string; pass?: boolean; detail?: string }> };
  rag_scope: string;
};

export type MatterUpdatePayload = Partial<
  Pick<
    Matter,
    | "matter_name"
    | "practice_area"
    | "matter_type"
    | "case_number"
    | "status_tier"
    | "client_name"
    | "opposing_party"
    | "venue"
    | "police_station"
    | "fir_number"
    | "filing_date"
    | "next_hearing_date"
    | "priority"
    | "description"
  >
>;

export async function getMatterDashboard(matterId: string) {
  return apiFetch<MatterDashboard>(`/api/v1/matters/${matterId}/dashboard`);
}

export async function linkMatterDocument(matterId: string, documentId: string) {
  return apiFetch<{ linked: boolean }>(`/api/v1/matters/${matterId}/documents/link`, {
    method: "POST",
    body: JSON.stringify({ document_id: documentId }),
  });
}

export async function listUnlinkedDocuments() {
  return apiFetch<{ documents: Array<{ document_id: string; filename: string }> }>(
    "/api/v1/matters/documents/unlinked"
  );
}

export async function listMatterTimeline(matterId: string) {
  return apiFetch<{ events: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/timeline`
  );
}

export async function addMatterTimeline(
  matterId: string,
  body: { title: string; description?: string; event_date?: string }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/timeline`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listMatterHearings(matterId: string) {
  return apiFetch<{ hearings: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/hearings`
  );
}

export async function addMatterHearing(
  matterId: string,
  body: {
    hearing_date: string;
    court_name?: string;
    purpose?: string;
    notes?: string;
    judge_name?: string;
    summary?: string;
  }
) {
  return apiFetch<{
    ok: boolean;
    message: string;
    hearing: Record<string, unknown>;
  }>(`/api/v1/matters/${matterId}/hearings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function addMatterTask(
  matterId: string,
  body: { title: string; due_date?: string; assignee?: string }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/tasks`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchMatterTask(
  matterId: string,
  taskId: string,
  body: Record<string, string>
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function addMatterDeadline(
  matterId: string,
  body: { title: string; due_date: string; deadline_type?: string; notes?: string }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/deadlines`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateMatter(matterId: string, body: MatterUpdatePayload) {
  return apiFetch<Matter>(`/api/v1/matters/${matterId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function searchMatter(matterId: string, q: string) {
  return apiFetch<{ query: string; results: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/search?q=${encodeURIComponent(q)}`
  );
}

export async function generateMatterTimeline(matterId: string, autoInsert = false) {
  return apiFetch<{ events: Array<Record<string, string>>; inserted: number }>(
    `/api/v1/matters/${matterId}/timeline/generate?auto_insert=${autoInsert ? "true" : "false"}`,
    { method: "POST" }
  );
}

export async function extractMatterEntities(matterId: string) {
  return apiFetch<{ entities: Array<Record<string, unknown>>; count: number }>(
    `/api/v1/matters/${matterId}/entities/extract`,
    { method: "POST" }
  );
}

export async function extractMatterEvidence(matterId: string) {
  return apiFetch<{ evidence: Array<Record<string, unknown>>; count: number }>(
    `/api/v1/matters/${matterId}/evidence/extract`,
    { method: "POST" }
  );
}

export async function extractMatterHearings(matterId: string) {
  return apiFetch<{
    ok: boolean;
    hearings: Array<Record<string, unknown>>;
    inserted: number;
    count: number;
  }>(`/api/v1/matters/${matterId}/hearings/extract`, { method: "POST" });
}

export async function getMatterIntelStatus(matterId: string) {
  return apiFetch<{
    matter_id: string;
    stage: string;
    message: string;
    progress: Record<string, number>;
    last_error?: string;
    updated_at?: string;
  }>(`/api/v1/matters/${matterId}/intelligence/status`);
}

export async function runMatterIntelligence(matterId: string) {
  return apiFetch<{ ok: boolean; progress?: Record<string, number>; stages?: Record<string, unknown> }>(
    `/api/v1/matters/${matterId}/intelligence/run`,
    { method: "POST" }
  );
}

export async function listMatterEntities(matterId: string) {
  return apiFetch<{ entities: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/entities`
  );
}

export async function listMatterEvidence(matterId: string) {
  return apiFetch<{ evidence: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/evidence`
  );
}

export async function addMatterEvidence(
  matterId: string,
  body: {
    title: string;
    category?: string;
    document_id?: string;
    tags?: string;
    notes?: string;
    strength?: string;
  }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/matters/${matterId}/evidence`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function runMatterSmokeTest(matterId: string) {
  return apiFetch<{
    ok: boolean;
    pass?: boolean;
    tests: Array<Record<string, unknown>>;
    ai_confidence?: number;
    vector_count?: number;
    chunk_count?: number;
    retrieval_pass_count?: number;
  }>(`/api/v1/matters/${matterId}/smoke`, { method: "POST" });
}

export async function fetchMatterNotifications() {
  return apiFetch<{ notifications: Array<Record<string, unknown>> }>(
    "/api/v1/matters/notifications/all"
  );
}

export async function listTimelineSuggestions(matterId: string, status = "pending") {
  return apiFetch<{ suggestions: Array<Record<string, string>> }>(
    `/api/v1/matters/${matterId}/timeline/suggestions?status=${encodeURIComponent(status)}`
  );
}

export async function approveTimelineSuggestion(matterId: string, suggestionId: string) {
  return apiFetch<{ approved: boolean }>(
    `/api/v1/matters/${matterId}/timeline/suggestions/${suggestionId}/approve`,
    { method: "POST" }
  );
}

export async function rejectTimelineSuggestion(matterId: string, suggestionId: string) {
  return apiFetch<{ rejected: boolean }>(
    `/api/v1/matters/${matterId}/timeline/suggestions/${suggestionId}/reject`,
    { method: "POST" }
  );
}

export async function fetchEntityProfiles(matterId: string) {
  return apiFetch<{ profiles: Array<Record<string, unknown>> }>(
    `/api/v1/matters/${matterId}/entities/profiles`
  );
}

export async function fetchContradictions(matterId: string) {
  return apiFetch<{
    summary?: string;
    sources?: Array<Record<string, string>>;
    pairs: Array<Record<string, string>>;
    count?: number;
  }>(`/api/v1/matters/${matterId}/contradictions`);
}

export async function extractMatterContradictions(matterId: string) {
  return apiFetch<{
    summary: string;
    sources: Array<Record<string, string>>;
    pairs: Array<Record<string, unknown>>;
  }>(`/api/v1/matters/${matterId}/contradictions/extract`, { method: "POST" });
}

export async function exportMatterPack(matterId: string) {
  const token = getToken();
  const res = await fetchWithRetry(
    `${getApiBase()}/api/v1/matters/${matterId}/export`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function fetchMatterAudit(matterId: string) {
  return apiFetch<{ audit: Array<Record<string, string>> }>(
    `/api/v1/matters/${matterId}/audit`
  );
}

export async function listMatterMembers(matterId: string) {
  return apiFetch<{ members: Array<Record<string, string>> }>(
    `/api/v1/matters/${matterId}/members`
  );
}

export async function addMatterMember(matterId: string, userId: string, role: string) {
  return apiFetch<Record<string, string>>(`/api/v1/matters/${matterId}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, role }),
  });
}

export async function patchMatterDocumentMeta(
  matterId: string,
  documentId: string,
  privileged: boolean
) {
  return apiFetch<{ updated: boolean }>(
    `/api/v1/matters/${matterId}/documents/${documentId}?privileged=${privileged}`,
    { method: "PATCH" }
  );
}

export async function uploadMatterDocument(matterId: string, file: File, ocr = true) {
  const fd = new FormData();
  fd.append("file", file);
  const ocrQ = ocr ? "1" : "0";
  return apiFetch<MatterDocumentUploadResponse>(
    `/api/v1/matters/${matterId}/documents/upload?ocr=${ocrQ}`,
    { method: "POST", body: fd }
  );
}

export async function listClauses(practice_area = "", tag = "") {
  const params = new URLSearchParams();
  if (practice_area) params.set("practice_area", practice_area);
  if (tag) params.set("tag", tag);
  const q = params.toString() ? `?${params}` : "";
  return apiFetch<{
    clauses: Array<{
      clause_id: string;
      clause_tag: string;
      practice_area: string;
      clause_text_content: string;
    }>;
  }>(`/api/v1/clauses${q}`);
}

export async function listSmartDraftTypes() {
  return apiFetch<{ types: Array<{ id: string; label: string; question_count: number }> }>(
    "/api/v1/drafting/smart-draft/types"
  );
}

export async function getSmartDraftQuestions(draftType: string) {
  return apiFetch<{
    draft_type: string;
    label: string;
    questions: Array<{ id: string; label: string; required?: boolean }>;
  }>(`/api/v1/drafting/smart-draft/${encodeURIComponent(draftType)}/questions`);
}

export async function generateSmartDraft(
  draftType: string,
  answers: Record<string, string>,
  useAiPolish = false
) {
  return apiFetch<{ rendered: string; missing_variables?: string[] }>(
    "/api/v1/drafting/smart-draft/generate",
    {
      method: "POST",
      body: JSON.stringify({ draft_type: draftType, answers, use_ai_polish: useAiPolish }),
    }
  );
}

export type WorkspaceDocument = {
  draft_id: string;
  title: string;
  document_type: string;
  status: string;
  content?: string;
  content_format?: "html" | "markdown";
  matter_id?: string;
  jurisdiction?: string;
  objectives?: string;
  instructions?: string;
  parties?: Record<string, string>;
  pinned?: boolean;
  version_count?: number;
  created_at?: string;
  updated_at?: string;
};

export async function draftingDashboard() {
  return apiFetch<{
    recent_documents: WorkspaceDocument[];
    pinned_documents: WorkspaceDocument[];
    counts: Record<string, unknown>;
    workflow_statuses: string[];
    document_types: Array<{ id: string; label: string; category: string }>;
  }>("/api/v1/drafting/workspace/dashboard");
}

export async function listWorkspaceDocuments(params?: {
  q?: string;
  status?: string;
  document_type?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  if (params?.status) qs.set("status", params.status);
  if (params?.document_type) qs.set("document_type", params.document_type);
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiFetch<{ documents: WorkspaceDocument[] }>(
    `/api/v1/drafting/workspace/documents${suffix}`
  );
}

export async function getWorkspaceDocument(draftId: string) {
  return apiFetch<{
    document: WorkspaceDocument;
    versions: Array<{ version_number: number; change_summary: string; created_at: string }>;
    comments: Array<{ comment_id: string; author_name: string; body: string; created_at: string }>;
  }>(`/api/v1/drafting/workspace/documents/${draftId}`);
}

export async function createWorkspaceDocument(body: Partial<WorkspaceDocument>) {
  return apiFetch<{ document: WorkspaceDocument }>("/api/v1/drafting/workspace/documents", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateWorkspaceDocument(
  draftId: string,
  body: Partial<WorkspaceDocument> & { change_summary?: string }
) {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
}

export async function deleteWorkspaceDocument(draftId: string) {
  return apiFetch<{ ok: boolean }>(`/api/v1/drafting/workspace/documents/${draftId}`, {
    method: "DELETE",
  });
}

export async function aiGenerateWorkspaceDocument(body: {
  document_type: string;
  parties: Record<string, string>;
  facts: string;
  jurisdiction: string;
  objectives: string;
  instructions?: string;
  use_polish?: boolean;
}) {
  return apiFetch<{ document: WorkspaceDocument; sources: string[] }>(
    "/api/v1/drafting/workspace/ai/generate",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function reviewWorkspaceDocument(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/review`,
    { method: "POST", body: "{}" }
  );
}

export async function assistWorkspaceDocument(
  draftId: string,
  action: string,
  selection: string,
  instruction?: string
) {
  return apiFetch<{ result: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/ai/assist`,
    {
      method: "POST",
      body: JSON.stringify({ action, selection, instruction: instruction || "" }),
    }
  );
}

export async function compareWorkspaceVersions(
  draftId: string,
  versionA: number,
  versionB: number
) {
  return apiFetch<{ diff_html: string; diff_markdown: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/compare?version_a=${versionA}&version_b=${versionB}`
  );
}

export async function restoreWorkspaceVersion(draftId: string, versionNumber: number) {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}/restore/${versionNumber}`,
    { method: "POST", body: "{}" }
  );
}

export async function addWorkspaceComment(draftId: string, body: string, authorName = "") {
  return apiFetch<{ comment_id: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/comments`,
    { method: "POST", body: JSON.stringify({ body, author_name: authorName }) }
  );
}

export async function draftingMatterVariables(matterId: string) {
  return apiFetch<{ variables: Record<string, string> }>(
    `/api/v1/drafting/workspace/v3/matters/${matterId}/variables`
  );
}

export async function autofillWorkspaceDocument(draftId: string) {
  return apiFetch<{ document: WorkspaceDocument; variables: Record<string, string> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/autofill`,
    { method: "POST", body: "{}" }
  );
}

export async function getWorkspaceInsights(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/insights`
  );
}

export async function getWorkspaceClauseIntel(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/clause-intel`
  );
}

export async function transitionWorkspaceStatus(draftId: string, status: string) {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}/status`,
    { method: "POST", body: JSON.stringify({ status }) }
  );
}

export async function draftingWorkspaceSearch(q: string) {
  return apiFetch<{
    documents: WorkspaceDocument[];
    clauses: Array<{ clause_id: string; clause_tag: string }>;
    templates: Array<{ template_id: string; template_name: string }>;
    comments: Array<{ comment_id: string; draft_id: string; body: string }>;
  }>(`/api/v1/drafting/workspace/v3/search?q=${encodeURIComponent(q)}`);
}

export async function listDraftingV3Templates() {
  return apiFetch<{
    templates: Array<{ template_id: string; template_name: string; practice_area: string; source: string }>;
  }>("/api/v1/drafting/workspace/v3/templates");
}

export async function createFromDraftingTemplate(body: {
  template_id: string;
  matter_id?: string;
  title?: string;
  variables?: Record<string, string>;
}) {
  return apiFetch<{ document: WorkspaceDocument }>(
    "/api/v1/drafting/workspace/v3/templates/create-document",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function copilotWorkspaceDocument(
  draftId: string,
  command: string,
  selection?: string,
  instruction?: string
) {
  const out = await apiFetch<{ result?: string; sources?: string[]; error?: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/copilot`,
    {
      method: "POST",
      body: JSON.stringify({ command, selection: selection || "", instruction: instruction || "" }),
    }
  );
  if (out.error) throw new Error(out.error);
  return { result: out.result || "", sources: out.sources };
}

export async function compareWorkspaceVersionsV3(
  draftId: string,
  versionA: number,
  versionB: number
) {
  return apiFetch<{
    diff_html: string;
    side_by_side_html: string;
    risk_delta: number;
    clause_changes: string[];
  }>(
    `/api/v1/drafting/workspace/documents/${draftId}/compare-v3?version_a=${versionA}&version_b=${versionB}`
  );
}

export async function saveWorkspaceContent(
  draftId: string,
  body: {
    content: string;
    content_format: "html" | "markdown";
    matter_id?: string;
    title?: string;
    status?: string;
    change_summary?: string;
  }
) {
  return apiFetch<{ document: WorkspaceDocument; billing?: Record<string, unknown> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/content`,
    {
      method: "PATCH",
      body: JSON.stringify({ ...body, change_summary: body.change_summary || "Editor save" }),
    }
  );
}

export async function exportWorkspaceDocumentV3(
  draftId: string,
  format: string,
  opts?: { watermark?: string; signature_blocks?: boolean }
) {
  const token = getToken();
  const res = await fetch(
    `${API_BASE}/api/v1/drafting/workspace/documents/${draftId}/export-v3`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        format,
        watermark: opts?.watermark || "",
        signature_blocks: opts?.signature_blocks ?? false,
      }),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    let msg = text || `Export failed (${res.status})`;
    try {
      const j = JSON.parse(text) as { detail?: string | Array<{ msg?: string }> };
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => d.msg || "").filter(Boolean).join("; ");
    } catch {
      /* plain text error */
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disp);
  return { blob, filename: match?.[1] || `document.${format}` };
}

export async function draftingControlCenter(matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{
    matter_id?: string;
    columns: Record<string, WorkspaceDocument[]>;
    counts: Record<string, number>;
    awaiting_action: Array<Record<string, unknown>>;
    reviewer_queue: Array<Record<string, unknown>>;
    near_deadline: Array<Record<string, unknown>>;
    recent_activity: Array<Record<string, unknown>>;
    health_score_avg: number;
    analytics: Record<string, unknown>;
  }>(`/api/v1/drafting/workspace/v4/control-center${q}`);
}

export async function linkDraftToHearing(draftId: string, hearingId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/link-hearing`,
    { method: "POST", body: JSON.stringify({ hearing_id: hearingId }) }
  );
}

export async function syncDraftToLitigation(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/sync-litigation`,
    { method: "POST", body: "{}" }
  );
}

export async function listDraftLinks(draftId: string) {
  return apiFetch<{ links: Array<Record<string, unknown>> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/links`
  );
}

export async function logDraftBillingSession(draftId: string, force = false) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/billing-session?force=${force}`,
    { method: "POST", body: "{}" }
  );
}

export async function transitionWorkspaceLifecycle(draftId: string, status: string) {
  return apiFetch<{ document: WorkspaceDocument; litigation_sync?: Record<string, unknown> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/transition?status=${encodeURIComponent(status)}`,
    { method: "POST", body: "{}" }
  );
}

export async function searchPrecedents(q: string) {
  return apiFetch<{ results: Array<Record<string, unknown>>; query: string }>(
    `/api/v1/drafting/workspace/v4/precedents/search?q=${encodeURIComponent(q)}`
  );
}

export async function matterDraftingHub(matterId: string) {
  return apiFetch<{
    matter_id: string;
    documents: Array<{
      draft_id: string;
      title: string;
      status: string;
      version_count: number;
      filing_readiness_score?: number;
    }>;
    by_status: Record<string, unknown[]>;
    timeline: Array<Record<string, unknown>>;
  }>(`/api/v1/drafting/workspace/v4/matters/${matterId}/drafting`);
}

export async function createMatterDraft(
  matterId: string,
  body: { title?: string; document_type?: string; template_id?: string }
) {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/v4/matters/${matterId}/drafts`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function matterCourtBundle(matterId: string) {
  return apiFetch<{ documents: WorkspaceDocument[]; matter_id: string }>(
    `/api/v1/drafting/workspace/v4/matters/${matterId}/court-bundle`,
    { method: "POST", body: "{}" }
  );
}

export async function downloadCourtPackage(matterId: string, draftIds: string[]) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/drafting/workspace/v4/court-package`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ matter_id: matterId, draft_ids: draftIds, include_cover: true }),
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disp);
  return { blob, filename: match?.[1] || "court_package.zip" };
}

export async function getFilingReadiness(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/filing-readiness`
  );
}

export async function getReviewWorkspace(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/review-workspace`
  );
}

export async function getDraftTimeline(draftId: string) {
  return apiFetch<{ events: Array<Record<string, unknown>> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/timeline`
  );
}

export async function assignDraftReviewer(
  draftId: string,
  assigneeUserId: string,
  assigneeName: string,
  dueDate: string
) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/assign`,
    {
      method: "POST",
      body: JSON.stringify({
        assignee_user_id: assigneeUserId,
        assignee_name: assigneeName,
        due_date: dueDate,
        role: "reviewer",
      }),
    }
  );
}

export async function addReviewSuggestion(draftId: string, body: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/suggestions`,
    { method: "POST", body: JSON.stringify({ body }) }
  );
}

export async function resolveSuggestion(draftId: string, suggestionId: string, accept: boolean) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/suggestions/${suggestionId}/resolve?accept=${accept}`,
    { method: "POST", body: "{}" }
  );
}

export async function promoteToPrecedent(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/promote-precedent`,
    { method: "POST", body: "{}" }
  );
}

export async function draftLock(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/lock`,
    { method: "POST", body: "{}" }
  );
}

export async function draftUnlock(draftId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/lock`,
    { method: "DELETE" }
  );
}

export async function draftPresenceHeartbeat(draftId: string) {
  return apiFetch<{ editors: Array<{ user_id: string; user_name: string }>; lock: Record<string, unknown> | null }>(
    `/api/v1/drafting/workspace/documents/${draftId}/presence/heartbeat`,
    { method: "POST", body: "{}" }
  );
}

export async function addDraftAnnexure(draftId: string, label: string, content: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/annexures`,
    { method: "POST", body: JSON.stringify({ label, content }) }
  );
}

export async function getCollaborationHub(draftId: string) {
  return apiFetch<{
    document: WorkspaceDocument;
    track_changes: Array<Record<string, unknown>>;
    assignments: Array<Record<string, unknown>>;
    annexures: Array<{ annexure_id: string; label: string; content: string }>;
    timeline: Array<Record<string, unknown>>;
    pending_changes: number;
  }>(`/api/v1/drafting/workspace/documents/${draftId}/collaboration-hub`);
}

export async function listTrackChanges(draftId: string) {
  return apiFetch<{ changes: Array<Record<string, unknown>> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/track-changes`
  );
}

export async function addTrackChange(
  draftId: string,
  body: { original_text: string; suggested_text: string; change_type?: string; author_name?: string }
) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/track-changes`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function resolveTrackChange(draftId: string, changeId: string, accept: boolean) {
  return apiFetch<{ document?: WorkspaceDocument; ok?: boolean }>(
    `/api/v1/drafting/workspace/documents/${draftId}/track-changes/${changeId}/resolve?accept=${accept}`,
    { method: "POST", body: "{}" }
  );
}

export async function listDraftAssignments(draftId: string) {
  return apiFetch<{ assignments: Array<Record<string, unknown>> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/assignments`
  );
}

export async function updateAssignmentStatus(draftId: string, assignmentId: string, status: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/drafting/workspace/documents/${draftId}/assignments/${assignmentId}`,
    { method: "PATCH", body: JSON.stringify({ status }) }
  );
}

export async function sendPartnerReview(draftId: string) {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}/partner-review`,
    { method: "POST", body: "{}" }
  );
}

export async function partnerApproveDraft(draftId: string, note = "") {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}/partner-approve`,
    { method: "POST", body: JSON.stringify({ note }) }
  );
}

export async function partnerRevisionDraft(draftId: string, note = "") {
  return apiFetch<{ document: WorkspaceDocument }>(
    `/api/v1/drafting/workspace/documents/${draftId}/partner-revision`,
    { method: "POST", body: JSON.stringify({ note }) }
  );
}

export async function compareDraftPrecedent(draftId: string, precedentId: string) {
  return apiFetch<{
    similarity_score: number;
    diff_html: string;
    precedent_title: string;
    precedent_excerpt: string;
  }>(
    `/api/v1/drafting/workspace/documents/${draftId}/compare-precedent?precedent_id=${encodeURIComponent(precedentId)}`
  );
}

export async function insertDocumentToc(draftId: string) {
  return apiFetch<{ document: WorkspaceDocument; toc_html: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/insert-toc`,
    { method: "POST", body: "{}" }
  );
}

export async function insertAnnexureIndex(draftId: string) {
  return apiFetch<{ document: WorkspaceDocument; index_html: string }>(
    `/api/v1/drafting/workspace/documents/${draftId}/insert-annexure-index`,
    { method: "POST", body: "{}" }
  );
}

export async function listDraftAnnexures(draftId: string) {
  return apiFetch<{ annexures: Array<{ annexure_id: string; label: string; content: string }> }>(
    `/api/v1/drafting/workspace/documents/${draftId}/annexures`
  );
}

export async function exportWorkspaceDocument(draftId: string, format: string) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/drafting/workspace/documents/${draftId}/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ format }),
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disp);
  return { blob, filename: match?.[1] || `document.${format}` };
}

const CRM_TIMEOUT_MS = 90000;

export async function convertLeadToMatter(leadId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/crm/${leadId}/convert`,
    { method: "POST" },
    CRM_TIMEOUT_MS
  );
}

export type CrmPermissions = {
  view: boolean;
  create: boolean;
  edit: boolean;
  convert: boolean;
  reject: boolean;
  analytics: boolean;
  assign: boolean;
  notes_only: boolean;
};

export type CrmLead = Record<string, unknown>;

export async function fetchCrmPermissions() {
  return apiFetch<CrmPermissions>("/api/v1/crm/permissions", {}, CRM_TIMEOUT_MS);
}

export async function fetchCrmDashboard() {
  return apiFetch<{
    kpis: Record<string, number>;
    funnel: Array<{ stage: string; count: number }>;
    stages: string[];
  }>("/api/v1/crm/dashboard", {}, CRM_TIMEOUT_MS);
}

export type CrmCommandCenter = {
  kpis: Record<string, number>;
  funnel: Array<{ stage: string; count: number }>;
  stages: string[];
  stage_labels: Record<string, string>;
  pipeline_value: {
    active_pipeline_inr: number;
    converted_inr: number;
    total_inr: number;
    by_stage: Array<{ stage: string; label: string; count: number; value_inr: number }>;
  };
  urgent_leads: Array<Record<string, unknown>>;
  recent_activity: Array<Record<string, unknown>>;
  follow_ups: {
    due_today: Array<Record<string, unknown>>;
    overdue: Array<Record<string, unknown>>;
    upcoming: Array<Record<string, unknown>>;
    overdue_count: number;
  };
  lead_sources: Array<{ source: string; count: number }>;
  latest_ai: Record<string, unknown> | null;
  ai_recommendations: Array<{ title: string; body: string; lead_id: string }>;
  kanban_preview: {
    columns: Record<string, number>;
    stages: string[];
    samples: Record<string, Array<Record<string, unknown>>>;
  };
  public_portal: {
    enabled?: boolean;
    public_url?: string;
    slug?: string;
    submissions_count?: number;
    last_submission_at?: string;
    setup_note?: string;
  };
  has_leads: boolean;
};

export async function fetchCrmCommandCenter() {
  return apiFetch<CrmCommandCenter>("/api/v1/crm/command-center", {}, CRM_TIMEOUT_MS);
}

export async function fetchCrmKanban() {
  return apiFetch<{
    columns: Record<string, CrmLead[]>;
    stages: string[];
    metrics?: Record<string, number>;
    empty_hints?: Record<string, string>;
  }>("/api/v1/crm/kanban", {}, CRM_TIMEOUT_MS);
}

export async function fetchCrmAnalytics() {
  return apiFetch<Record<string, unknown>>("/api/v1/crm/analytics", {}, CRM_TIMEOUT_MS);
}

export async function fetchCrmPipelineStages() {
  return apiFetch<{ stages: string[]; labels: Record<string, string>; empty_hints?: Record<string, string> }>(
    "/api/v1/crm/pipeline-stages",
    {},
    CRM_TIMEOUT_MS
  );
}

export async function getCrmLead(leadId: string) {
  return apiFetch<CrmLead>(`/api/v1/crm/${leadId}`, {}, CRM_TIMEOUT_MS);
}

export async function createCrmLead(body: Record<string, string>) {
  return apiFetch<CrmLead>(
    "/api/v1/crm",
    { method: "POST", body: JSON.stringify(body) },
    CRM_TIMEOUT_MS
  );
}

export async function patchCrmLead(leadId: string, body: Record<string, string>) {
  return apiFetch<CrmLead>(`/api/v1/crm/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function patchCrmLeadStage(leadId: string, stage: string, note = "") {
  return apiFetch<CrmLead>(
    `/api/v1/crm/${leadId}/stage`,
    {
      method: "PATCH",
      body: JSON.stringify({ stage, note }),
    },
    CRM_TIMEOUT_MS
  );
}

export async function analyzeCrmLead(leadId: string) {
  return apiFetch<CrmLead>(
    `/api/v1/crm/${leadId}/analyze`,
    { method: "POST" },
    CRM_TIMEOUT_MS
  );
}

export async function listCrmLeadDocuments(leadId: string) {
  return apiFetch<{ documents: Array<Record<string, unknown>> }>(
    `/api/v1/crm/${leadId}/documents`
  );
}

export async function uploadCrmLeadDocument(
  leadId: string,
  file: File,
  docKind = "document"
) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("doc_kind", docKind);
  return apiFetch<Record<string, unknown>>(
    `/api/v1/crm/${leadId}/documents`,
    { method: "POST", body: fd },
    CRM_TIMEOUT_MS
  );
}

export async function listCrmInteractions(leadId: string) {
  return apiFetch<{ interactions: Array<Record<string, unknown>> }>(
    `/api/v1/crm/${leadId}/interactions`
  );
}

export async function addCrmInteraction(
  leadId: string,
  body: { interaction_type?: string; title?: string; body?: string }
) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/crm/${leadId}/interactions`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    CRM_TIMEOUT_MS
  );
}

export async function listCrmAudit(leadId: string) {
  return apiFetch<{ audit: Array<Record<string, unknown>> }>(
    `/api/v1/crm/${leadId}/audit`
  );
}

export async function previewCrmConversion(leadId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/crm/${leadId}/convert/preview`,
    { method: "POST" },
    CRM_TIMEOUT_MS
  );
}

export async function rejectCrmLead(leadId: string, reason: string) {
  return apiFetch<CrmLead>(`/api/v1/crm/${leadId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function archiveCrmLead(leadId: string) {
  return apiFetch<CrmLead>(`/api/v1/crm/${leadId}/archive`, { method: "POST" });
}

export async function fetchCrmFollowUpTemplates(leadId: string) {
  return apiFetch<{
    templates: Array<{
      template_id: string;
      name: string;
      subject: string;
      body_template: string;
      template_type: string;
    }>;
  }>(`/api/v1/crm/${leadId}/follow-up/templates`);
}

export async function applyCrmFollowUpTemplate(leadId: string, templateId: string) {
  return apiFetch<{ draft: string; subject: string }>(
    `/api/v1/crm/${leadId}/follow-up/apply`,
    {
      method: "POST",
      body: JSON.stringify({ template_id: templateId }),
    }
  );
}

export async function crmFollowUpPreview(leadId: string, prospectName = "Client") {
  return apiFetch<{ draft: string }>(
    `/api/v1/crm/${leadId}/follow-up/preview?prospect_name=${encodeURIComponent(prospectName)}`,
    { method: "POST" }
  );
}

export async function crmFollowUpSend(
  leadId: string,
  body: { subject?: string; body?: string; template_type?: string }
) {
  return apiFetch<{ ok: boolean; draft: string }>(
    `/api/v1/crm/${leadId}/follow-up/send`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function crmAssistant(leadId: string, action: string) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/crm/assistant",
    {
      method: "POST",
      body: JSON.stringify({ lead_id: leadId, action }),
    },
    CRM_TIMEOUT_MS
  );
}

export async function submitPublicIntake(
  body: Record<string, string>,
  intakeKey = ""
) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (intakeKey) headers["X-Intake-Key"] = intakeKey;
  return apiFetch<Record<string, unknown>>("/api/v1/practice/public-intake", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

export type DocTemplate = {
  template_id: string;
  template_name: string;
  practice_area: string;
  variables?: string[];
  raw_markdown_structure?: string;
};

export async function listDocTemplates(practice_area = "") {
  const q = practice_area ? `?practice_area=${encodeURIComponent(practice_area)}` : "";
  return apiFetch<{ templates: DocTemplate[] }>(`/api/v1/templates${q}`);
}

export async function generateFromTemplate(
  templateId: string,
  variables: Record<string, string>
) {
  return apiFetch<{ rendered: string; missing_variables: string[] }>(
    `/api/v1/templates/${templateId}/generate`,
    { method: "POST", body: JSON.stringify({ variables }) }
  );
}

export async function clauseFeedback(body: {
  baseline: string;
  accepted: string;
  clause_tag?: string;
  practice_area?: string;
  signal?: number;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/clauses/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------- Phase 2: Billing ----------

export async function billingSummary() {
  return apiFetch<{
    unbilled_amount_inr: number;
    unbilled_entries: number;
    invoiced_total_inr: number;
    invoice_count: number;
  }>("/api/v1/billing/summary");
}

export async function logBillingEntry(body: {
  matter_id: string;
  raw_activity: string;
  units_logged: number;
  rate_per_unit: number;
  billing_type?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/billing/entries", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function previewBillingNarrative(body: {
  raw_activity: string;
  units_logged?: number;
  matter_id?: string;
}) {
  return apiFetch<{ narrative: string }>("/api/v1/billing/narrative/preview", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function correctBillingNarrative(raw_activity: string, polished_narrative: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/billing/narrative/correct", {
    method: "POST",
    body: JSON.stringify({ raw_activity, polished_narrative }),
  });
}

export async function createInvoice(body: {
  matter_id: string;
  client_name?: string;
  tax_rate?: number;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/billing/invoices", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type InvoicePayload = Record<string, unknown>;
export type InvoiceRecord = {
  invoice_id: string;
  invoice_number?: string;
  matter_id: string;
  client_name: string;
  status: string;
  total: number;
  balance_due?: number;
  invoice_date?: string;
  due_date?: string;
  payload?: InvoicePayload;
  totals?: Record<string, number>;
};

export async function prefillInvoice(matter_id: string) {
  return apiFetch<{ payload: InvoicePayload; matter_id: string }>(
    `/api/v1/billing/invoices/prefill?matter_id=${encodeURIComponent(matter_id)}`
  );
}

export async function listInvoices(matter_id = "", status = "") {
  const params = new URLSearchParams();
  if (matter_id) params.set("matter_id", matter_id);
  if (status) params.set("status", status);
  const q = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ invoices: InvoiceRecord[] }>(`/api/v1/billing/invoices${q}`);
}

export async function getInvoice(invoice_id: string) {
  return apiFetch<InvoiceRecord>(`/api/v1/billing/invoices/${encodeURIComponent(invoice_id)}`);
}

export async function saveInvoiceDraft(body: {
  payload: InvoicePayload;
  invoice_id?: string;
  status?: string;
}) {
  return apiFetch<InvoiceRecord>("/api/v1/billing/invoices/draft", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateInvoice(invoice_id: string, body: { payload: InvoicePayload; status?: string }) {
  return apiFetch<InvoiceRecord>(`/api/v1/billing/invoices/${encodeURIComponent(invoice_id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function finalizeInvoice(invoice_id: string) {
  return apiFetch<InvoiceRecord>(`/api/v1/billing/invoices/${encodeURIComponent(invoice_id)}/finalize`, {
    method: "POST",
  });
}

export async function patchInvoiceStatus(invoice_id: string, status: string) {
  return apiFetch<InvoiceRecord>(`/api/v1/billing/invoices/${encodeURIComponent(invoice_id)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function computeInvoiceTotals(payload: InvoicePayload) {
  return apiFetch<{ totals: Record<string, number> }>("/api/v1/billing/invoices/compute-totals", {
    method: "POST",
    body: JSON.stringify({ payload }),
  });
}

export async function downloadInvoicePdf(invoice_id: string): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithRetry(
    `/api/v1/billing/invoices/${encodeURIComponent(invoice_id)}/pdf`,
    { headers },
    60000
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "PDF download failed"));
  }
  return res.blob();
}

export async function listBillingEntries(matter_id = "") {
  const q = matter_id ? `?matter_id=${encodeURIComponent(matter_id)}` : "";
  return apiFetch<{ entries: Array<Record<string, unknown>> }>(`/api/v1/billing/entries${q}`);
}

export type MatterBillingProfile = {
  matter_id: string;
  client_name: string;
  client_email: string;
  client_phone: string;
  client_address: string;
  client_gst: string;
  client_company: string;
  matter_name: string;
  matter_number: string;
  case_number: string;
  court_name: string;
  assigned_lawyer: string;
  retainer_balance: number;
  operating_balance: number;
  outstanding_balance: number;
  total_billed: number;
  total_collected: number;
  hours_logged: number;
  unbilled_amount: number;
  expense_total: number;
};

export type BillingWorkspaceData = {
  summary: Record<string, number>;
  profile: MatterBillingProfile;
  entries: Array<Record<string, unknown>>;
  expenses: Array<Record<string, unknown>>;
  invoices: InvoiceRecord[];
  matter_financials: Record<string, unknown>;
  expense_types: string[];
};

export async function fetchBillingWorkspace(matter_id: string) {
  const q = matter_id ? `?matter_id=${encodeURIComponent(matter_id)}` : "";
  return apiFetch<BillingWorkspaceData>(`/api/v1/billing/workspace${q}`);
}

export async function updateBillingEntry(
  record_id: string,
  body: {
    raw_activity?: string;
    units_logged?: number;
    rate_per_unit?: number;
    narrative_description?: string;
  }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/billing/entries/${encodeURIComponent(record_id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteBillingEntry(record_id: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/billing/entries/${encodeURIComponent(record_id)}`, {
    method: "DELETE",
  });
}

export async function duplicateBillingEntry(record_id: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/billing/entries/${encodeURIComponent(record_id)}/duplicate`,
    { method: "POST" }
  );
}

export async function bulkImportBillingEntries(
  entries: Array<{
    matter_id: string;
    raw_activity?: string;
    units_logged?: number;
    rate_per_unit?: number;
  }>
) {
  return apiFetch<{ created: number; record_ids: string[]; errors: unknown[] }>(
    "/api/v1/billing/entries/bulk",
    { method: "POST", body: JSON.stringify({ entries }) }
  );
}

export async function listBillingExpenses(matter_id = "") {
  const q = matter_id ? `?matter_id=${encodeURIComponent(matter_id)}` : "";
  return apiFetch<{ expenses: Array<Record<string, unknown>>; expense_types: string[] }>(
    `/api/v1/billing/expenses${q}`
  );
}

export async function createBillingExpense(body: {
  matter_id: string;
  expense_date?: string;
  expense_type?: string;
  description: string;
  amount: number;
  billable?: boolean;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/billing/expenses", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteBillingExpense(expense_id: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/billing/expenses/${encodeURIComponent(expense_id)}`, {
    method: "DELETE",
  });
}

export async function fetchBillingReport(report_type: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/billing/reports/${encodeURIComponent(report_type)}`);
}

export async function saveMatterBillingProfile(
  matter_id: string,
  body: Partial<MatterBillingProfile> & { payment?: Record<string, string> }
) {
  return apiFetch<MatterBillingProfile>(`/api/v1/billing/matter/${encodeURIComponent(matter_id)}/profile`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ---------- Phase 3: CRM (legacy helpers) ----------

export async function listLeads(stage = "") {
  const q = stage ? `?stage=${encodeURIComponent(stage)}` : "";
  return apiFetch<{ leads: Array<Record<string, unknown>> }>(
    `/api/v1/crm${q}`,
    {},
    CRM_TIMEOUT_MS
  );
}

export async function classifyIntake(query: string) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/crm/classify",
    {
      method: "POST",
      body: JSON.stringify({ query }),
    },
    CRM_TIMEOUT_MS
  );
}

export async function createLead(body: {
  prospect_name: string;
  contact_email: string;
  raw_intake_query: string;
  contact_phone?: string;
}) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/crm",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    CRM_TIMEOUT_MS
  );
}

export async function updateLead(leadId: string, body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>(`/api/v1/crm/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function correctCrmIntent(body: {
  raw_query: string;
  corrected_intent: string;
  original_intent?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/crm/intent/correct", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------- Phase 4: E-discovery & research ----------

// ---------- Evidence Intelligence Center ----------

export type EvidenceStrength = {
  score?: number;
  percent?: number;
  label?: string;
  classification?: string;
  tags?: string[];
  rationale?: string;
};

export type EvidenceEntities = {
  people?: string[];
  organizations?: string[];
  locations?: string[];
  dates?: string[];
  emails?: string[];
  phones?: string[];
  bank_accounts?: string[];
  ifsc_codes?: string[];
  case_numbers?: string[];
};

export type EvidenceAnalysis = {
  classification?: { primary_category?: string; categories?: string[]; category_labels?: string[] };
  evidence_strength?: EvidenceStrength;
  risks?: Array<{ code?: string; description?: string; confidence?: number }>;
  privilege?: { privileged?: boolean; flags?: Array<{ type?: string; description?: string }>; recommendation?: string };
  entities?: EvidenceEntities;
  timeline?: Array<{ date_raw?: string; date_iso?: string; event?: string; source?: string }>;
  statutes?: Array<{ offence?: string; section?: string; act?: string; relevance?: string }>;
  excerpt?: string;
  metadata?: Record<string, unknown>;
};

export type EvidenceItem = {
  item_id?: string;
  source_identifier?: string;
  relevance_score?: number;
  classification?: string;
  tags?: string[];
  category?: string;
  evidence_strength?: EvidenceStrength;
  entities?: EvidenceEntities;
  timeline?: EvidenceAnalysis["timeline"];
  statutes?: EvidenceAnalysis["statutes"];
  privilege?: EvidenceAnalysis["privilege"];
  risks?: EvidenceAnalysis["risks"];
  metadata?: Record<string, unknown>;
  matter_id?: string;
  batch_title?: string;
  excerpt?: string;
  created_at?: string;
};

export async function getEvidenceFormats() {
  return apiFetch<{ formats: string[] }>("/api/v1/ediscovery/evidence/formats");
}

export async function uploadEvidence(file: File, matter_id: string, batch_title = "") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("matter_id", matter_id);
  if (batch_title) fd.append("batch_title", batch_title);
  return apiFetch<Record<string, unknown>>(
    "/api/v1/ediscovery/evidence/upload",
    { method: "POST", body: fd },
    LONG_TIMEOUT_MS
  );
}

export async function getEvidenceRepository(matter_id = "", limit = 100) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (matter_id) q.set("matter_id", matter_id);
  return apiFetch<{ items: EvidenceItem[]; count: number; timeline: EvidenceAnalysis["timeline"] }>(
    `/api/v1/ediscovery/evidence/repository?${q}`
  );
}

export async function getEvidenceTimeline(matter_id: string) {
  return apiFetch<{ timeline: EvidenceAnalysis["timeline"] }>(
    `/api/v1/ediscovery/evidence/timeline?matter_id=${encodeURIComponent(matter_id)}`
  );
}

export async function detectEvidenceContradictions(body: {
  document_a: string;
  document_b: string;
  label_a?: string;
  label_b?: string;
}) {
  return apiFetch<{ contradictions: Array<Record<string, string>>; summary: string }>(
    "/api/v1/ediscovery/evidence/contradictions",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function findEvidenceStatutes(text: string, matter_id = "") {
  return apiFetch<{ statutes: EvidenceAnalysis["statutes"]; count: number }>(
    "/api/v1/ediscovery/evidence/statutes",
    { method: "POST", body: JSON.stringify({ text, matter_id }) }
  );
}

export async function matchEvidenceCourtOrders(text: string, matter_id = "") {
  return apiFetch<{ results: Array<Record<string, unknown>>; count: number }>(
    "/api/v1/ediscovery/evidence/court-orders",
    { method: "POST", body: JSON.stringify({ text, matter_id }) }
  );
}

export async function triageDiscovery(text: string, matter_id = "") {
  return apiFetch<{ triage: Record<string, unknown>; analysis: EvidenceAnalysis }>(
    "/api/v1/ediscovery/triage",
    { method: "POST", body: JSON.stringify({ text, matter_id }) }
  );
}

export async function createDiscoveryBatch(body: {
  matter_id: string;
  batch_title: string;
  documents: Array<{ source_identifier: string; text: string }>;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/ediscovery/batches", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDiscoveryBatch(batchId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/ediscovery/batches/${batchId}`);
}

export async function reviewDiscoveryItem(
  itemId: string,
  body: { tags?: string[]; classification?: string; verified?: boolean }
) {
  return apiFetch<Record<string, unknown>>(`/api/v1/ediscovery/items/${itemId}/review`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function expandResearch(query: string, matter_id = "") {
  return apiFetch<Record<string, unknown>>("/api/v1/research/expand", {
    method: "POST",
    body: JSON.stringify({ query, matter_id }),
  });
}

export async function logResearch(query: string, mode = "KNOWLEDGE_BASE") {
  return apiFetch<Record<string, unknown>>("/api/v1/research/log", {
    method: "POST",
    body: JSON.stringify({ query, selected_mode: mode }),
  });
}

export async function piiRedact(text: string, enabled = true, types?: string[]) {
  return apiFetch<Record<string, unknown>>("/api/v1/ediscovery/pii/redact", {
    method: "POST",
    body: JSON.stringify({ text, enabled, types }),
  });
}

// ---------- Trust ledger ----------

export async function getTrustAccount(matter_id: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/trust/account?matter_id=${encodeURIComponent(matter_id)}`
  );
}

export async function listTrustTransactions(matter_id: string) {
  return apiFetch<{ transactions: Array<Record<string, unknown>> }>(
    `/api/v1/trust/transactions?matter_id=${encodeURIComponent(matter_id)}`
  );
}

export async function postTrustTransaction(body: {
  matter_id: string;
  ledger_type: string;
  txn_type: string;
  amount: number;
  narrative: string;
  reference_id?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/trust/transactions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------- Client portal ----------

export async function createPortalAccess(body: {
  matter_id: string;
  client_email: string;
  days_valid?: number;
}) {
  return apiFetch<{
    portal_token: string;
    portal_path: string;
    expires_at: string;
  }>("/api/v1/portal/access", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchPortalView(token: string) {
  const res = await fetchWithRetry(
    `/api/v1/portal/view/${encodeURIComponent(token)}`,
    {},
    15000
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : res.statusText);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function uploadPortalDocument(token: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetchWithRetry(
    `/api/v1/portal/upload/${encodeURIComponent(token)}`,
    { method: "POST", body: fd },
    60000
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : res.statusText);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function signPortalDocument(
  token: string,
  body: { signer_name?: string; intent?: string } = {}
) {
  const res = await fetchWithRetry(
    `/api/v1/portal/sign/${encodeURIComponent(token)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    15000
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : res.statusText);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

// ---------- E-signature ----------

export async function createSigningRequest(body: {
  document_title: string;
  document_body: string;
  signer_name: string;
  signer_email: string;
  matter_id?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/esign/requests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createDiscoveryJob(body: {
  matter_id: string;
  batch_title: string;
  documents: Array<{ source_identifier: string; text: string }>;
}) {
  return apiFetch<Record<string, unknown>>(
    "/api/v1/ediscovery/batches?async_job=true",
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
}

export async function getDiscoveryJob(jobId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/ediscovery/jobs/${jobId}`);
}

// ---------- Speech-to-text ----------

export type SpeechTranscribeResult = {
  text: string;
  language_detected?: string;
  language_requested?: string;
  engine?: string;
};

export class SpeechBrowserFallbackError extends Error {
  readonly fallback = "browser" as const;
  constructor(message = "Use browser speech recognition") {
    super(message);
    this.name = "SpeechBrowserFallbackError";
  }
}

export async function transcribeSpeech(
  audio: Blob,
  language: string,
  matterId?: string
): Promise<SpeechTranscribeResult> {
  const token = getToken();
  const fd = new FormData();
  fd.append("audio", audio, "recording.webm");
  fd.append("language", uiLangToCode(language));
  if (matterId) fd.append("matter_id", matterId);

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetchWithRetry(
    "/api/v1/speech/transcribe",
    { method: "POST", headers, body: fd },
    120000,
    1
  );

  const errBody = !res.ok
    ? ((await res.clone().json().catch(() => ({}))) as {
        detail?: { fallback?: string; message?: string } | string;
      })
    : null;

  const detail = errBody?.detail;
  const browserFallback =
    typeof detail === "object" &&
    detail &&
    detail.fallback === "browser";

  if (res.status === 503 || (res.status >= 500 && browserFallback)) {
    if (browserFallback) {
      throw new SpeechBrowserFallbackError(
        typeof detail === "object" && detail?.message
          ? detail.message
          : "Server STT unavailable"
      );
    }
    throw new Error(
      typeof detail === "string"
        ? detail
        : "Speech-to-text is temporarily unavailable."
    );
  }

  if (!res.ok) {
    throw new Error(await readResponseError(res, "Transcription failed"));
  }

  return res.json() as Promise<SpeechTranscribeResult>;
}

export async function polishSpeechText(text: string): Promise<{ text: string }> {
  return apiFetch<{ text: string }>("/api/v1/speech/polish", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function speechStatus() {
  return apiFetch<Record<string, unknown>>("/api/v1/speech/status");
}

export type HearingDigestItem = {
  hearing_id?: string;
  matter_id: string;
  matter_name: string;
  hearing_date: string;
  court_name?: string;
  purpose?: string;
  next_hearing_date?: string;
};

export async function fetchHearingDigest(daysAhead = 14) {
  return apiFetch<{
    today: HearingDigestItem[];
    this_week: HearingDigestItem[];
    upcoming: HearingDigestItem[];
    today_count?: number;
    week_count?: number;
  }>(`/api/v1/matters/hearings/digest?days_ahead=${daysAhead}`);
}

export async function fetchHearingPrepPack(matterId: string) {
  return apiFetch<{ markdown: string; sections?: Record<string, unknown> }>(
    `/api/v1/matters/${encodeURIComponent(matterId)}/hearing-prep-pack`
  );
}

export async function fetchClientStatusLetter(matterId: string) {
  return apiFetch<{ letter: string; subject?: string }>(
    `/api/v1/matters/${encodeURIComponent(matterId)}/client-status-letter`
  );
}

export async function importCauseList(matterId: string, text: string) {
  return apiFetch<{ ok: boolean; inserted?: number; hearings?: unknown[] }>(
    `/api/v1/matters/${encodeURIComponent(matterId)}/hearings/import-cause-list`,
    { method: "POST", body: JSON.stringify({ text }) }
  );
}

export async function hearingFromVoice(matterId: string, transcript: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/matters/${encodeURIComponent(matterId)}/hearings/from-voice`,
    { method: "POST", body: JSON.stringify({ transcript }) }
  );
}

export async function fetchAccountPreferences() {
  return apiFetch<{ profile: Record<string, unknown>; learner_mode: boolean }>(
    "/api/v1/account/preferences"
  );
}

export async function setLearnerMode(enabled: boolean) {
  return apiFetch<{ ok: boolean; learner_mode: boolean }>(
    "/api/v1/account/preferences/learner-mode",
    { method: "PATCH", body: JSON.stringify({ enabled }) }
  );
}

export type LimitationPreset = {
  id: string;
  label: string;
  days: number;
  description: string;
};

export async function fetchLimitationPresets() {
  return apiFetch<{ presets: LimitationPreset[] }>("/api/v1/practice/limitation/presets");
}

export async function calculateLimitation(presetId: string, startDate: string) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/limitation/calculate", {
    method: "POST",
    body: JSON.stringify({ preset_id: presetId, start_date: startDate }),
  });
}

export async function addLimitationToMatter(
  matterId: string,
  presetId: string,
  startDate: string,
  title = ""
) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/limitation/add-to-matter", {
    method: "POST",
    body: JSON.stringify({
      matter_id: matterId,
      preset_id: presetId,
      start_date: startDate,
      title,
    }),
  });
}

export type CourtDayRow = {
  row_index?: number;
  hearing_date?: string;
  court_name?: string;
  purpose?: string;
  suggested_matter_id?: string;
  suggested_matter_name?: string;
  matter_id?: string;
  match_score?: number;
  confidence?: string;
  selected?: boolean;
  alternatives?: Array<{ matter_id?: string; matter_name?: string; score?: number }>;
};

export async function parseCourtDayCauseList(text: string) {
  return apiFetch<{
    ok?: boolean;
    parsed_count?: number;
    parser?: string;
    rows?: CourtDayRow[];
    matters?: Array<{ matter_id: string; matter_name: string }>;
  }>(
    "/api/v1/practice/court-day/parse",
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
    LONG_TIMEOUT_MS
  );
}

export async function importCourtDayRows(rows: CourtDayRow[]) {
  return apiFetch<{ ok?: boolean; inserted?: number; skipped?: number; errors?: string[] }>(
    "/api/v1/practice/court-day/import",
    {
      method: "POST",
      body: JSON.stringify({ rows }),
    }
  );
}

export type CourtDayToday = {
  ok?: boolean;
  digest?: {
    today: HearingDigestItem[];
    this_week: HearingDigestItem[];
    upcoming: HearingDigestItem[];
  };
  summary?: { today_count?: number; week_count?: number; upcoming_count?: number };
};

export async function fetchCourtDayToday(daysAhead = 14) {
  return apiFetch<CourtDayToday>(
    `/api/v1/practice/court-day/today?days_ahead=${daysAhead}`
  );
}

// ---------- Litigation OS ----------

export type LitigationDashboard = {
  today_hearings: number;
  tomorrow_hearings?: number;
  this_week_hearings: number;
  upcoming_hearings: number;
  urgent_matters: number;
  high_risk_matters?: number;
  vip_clients: number;
  limitation_deadlines: number;
  limitation_critical: number;
  pending_tasks: number;
  evidence_pending: number;
  evidence_records?: number;
  evidence_pending_review?: number;
  affidavits_pending: number;
  court_appearances: number;
  drafts_pending: number;
  orders_awaiting_review?: number;
  active_matters: number;
  today_board?: HearingDigestItem[];
  tomorrow_board?: Array<Record<string, unknown>>;
  week_board?: HearingDigestItem[];
  upcoming_timeline?: Array<Record<string, unknown>>;
  recent_orders?: Array<Record<string, unknown>>;
  today_tasks?: Array<Record<string, unknown>>;
  urgent_alerts?: Array<{ type: string; message: string; matter_id: string; href_tab: string }>;
  vip_client_matters?: Array<{ matter_id: string; matter_name: string }>;
  high_risk_list?: Array<Record<string, unknown>>;
  lawyer_workload?: Array<{ lawyer: string; open_tasks: number }>;
  matter_health?: Array<{ matter_id: string; matter_name: string; score: number; factors: string[] }>;
};

export type LitigationDiagnostics = {
  ok?: boolean;
  overall_status?: string;
  table_counts?: Record<string, number>;
  modules?: Array<{ id: string; label: string; status: string; records?: number; note?: string }>;
  routes?: Record<string, string>;
  issues?: string[];
  warnings?: string[];
  last_sync?: { at?: string; mode?: string; status?: string };
  court_sync?: Record<string, unknown>;
  llm_health?: string;
  checks?: Record<string, string>;
};

export async function fetchLitigationDiagnostics() {
  return apiFetch<LitigationDiagnostics>("/api/v1/practice/litigation/diagnostics");
}

function mapCourtDayToDashboard(court: CourtDayToday & Record<string, unknown>, matterCount = 0, urgent = 0): LitigationDashboard {
  const digest = court.digest ?? { today: [], this_week: [], upcoming: [] };
  const today = (digest.today || court.today_board || []) as HearingDigestItem[];
  const week = (digest.this_week || court.week_board || []) as HearingDigestItem[];
  return {
    today_hearings: Number(court.today_hearings ?? court.summary?.today_count ?? today.length),
    this_week_hearings: Number(court.this_week_hearings ?? court.summary?.week_count ?? week.length),
    upcoming_hearings: Number(
      court.upcoming_hearings ?? court.summary?.upcoming_count ?? (digest.upcoming?.length || 0)
    ),
    urgent_matters: Number(court.urgent_matters ?? urgent),
    vip_clients: Number(court.vip_clients ?? 0),
    limitation_deadlines: Number(court.limitation_deadlines ?? 0),
    limitation_critical: Number(court.limitation_critical ?? 0),
    pending_tasks: Number(court.pending_tasks ?? 0),
    evidence_pending: Number(court.evidence_pending ?? 0),
    affidavits_pending: Number(court.affidavits_pending ?? 0),
    court_appearances: Number(court.court_appearances ?? today.length),
    drafts_pending: Number(court.drafts_pending ?? 0),
    active_matters: Number(court.active_matters ?? matterCount),
    today_board: today,
    week_board: week,
  };
}

export async function fetchLitigationDashboard() {
  try {
    return await apiFetch<LitigationDashboard>("/api/v1/practice/litigation/dashboard");
  } catch (e) {
    const msg = e instanceof Error ? e.message.toLowerCase() : "";
    if (!msg.includes("not found") && !msg.includes("404")) throw e;
  }
  try {
    const court = await apiFetch<CourtDayToday & Record<string, unknown>>(
      "/api/v1/practice/court-day/mission-control"
    );
    let urgent = 0;
    let matterCount = 0;
    try {
      const m = await listMatters();
      matterCount = m.matters?.length ?? 0;
      urgent = (m.matters || []).filter((x) =>
        ["high", "urgent", "critical"].includes(String(x.priority || "").toLowerCase())
      ).length;
    } catch {
      /* matters optional for fallback */
    }
    return mapCourtDayToDashboard(court, matterCount, urgent);
  } catch {
    const court = await fetchCourtDayToday(30);
    return mapCourtDayToDashboard(court as CourtDayToday & Record<string, unknown>);
  }
}

export async function fetchLitigationHearings(params?: {
  matter_id?: string;
  status?: string;
  from_date?: string;
  to_date?: string;
}) {
  const q = new URLSearchParams();
  if (params?.matter_id) q.set("matter_id", params.matter_id);
  if (params?.status) q.set("status", params.status);
  if (params?.from_date) q.set("from_date", params.from_date);
  if (params?.to_date) q.set("to_date", params.to_date);
  const qs = q.toString() ? `?${q.toString()}` : "";
  return apiFetch<{ hearings: Array<Record<string, unknown>> }>(`/api/v1/practice/litigation/hearings${qs}`);
}

export async function patchLitigationHearing(hearingId: string, body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/hearings/${encodeURIComponent(hearingId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function createLitigationHearing(body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/hearings", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchLitigationTask(taskId: string, body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteLitigationTask(taskId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
}

export async function patchLitigationOrder(orderId: string, body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/orders/${encodeURIComponent(orderId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteLitigationOrder(orderId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/orders/${encodeURIComponent(orderId)}`, {
    method: "DELETE",
  });
}

export async function fetchLitigationLimitationDeadlines() {
  return apiFetch<{ deadlines: Array<Record<string, unknown>> }>("/api/v1/practice/litigation/limitation/deadlines");
}

export async function fetchLitigationNotifications() {
  return apiFetch<{ notifications: Array<Record<string, unknown>>; unread_count: number }>(
    "/api/v1/practice/litigation/notifications"
  );
}

export async function fetchCourtSyncHistory(limit = 10) {
  return apiFetch<{ history: Array<Record<string, unknown>> }>(`/api/v1/practice/court-sync/history?limit=${limit}`);
}

export async function downloadCourtDayPrepPdf(matterId: string, useAi = true): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithRetry(
    `/api/v1/practice/court-day/prep/${encodeURIComponent(matterId)}/pdf?use_ai=${useAi ? "1" : "0"}`,
    { headers },
    120000
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "PDF download failed"));
  }
  return res.blob();
}

export async function fetchLitigationCalendar(year = 0, month = 0) {
  const q = new URLSearchParams();
  if (year) q.set("year", String(year));
  if (month) q.set("month", String(month));
  const qs = q.toString() ? `?${q.toString()}` : "";
  return apiFetch<{ year: number; month: number; events: Array<Record<string, unknown>> }>(
    `/api/v1/practice/litigation/calendar${qs}`
  );
}

export async function fetchLitigationTasks(matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{ tasks: Array<Record<string, unknown>>; templates: string[] }>(
    `/api/v1/practice/litigation/tasks${q}`
  );
}

export async function createLitigationTask(body: {
  matter_id: string;
  title: string;
  due_date?: string;
  assignee?: string;
  priority?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchLitigationOrders(matterId = "", q = "") {
  const params = new URLSearchParams();
  if (matterId) params.set("matter_id", matterId);
  if (q) params.set("q", q);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ orders: Array<Record<string, unknown>> }>(`/api/v1/practice/litigation/orders${qs}`);
}

export async function saveLitigationOrder(body: Record<string, string>) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/orders", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchLitigationAnalytics() {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/analytics");
}

export async function fetchLitigationWatchlistDashboard() {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/watchlist-dashboard");
}

export async function fetchLitigationWarRoom(matterId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/practice/litigation/war-room/${encodeURIComponent(matterId)}`);
}

export async function runLitigationAI(body: { tool: string; matter_id: string; extra?: string }) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/litigation/ai", {
    method: "POST",
    body: JSON.stringify(body),
  }, LONG_TIMEOUT_MS);
}

export async function fetchCourtDayPrepPack(matterId: string, useAi = true) {
  return apiFetch<{
    ok?: boolean;
    markdown?: string;
    error?: string;
    ai_brief_included?: boolean;
  }>(
    `/api/v1/practice/court-day/prep/${encodeURIComponent(matterId)}?use_ai=${useAi ? "1" : "0"}`,
    {},
    LONG_TIMEOUT_MS
  );
}

export async function parseCourtDayFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return apiFetch<{
    ok?: boolean;
    parsed_count?: number;
    parser?: string;
    rows?: CourtDayRow[];
    matters?: Array<{ matter_id: string; matter_name: string }>;
  }>("/api/v1/practice/court-day/parse-file", { method: "POST", body: fd }, LONG_TIMEOUT_MS);
}

export async function fetchCourtSyncStatus() {
  return apiFetch<{
    live_api_enabled?: boolean;
    api_configured?: boolean;
    api_provider?: string;
    api_key_masked?: string;
    api_key_source?: string;
    preferred_mode?: string;
    modes?: Array<{ id: string; label: string; cost_note?: string; recommended_for?: string }>;
    supported_sources?: string[];
    note?: string;
  }>("/api/v1/practice/court-sync/status");
}

export async function fetchCourtSyncSettings() {
  return apiFetch<{
    preferred_mode: string;
    api_configured: boolean;
    api_key_masked: string;
    api_key_source: string;
    save_user_key: boolean;
  }>("/api/v1/practice/court-sync/settings");
}

export async function saveCourtSyncSettings(body: {
  preferred_mode?: string;
  api_key?: string;
  clear_api_key?: boolean;
}) {
  return apiFetch<{
    preferred_mode: string;
    api_configured: boolean;
    api_key_masked: string;
    api_key_source: string;
    save_user_key: boolean;
  }>("/api/v1/practice/court-sync/settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function syncPracticeCourtCauseList(
  body: {
    source?: "paste" | "ecourtsindia";
    text?: string;
    auto_schedule?: boolean;
    api_date?: string;
    api_state?: string;
    api_query?: string;
    api_advocate?: string;
    api_litigant?: string;
    api_limit?: number;
    api_district_code?: string;
    api_court_complex_code?: string;
  }
) {
  return apiFetch<Record<string, unknown>>("/api/v1/practice/court-sync", {
    method: "POST",
    body: JSON.stringify({
      source: body.source ?? "paste",
      text: body.text ?? "",
      auto_schedule: body.auto_schedule ?? true,
      api_date: body.api_date ?? "",
      api_state: body.api_state ?? "",
      api_query: body.api_query ?? "",
      api_advocate: body.api_advocate ?? "",
      api_litigant: body.api_litigant ?? "",
      api_limit: body.api_limit ?? 50,
      api_district_code: body.api_district_code ?? "",
      api_court_complex_code: body.api_court_complex_code ?? "",
    }),
  }, LONG_TIMEOUT_MS);
}

export type EcourtsCasePreview = {
  ok?: boolean;
  cnr?: string;
  case_number?: string;
  parties?: string;
  petitioners?: string[];
  respondents?: string[];
  status?: string;
  court?: string;
  state?: string;
  next_hearing_date?: string;
  last_hearing_date?: string;
  filing_date?: string;
  order_count?: number;
  hearing_count?: number;
  hearing_preview?: Array<Record<string, string>>;
  request_id?: string;
};

export type EcourtsSearchHit = {
  cnr?: string;
  case_type?: string;
  case_status?: string;
  filing_date?: string;
  next_hearing_date?: string;
  court_code?: string;
  parties?: string;
  petitioners?: string[];
  respondents?: string[];
  judges?: string[];
  registration_number?: string;
};

export async function fetchEcourtsCase(cnr: string) {
  return apiFetch<EcourtsCasePreview>(
    `/api/v1/practice/ecourts/case/${encodeURIComponent(cnr.replace(/\s/g, "").toUpperCase())}`
  );
}

export async function syncEcourtsCase(
  cnr: string,
  body: { matter_id: string; import_hearings?: boolean; import_orders?: boolean }
) {
  return apiFetch<{
    ok?: boolean;
    cnr?: string;
    matter_id?: string;
    hearings_imported?: number;
    orders_imported?: number;
    hearings_skipped?: number;
    orders_skipped?: number;
    preview?: Record<string, string>;
  }>(`/api/v1/practice/ecourts/case/${encodeURIComponent(cnr.replace(/\s/g, "").toUpperCase())}/sync`, {
    method: "POST",
    body: JSON.stringify({
      matter_id: body.matter_id,
      import_hearings: body.import_hearings ?? true,
      import_orders: body.import_orders ?? true,
    }),
  }, LONG_TIMEOUT_MS);
}

export async function searchEcourtsCases(params: {
  query?: string;
  advocates?: string;
  litigants?: string;
  courtCodes?: string;
  filingDateFrom?: string;
  filingDateTo?: string;
  page?: number;
  pageSize?: number;
  caseStatus?: string;
  caseType?: string;
  state?: string;
}) {
  const q = new URLSearchParams();
  if (params.query) q.set("query", params.query);
  if (params.advocates) q.set("advocates", params.advocates);
  if (params.litigants) q.set("litigants", params.litigants);
  if (params.courtCodes) q.set("courtCodes", params.courtCodes);
  if (params.filingDateFrom) q.set("filingDateFrom", params.filingDateFrom);
  if (params.filingDateTo) q.set("filingDateTo", params.filingDateTo);
  if (params.page) q.set("page", String(params.page));
  if (params.pageSize) q.set("pageSize", String(params.pageSize));
  if (params.caseStatus) q.set("caseStatus", params.caseStatus);
  if (params.caseType) q.set("caseType", params.caseType);
  if (params.state) q.set("state", params.state);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiFetch<{
    ok?: boolean;
    results?: EcourtsSearchHit[];
    total_hits?: number;
    page?: number;
    page_size?: number;
    total_pages?: number;
    has_next_page?: boolean;
  }>(`/api/v1/practice/ecourts/search${suffix}`);
}

export async function fetchEcourtsStates() {
  return apiFetch<{ data?: unknown; states?: unknown }>("/api/v1/practice/ecourts/court-structure/states");
}

export async function fetchEcourtsDistricts(state: string) {
  return apiFetch<{ data?: unknown; districts?: unknown }>(
    `/api/v1/practice/ecourts/court-structure/states/${encodeURIComponent(state.toUpperCase())}/districts`
  );
}

export async function fetchEcourtsAvailableDates(params: {
  state: string;
  districtCode?: string;
  courtComplexCode?: string;
}) {
  const q = new URLSearchParams({ state: params.state.toUpperCase() });
  if (params.districtCode) q.set("districtCode", params.districtCode);
  if (params.courtComplexCode) q.set("courtComplexCode", params.courtComplexCode);
  return apiFetch<{ state?: string; dates?: string[] }>(
    `/api/v1/practice/ecourts/causelist/available-dates?${q.toString()}`
  );
}

export async function downloadHearingsCalendar(daysAhead = 60) {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithRetry(
    `/api/v1/practice/court-day/calendar.ics?days_ahead=${daysAhead}`,
    { headers },
    DEFAULT_TIMEOUT_MS
  );
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Calendar export failed"));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "legalease-hearings.ics";
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadEvidenceDeskReport() {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithRetry("/api/v1/practice/evidence-desk/export", { headers }, LONG_TIMEOUT_MS);
  if (!res.ok) {
    throw new Error(await readResponseError(res, "Export failed"));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "evidence-desk-report.md";
  a.click();
  URL.revokeObjectURL(url);
}

export type EvidenceDeskContradiction = {
  matter_id: string;
  matter_name: string;
  contradiction_id?: string;
  contradiction_type?: string;
  topic?: string;
  statement_a?: string;
  statement_b?: string;
  confidence?: number;
  source_hint?: string;
  created_at?: string;
};

export type EvidenceDeskResponse = {
  ok?: boolean;
  summary?: {
    total_matters: number;
    matters_with_contradictions: number;
    contradiction_count: number;
    blind_spot_count: number;
  };
  contradictions?: EvidenceDeskContradiction[];
  blind_spots?: Array<{
    matter_id: string;
    matter_name: string;
    document_count: number;
    reason: string;
  }>;
};

export async function fetchEvidenceDesk() {
  return apiFetch<EvidenceDeskResponse>("/api/v1/practice/evidence-desk");
}

export async function scanEvidenceDesk(maxMatters = 8) {
  return apiFetch<{
    ok?: boolean;
    scanned?: Array<{ matter_id: string; matter_name?: string; pairs_found?: number }>;
    scan_cap?: number;
    candidates_total?: number;
    errors?: string[];
    desk?: EvidenceDeskResponse;
  }>(
    `/api/v1/practice/evidence-desk/scan?max_matters=${maxMatters}`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    LONG_TIMEOUT_MS
  );
}

export async function scanEvidenceDeskAll() {
  return apiFetch<{
    ok?: boolean;
    scanned?: Array<{ matter_id: string; matter_name?: string; pairs_found?: number }>;
    scan_cap?: number;
    candidates_total?: number;
    errors?: string[];
    desk?: EvidenceDeskResponse;
  }>("/api/v1/practice/evidence-desk/scan-all", { method: "POST", body: JSON.stringify({}) }, LONG_TIMEOUT_MS * 2);
}

export type LegalWatch = {
  id: string;
  watch_type: string;
  label: string;
  query: string;
  matter_id?: string;
  active?: number;
  last_checked?: string;
};

export async function fetchWatchlist(matterId = "") {
  const q = matterId ? `?matter_id=${encodeURIComponent(matterId)}` : "";
  return apiFetch<{ items: LegalWatch[] }>(`/api/v1/engines/watchlist${q}`);
}

export async function addWatchlistItem(body: {
  watch_type: string;
  label: string;
  query: string;
  matter_id?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/v1/engines/watchlist", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function removeWatchlistItem(watchId: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/engines/watchlist/${encodeURIComponent(watchId)}`, {
    method: "DELETE",
  });
}

export async function checkWatchlistItem(watchId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/engines/watchlist/${encodeURIComponent(watchId)}/check`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

// —— Firm Chat (internal messaging; API path /collaboration) ——

export type CollabRoom = {
  room_id: string;
  org_id?: string;
  room_type: "dm" | "matter" | "channel" | string;
  matter_id?: string;
  slug?: string;
  name: string;
  description?: string;
  unread_count?: number;
  updated_at?: string;
  peer_user_id?: string;
  is_private_dm?: boolean;
  last_message_preview?: string;
  last_message_at?: string;
  last_sender_name?: string;
  last_sender_id?: string;
};

export type CollabMessage = {
  message_id: string;
  room_id: string;
  sender_id: string;
  sender_name?: string;
  body: string;
  message_type?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  attachments?: Array<{
    attachment_id: string;
    filename: string;
    mime_type?: string;
    file_size?: number;
    version?: number;
    uploader_id?: string;
    uploader_name?: string;
    matter_id?: string;
    matter_name?: string;
    created_at?: string;
  }>;
  reactions?: Array<{ emoji: string; user_id: string }>;
  seen?: boolean;
  seen_by?: string[];
};

export type CollabNotification = {
  notification_id: string;
  type: string;
  title: string;
  body?: string;
  link_path?: string;
  room_id?: string;
  read?: boolean;
  created_at: string;
};

export async function postCollabPresence(roomId = "", displayName = "") {
  return apiFetch<{ ok: boolean; backend?: string }>("/api/v1/collaboration/presence", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, display_name: displayName }),
  });
}

export async function fetchCollabPresence(roomId = "") {
  const q = roomId ? `?room_id=${encodeURIComponent(roomId)}` : "";
  return apiFetch<{
    online: Array<{ user_id: string; display_name?: string; online: boolean }>;
  }>(`/api/v1/collaboration/presence${q}`);
}

export async function fetchCollabPermissions() {
  return apiFetch<{ permissions: Record<string, boolean> }>(
    "/api/v1/collaboration/permissions"
  );
}

export async function fetchCollabRooms() {
  return apiFetch<{ rooms: CollabRoom[] }>("/api/v1/collaboration/rooms");
}

export async function fetchCollabMembers() {
  return apiFetch<{
    members: Array<{ user_id: string; username: string; role?: string }>;
  }>("/api/v1/collaboration/members");
}

export type CollabUserSearchHit = {
  user_id: string;
  username: string;
  display_name?: string;
  is_self?: boolean;
  connection_status:
    | "none"
    | "connected"
    | "pending_sent"
    | "pending_received"
    | "self";
};

export type CollabChatRequest = {
  request_id: string;
  from_user_id?: string;
  to_user_id?: string;
  from_username?: string;
  to_username?: string;
  intro_message?: string;
  status: string;
  created_at: string;
};

export async function searchCollabUsers(q: string) {
  return apiFetch<{
    users: CollabUserSearchHit[];
    hint?: string;
    your_username?: string;
    query?: string;
  }>(`/api/v1/collaboration/users/search?q=${encodeURIComponent(q)}`);
}

export async function fetchCollabChatRequests() {
  return apiFetch<{
    incoming: CollabChatRequest[];
    outgoing: CollabChatRequest[];
  }>("/api/v1/collaboration/requests");
}

export async function sendCollabChatRequest(toUserId: string, introMessage = "") {
  return apiFetch<{
    status: string;
    request_id?: string;
    message?: string;
    room?: CollabRoom;
  }>("/api/v1/collaboration/requests", {
    method: "POST",
    body: JSON.stringify({ to_user_id: toUserId, intro_message: introMessage }),
  });
}

export async function acceptCollabChatRequest(requestId: string) {
  return apiFetch<{ status: string; room?: CollabRoom }>(
    `/api/v1/collaboration/requests/${encodeURIComponent(requestId)}/accept`,
    { method: "POST", body: "{}" }
  );
}

export async function rejectCollabChatRequest(requestId: string) {
  return apiFetch<{ status: string }>(
    `/api/v1/collaboration/requests/${encodeURIComponent(requestId)}/reject`,
    { method: "POST", body: "{}" }
  );
}

export async function createCollabDm(peerUserId: string) {
  return apiFetch<{ room: CollabRoom }>("/api/v1/collaboration/rooms/dm", {
    method: "POST",
    body: JSON.stringify({ peer_user_id: peerUserId }),
  });
}

export async function fetchCollabMatterRoom(matterId: string) {
  return apiFetch<{ room: CollabRoom }>(
    `/api/v1/collaboration/rooms/matter/${encodeURIComponent(matterId)}`
  );
}

export async function fetchCollabMessages(
  roomId: string,
  opts: { before?: string; since?: string; limit?: number } = {}
) {
  const q = new URLSearchParams({ limit: String(opts.limit ?? 50) });
  if (opts.before) q.set("before", opts.before);
  if (opts.since) q.set("since", opts.since);
  return apiFetch<{ messages: CollabMessage[] }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/messages?${q}`
  );
}

export async function postCollabMessage(
  roomId: string,
  body: { body: string; parent_id?: string; message_type?: string }
) {
  return apiFetch<{ message: CollabMessage }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/messages`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function markCollabRoomRead(roomId: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/read`,
    { method: "POST", body: "{}" }
  );
}

export async function uploadCollabAttachment(
  roomId: string,
  messageId: string,
  file: File
) {
  const fd = new FormData();
  fd.append("file", file);
  return apiFetch<{ attachment: Record<string, unknown> }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}/attachments`,
    { method: "POST", body: fd }
  );
}

/** Upload with progress — does not block UI; use for voice notes and large files. */
export function uploadCollabAttachmentWithProgress(
  roomId: string,
  messageId: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<{ attachment: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const token = getToken();
    const xhr = new XMLHttpRequest();
    const url = `${getApiBase()}/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}/attachments`;
    const fd = new FormData();
    fd.append("file", file);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as { attachment: Record<string, unknown> });
        } catch {
          reject(new Error("Invalid upload response"));
        }
        return;
      }
      reject(new Error(xhr.responseText || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.open("POST", url);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(fd);
  });
}

export async function fetchCollabRealtimeDebug() {
  return apiFetch<{ hub: Record<string, unknown>; rate_limits: Record<string, unknown> }>(
    "/api/v1/collaboration/debug/realtime"
  );
}

export function collabAttachmentUrl(attachmentId: string) {
  return `${API_BASE}/api/v1/collaboration/attachments/${encodeURIComponent(attachmentId)}/download`;
}

/** Authenticated blob URL for inline audio playback. */
export async function fetchCollabAttachmentObjectUrl(attachmentId: string): Promise<string> {
  const token = getToken();
  const res = await fetch(collabAttachmentUrl(attachmentId), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Attachment download failed");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function createTaskFromCollabMessage(
  messageId: string,
  body: { title?: string; assignee?: string; due_date?: string; priority?: string }
) {
  return apiFetch<{ task: Record<string, unknown>; matter_id: string }>(
    `/api/v1/collaboration/messages/${encodeURIComponent(messageId)}/create-task`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function createDeadlineFromCollabMessage(
  messageId: string,
  body: { title?: string; due_date: string; deadline_type?: string; notes?: string }
) {
  return apiFetch<{ deadline: Record<string, unknown>; matter_id: string }>(
    `/api/v1/collaboration/messages/${encodeURIComponent(messageId)}/create-deadline`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function searchCollab(q: string) {
  return apiFetch<{
    query: string;
    rooms: CollabRoom[];
    messages: Array<{
      message_id: string;
      room_id: string;
      body: string;
      room_name?: string;
    }>;
  }>(`/api/v1/collaboration/search?q=${encodeURIComponent(q)}`);
}

export async function fetchCollabNotifications(unreadOnly = false) {
  return apiFetch<{ notifications: CollabNotification[] }>(
    `/api/v1/collaboration/notifications?unread_only=${unreadOnly ? "true" : "false"}`
  );
}

export async function markCollabNotificationRead(notificationId: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/v1/collaboration/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: "POST", body: "{}" }
  );
}

export async function createCollabChannel(payload: {
  slug: string;
  name: string;
  description?: string;
}) {
  return apiFetch<{ room: CollabRoom }>("/api/v1/collaboration/rooms/channel", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function postCollabTyping(roomId: string, typing: boolean, displayName = "") {
  return apiFetch<{ ok: boolean }>("/api/v1/collaboration/typing", {
    method: "POST",
    body: JSON.stringify({ room_id: roomId, typing, display_name: displayName }),
  });
}

export async function fetchCollabTyping(roomId: string) {
  return apiFetch<{ typing: Array<{ user_id: string; display_name?: string }> }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/typing`
  );
}

export async function fetchCollabRoomContext(roomId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/context`
  );
}

export async function fetchCollabRoomStats(roomId: string) {
  return apiFetch<{
    room_id: string;
    message_count: number;
    documents_shared: number;
    tasks_created: number;
    matter_id?: string;
    matter_name?: string;
    room_type?: string;
    room_name?: string;
  }>(`/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/stats`);
}

export async function summarizeCollabRoom(roomId: string, limit = 100) {
  return apiFetch<{
    summary_text: string;
    key_decisions: string[];
    open_issues: string[];
    action_items: string[];
    deadlines: string[];
    hearing_notes?: string[];
    matter_id?: string;
    ai_note?: string;
  }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/summarize?limit=${limit}`,
    { method: "POST", body: "{}" },
    LONG_TIMEOUT_MS
  );
}

export async function addCollabReaction(roomId: string, messageId: string, emoji: string) {
  return apiFetch<{ message_id: string }>(
    `/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}/reactions`,
    { method: "POST", body: JSON.stringify({ emoji }) }
  );
}
