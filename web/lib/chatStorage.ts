import type { UiMessage } from "@/hooks/useChat";

const CACHE_KEY = "legalease_chat_cache";
/** Must match ChatSessionProvider THREAD_STORAGE_KEY */
const LAST_THREAD_KEY = "legalease_active_thread";

export type ChatCache = {
  threadId?: string;
  messages: UiMessage[];
  mode: string;
  lang: string;
  updatedAt: number;
};

export function saveChatCache(cache: ChatCache) {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache));
    if (cache.threadId) {
      localStorage.setItem(LAST_THREAD_KEY, cache.threadId);
    }
  } catch {
    /* ignore quota */
  }
}

export function loadChatCache(): ChatCache | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChatCache;
    if (!parsed?.messages?.length) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearChatCache() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(CACHE_KEY);
  localStorage.removeItem(LAST_THREAD_KEY);
  localStorage.removeItem("legalease_last_thread");
}

export function getLastThreadId(): string | null {
  if (typeof window === "undefined") return null;
  const active = localStorage.getItem(LAST_THREAD_KEY);
  if (active) return active;
  const legacy = localStorage.getItem("legalease_last_thread");
  if (legacy) {
    localStorage.setItem(LAST_THREAD_KEY, legacy);
    localStorage.removeItem("legalease_last_thread");
    return legacy;
  }
  return null;
}
