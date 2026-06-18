"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ChatMessage } from "@/lib/api";
import {
  getChatThread,
  getThreadAttachment,
  removeThreadAttachment,
  streamChat,
  uploadThreadAttachment,
} from "@/lib/api";
import type { ThreadAttachmentInfo } from "@/components/chat/InputDock";
import { useChatSession } from "@/components/providers/ChatSessionProvider";
import {
  clearChatCache,
  getLastThreadId,
  loadChatCache,
  saveChatCache,
} from "@/lib/chatStorage";
import { stripVendorNamesFromText } from "@/lib/displayLabels";

export type SourceMeta = {
  filename?: string;
  section?: string;
};

export type WebSourceItem = {
  title?: string;
  href?: string;
  body?: string;
  provider?: string;
  trust_badge?: string;
  freshness?: string;
};

export type RetrievalDebugPayload = {
  original_query?: string;
  expanded_query?: string;
  retrieval_mode?: string;
  follow_up_detected?: boolean;
  memory_used?: boolean;
  active_topic?: string;
  active_section?: string;
  active_document?: string;
  chunk_count?: number;
  context_passed_to_llm?: boolean;
  stage_failures?: string[];
  retrieved_chunks?: Array<{
    index?: number;
    score?: number;
    source?: string;
    excerpt?: string;
  }>;
};

export type UiMessage = {
  role: "user" | "assistant";
  content: string;
  sourcesLabel?: string | null;
  sourceMeta?: SourceMeta;
  webSources?: WebSourceItem[];
  streaming?: boolean;
  streamStatus?: string;
  interactionId?: string;
  chatId?: string;
};

const GARBAGE = new Set(["{}", "{ }", "[]", "null", "none", ""]);

const BROKEN_FALLBACK = /couldn'?t generate a proper answer|found related document content, but/i;
const NOT_FOUND_PHRASE =
  /could(?:n't| not) find(?: a clear reference| this information)? in the uploaded legal documents/i;
const LEGAL_CONTENT =
  /\b(?:section|ipc|bns)\s*\d{1,4}[a-z]?|##\s|###\s|direct answer|case overview|legal fact sheet|web intelligence/i;

const KB_NOT_FOUND =
  "I couldn't find a clear reference to that in the uploaded legal documents.";

const WEB_UNAVAILABLE =
  "Live web research is temporarily unavailable. Please try again in a moment.";

function isOpenLawChatMode(chatMode?: string): boolean {
  return (
    chatMode === "web_search" ||
    chatMode === "open_law" ||
    chatMode === "hybrid" ||
    chatMode === "deep_case"
  );
}

function jsonLikeToMarkdown(text: string): string {
  const t = text.trim();
  if (!t.startsWith("{") && !t.startsWith("[")) return text;
  try {
    const data = JSON.parse(t) as Record<string, unknown>;
    const lines: string[] = [];
    const walk = (obj: unknown, depth = 0): void => {
      if (typeof obj === "string" && obj.length > 20) {
        lines.push(obj);
        return;
      }
      if (obj && typeof obj === "object" && !Array.isArray(obj)) {
        for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
          if (typeof v === "string" && v.length > 0) {
            lines.push(depth === 0 ? `## ${k}\n\n${v}` : `**${k}:** ${v}`);
          } else if (v && typeof v === "object") {
            lines.push(`## ${k}`);
            walk(v, depth + 1);
          }
        }
      }
    };
    walk(data);
    return lines.join("\n\n").trim() || text;
  } catch {
    return text;
  }
}

function cleanAssistantText(raw: string): string {
  let t = (raw || "").trim();
  if (t.startsWith("{") || t.startsWith("[")) {
    t = jsonLikeToMarkdown(t);
  }
  t = t.replace(BROKEN_FALLBACK, "");
  t = t.replace(
    /this explanation is drawn only from your uploaded document\.?\s*/gi,
    ""
  );
  t = t.replace(/\n*\*{0,2}Source\*{0,2}\s*:[\s\S]*$/i, "");
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  return stripVendorNamesFromText(t);
}

function parseSourceMeta(
  meta?: Record<string, unknown>,
  answerText?: string
): SourceMeta {
  const sm = meta?.source_meta as SourceMeta | undefined;
  if (sm?.section) return sm;
  const fromAnswer = (answerText || "").match(
    /(?:IPC|BNS)\s+Section\s+(\d{1,4}[a-z]?)\s*[—–-]/i
  );
  if (fromAnswer) {
    return {
      filename: sm?.filename || "",
      section: fromAnswer[1].toUpperCase(),
    };
  }
  if (sm?.filename) return sm;
  return sm || {};
}

function stripFalseNotFound(text: string): string {
  if (!text || !NOT_FOUND_PHRASE.test(text)) return text;
  if (LEGAL_CONTENT.test(text)) {
    return text
      .replace(NOT_FOUND_PHRASE, "")
      .replace(
        /I checked the uploaded legal documents[^\n.]*\.?\s*/gi,
        ""
      )
      .trim();
  }
  return text;
}

function pickFinalAnswer(
  streamed: string,
  meta?: Record<string, unknown>,
  chatMode?: string
): string {
  const fromStream = stripFalseNotFound(cleanAssistantText(streamed));
  const fromMeta = stripFalseNotFound(
    cleanAssistantText(
      String(
        meta?.answer ||
          meta?.content ||
          meta?.response ||
          meta?.message ||
          meta?.text ||
          ""
      )
    )
  );

  const isOpenLawMode = isOpenLawChatMode(chatMode);
  if (isOpenLawMode) {
    const candidates = [fromStream, fromMeta].filter(
      (t) => t && !GARBAGE.has(t) && t.length > 8 && !BROKEN_FALLBACK.test(t)
    );
    for (const c of candidates) {
      if (!NOT_FOUND_PHRASE.test(c) || LEGAL_CONTENT.test(c)) {
        return stripFalseNotFound(c);
      }
    }
    if (fromStream.length > 20) return fromStream;
    if (fromMeta.length > 20 && !NOT_FOUND_PHRASE.test(fromMeta)) return fromMeta;
  }

  const webSources = meta?.web_sources as unknown[] | undefined;
  const isOpenLaw =
    Array.isArray(webSources) &&
    webSources.length > 0 &&
    webSources[0] &&
    typeof webSources[0] === "object";
  if (isOpenLaw && fromMeta.length > 40 && !isOpenLawMode) {
    return fromMeta;
  }

  const streamHasLegal = LEGAL_CONTENT.test(fromStream);
  const metaHasLegal = LEGAL_CONTENT.test(fromMeta);

  let best = fromMeta;
  if (streamHasLegal && !metaHasLegal) best = fromStream;
  else if (streamHasLegal && metaHasLegal) {
    best = fromMeta.length >= fromStream.length ? fromMeta : fromStream;
  } else if (!metaHasLegal && fromStream.length > fromMeta.length) {
    best = fromStream;
  }

  best = stripFalseNotFound(best);
  if (best && !GARBAGE.has(best) && best.length > 8 && !BROKEN_FALLBACK.test(best)) {
    if (NOT_FOUND_PHRASE.test(best) && LEGAL_CONTENT.test(best)) {
      return stripFalseNotFound(best);
    }
    if (NOT_FOUND_PHRASE.test(best) && !LEGAL_CONTENT.test(best)) {
      return KB_NOT_FOUND;
    }
    return best;
  }
  if (
    fromMeta &&
    !GARBAGE.has(fromMeta) &&
    !(NOT_FOUND_PHRASE.test(fromMeta) && !LEGAL_CONTENT.test(fromMeta))
  ) {
    return fromMeta;
  }
  if (fromStream && !GARBAGE.has(fromStream)) {
    if (NOT_FOUND_PHRASE.test(fromStream) && !LEGAL_CONTENT.test(fromStream)) {
      return KB_NOT_FOUND;
    }
    return fromStream;
  }
  return KB_NOT_FOUND;
}

function ensureNonEmptyAssistantText(text: string, chatMode?: string): string {
  const t = (text || "").trim();
  if (t && !GARBAGE.has(t) && t.length > 8) return t;
  if (isOpenLawChatMode(chatMode)) return WEB_UNAVAILABLE;
  return KB_NOT_FOUND;
}

function isVerbalFeedbackMessage(content: string): boolean {
  const q = (content || "").trim().toLowerCase();
  if (!q || q.length > 80) return false;
  return /^(good|great|thanks?|thank you|helpful|ok|okay|not relevant|wrong|missing|error|can do better)$/.test(
    q
  );
}

function sanitizeHistoryForSend(messages: UiMessage[]): ChatMessage[] {
  return messages
    .filter((m) => !(m.role === "assistant" && m.streaming))
    .filter((m) => !isVerbalFeedbackMessage(m.content))
    .filter(
      (m) =>
        !(
          m.role === "assistant" &&
          /glad that helped|you're welcome|thanks for the feedback/i.test(m.content)
        )
    )
    .map((m) => ({ role: m.role, content: m.content }));
}

function formatSources(
  similar_cases?: Record<string, unknown>[],
  web_sources?: Record<string, unknown>[]
) {
  const parts: string[] = [];
  if (similar_cases?.[0]) {
    const f = similar_cases[0].filename as string;
    parts.push(`Source: ${f || "document"}`);
  }
  if (web_sources?.[0]?.href) {
    parts.push((web_sources[0].title as string) || "Web");
  }
  return parts.join(" · ") || null;
}

export function useChat(
  mode: string,
  lang: string,
  setMode?: (m: string) => void,
  setLang?: (l: string) => void,
  matterId = "",
  setMatterId?: (id: string) => void
) {
  const {
    threadId,
    setThreadId,
    bumpHistory,
    registerThreadLoader,
    registerClearHandler,
    openThread,
  } = useChatSession();

  const router = useRouter();
  const searchParams = useSearchParams();
  const threadFromUrl = searchParams.get("thread");
  const matterModeFromUrl = searchParams.get("matter_mode") || "";

  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingThread, setLoadingThread] = useState(false);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [retrievalDebug, setRetrievalDebug] = useState<RetrievalDebugPayload | null>(null);
  const [debugBusy, setDebugBusy] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [threadAttachment, setThreadAttachment] =
    useState<ThreadAttachmentInfo | null>(null);
  const [attachBusy, setAttachBusy] = useState(false);
  const lastLoadedThreadRef = useRef<string | null>(null);
  const loadedThreadIdRef = useRef<string | null>(null);
  const inFlightThreadRef = useRef<string | null>(null);
  const loadSeqRef = useRef(0);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const hydratedRef = useRef(false);
  const skipUrlThreadLoadRef = useRef(false);
  const streamAbortRef = useRef<AbortController | null>(null);
  const assistantContentRef = useRef("");
  const gotStreamMetaRef = useRef(false);
  const streamIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearStreamIdleTimer = useCallback(() => {
    if (streamIdleTimerRef.current) {
      clearTimeout(streamIdleTimerRef.current);
      streamIdleTimerRef.current = null;
    }
  }, []);

  const finalizeStreamingMessage = useCallback(
    (meta?: Record<string, unknown>) => {
      gotStreamMetaRef.current = true;
      clearStreamIdleTimer();
      const finalText = ensureNonEmptyAssistantText(
        cleanAssistantText(
          pickFinalAnswer(assistantContentRef.current, meta, mode)
        ),
        mode
      );
      assistantContentRef.current = finalText;
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last?.role !== "assistant") return prev;
        const ws = (meta?.web_sources as WebSourceItem[]) || last.webSources || [];
        const sc = meta?.similar_cases as Record<string, unknown>[] | undefined;
        copy[copy.length - 1] = {
          ...last,
          content: finalText,
          sourcesLabel:
            last.sourcesLabel ||
            formatSources(sc, ws as Record<string, unknown>[]),
          sourceMeta: parseSourceMeta(meta, finalText || last.content),
          webSources: ws,
          streaming: false,
          streamStatus: "",
          interactionId: String(
            meta?.interaction_id || last.interactionId || ""
          ),
          chatId: String(meta?.chat_id || meta?.thread_id || last.chatId || ""),
        };
        return copy;
      });
    },
    [clearStreamIdleTimer, mode]
  );

  const scheduleStreamIdleFinalize = useCallback(
    (opts?: { idleMs?: number; requireTokens?: boolean }) => {
      clearStreamIdleTimer();
      const idleMs = opts?.idleMs ?? (mode === "knowledge_base" ? 120000 : 45000);
      if (opts?.requireTokens && !assistantContentRef.current.trim()) {
        return;
      }
      streamIdleTimerRef.current = setTimeout(() => {
        if (gotStreamMetaRef.current) return;
        if (!assistantContentRef.current.trim()) return;
        finalizeStreamingMessage({
          follow_ups: [],
          similar_cases: [],
          web_sources: [],
        });
        setLoading(false);
      }, idleMs);
    },
    [clearStreamIdleTimer, finalizeStreamingMessage, mode]
  );

  const loadThreadById = useCallback(
    async (tid: string, opts?: { force?: boolean }) => {
      if (!tid) return;
      if (
        !opts?.force &&
        loadedThreadIdRef.current === tid &&
        messagesRef.current.length > 0
      ) {
        return;
      }
      if (inFlightThreadRef.current === tid && !opts?.force) {
        return;
      }

      const loadSeq = ++loadSeqRef.current;
      inFlightThreadRef.current = tid;
      const switching = loadedThreadIdRef.current !== tid;
      if (switching) {
        setMessages([]);
        setFollowUps([]);
        setThreadAttachment(null);
      }

      lastLoadedThreadRef.current = tid;
      setThreadId(tid);
      setLoadingThread(true);
      setError("");

      try {
        const data = await getChatThread(tid);
        if (loadSeq !== loadSeqRef.current) return;

        const loaded: UiMessage[] = (data.messages || []).map((m) => ({
          role: m.role as "user" | "assistant",
          content: cleanAssistantText(m.content),
        }));
        if (!loaded.length) {
          loadedThreadIdRef.current = null;
          setMessages([]);
          setError("This chat is empty or could not be loaded.");
          return;
        }
        setMessages(loaded);
        const resolvedId = data.thread_id || tid;
        loadedThreadIdRef.current = resolvedId;
        setThreadId(resolvedId);
        if (setMode && data.mode) setMode(data.mode);
        if (setLang && data.language) setLang(data.language);
        if (data.matter_id && setMatterId) {
          setMatterId(data.matter_id);
          if (typeof window !== "undefined") {
            localStorage.setItem("legalease_active_matter", data.matter_id);
          }
        }
        saveChatCache({
          threadId: resolvedId,
          messages: loaded,
          mode: data.mode || mode,
          lang: data.language || lang,
          updatedAt: Date.now(),
        });
        if (typeof window !== "undefined") {
          const url = new URL(window.location.href);
          url.searchParams.set("thread", resolvedId);
          window.history.replaceState({}, "", url.pathname + url.search);
        }
        try {
          const att = await getThreadAttachment(resolvedId);
          if (loadSeq !== loadSeqRef.current) return;
          if (att.has_attachment && att.filename) {
            setThreadAttachment({
              filename: att.filename,
              charCount: att.char_count,
              preview: att.preview,
            });
          } else {
            setThreadAttachment(null);
          }
        } catch {
          if (loadSeq === loadSeqRef.current) {
            setThreadAttachment(null);
          }
        }
      } catch (e) {
        if (loadSeq !== loadSeqRef.current) return;
        const msg = e instanceof Error ? e.message : "";
        const cache = loadChatCache();
        if (cache?.threadId === tid && cache.messages?.length) {
          setMessages(cache.messages);
          loadedThreadIdRef.current = cache.threadId || tid;
          setThreadId(cache.threadId || tid);
          if (setMode && cache.mode) setMode(cache.mode);
          if (setLang && cache.lang) setLang(cache.lang);
          setError("Showing cached copy — server could not refresh this chat.");
          return;
        }
        loadedThreadIdRef.current = null;
        setMessages([]);
        if (/not found/i.test(msg)) {
          clearChatCache();
          setError("This saved chat was not found. It may have been deleted.");
          return;
        }
        if (/429|rate limit/i.test(msg)) {
          setError("Too many requests — wait a moment, then click Saved Chats ↻ refresh.");
          return;
        }
        setError(msg || "Could not load this chat. Try sending a new message first.");
      } finally {
        if (loadSeq === loadSeqRef.current) {
          setLoadingThread(false);
          if (inFlightThreadRef.current === tid) {
            inFlightThreadRef.current = null;
          }
        }
      }
    },
    [setThreadId, setMode, setLang, setMatterId, mode, lang]
  );

  const loadThreadByIdRef = useRef(loadThreadById);
  loadThreadByIdRef.current = loadThreadById;

  const ensureThreadId = useCallback(() => {
    if (threadId) return threadId;
    const newId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `thread-${Date.now()}`;
    setThreadId(newId);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("thread", newId);
      window.history.replaceState({}, "", url.pathname + url.search);
    }
    return newId;
  }, [threadId, setThreadId]);

  const attachFile = useCallback(
    async (file: File) => {
      setError("");
      const tid = ensureThreadId();
      setAttachBusy(true);
      try {
        const res = await uploadThreadAttachment(tid, file, false);
        setThreadAttachment({
          filename: res.filename,
          charCount: res.char_count,
          preview: res.preview,
        });
        if (mode !== "knowledge_base" && setMode) {
          setMode("knowledge_base");
        }
        setError("");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not attach file");
      } finally {
        setAttachBusy(false);
      }
    },
    [ensureThreadId, mode, setMode]
  );

  const clearAttachment = useCallback(async () => {
    if (threadId) {
      try {
        await removeThreadAttachment(threadId);
      } catch {
        /* ignore */
      }
    }
    setThreadAttachment(null);
  }, [threadId]);

  const resetChat = useCallback(() => {
    skipUrlThreadLoadRef.current = true;
    loadSeqRef.current += 1;
    inFlightThreadRef.current = null;
    lastLoadedThreadRef.current = null;
    loadedThreadIdRef.current = null;
    setMessages([]);
    setFollowUps([]);
    setError("");
    setSessionId(undefined);
    setThreadAttachment(null);
    clearChatCache();
    router.replace("/");
  }, [router]);

  useEffect(() => {
    registerThreadLoader(loadThreadById);
    return () => registerThreadLoader(null);
  }, [loadThreadById, registerThreadLoader]);

  useEffect(() => {
    registerClearHandler(resetChat);
    return () => registerClearHandler(null);
  }, [resetChat, registerClearHandler]);

  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;

    const cache = loadChatCache();
    const targetTid = threadFromUrl || cache?.threadId || getLastThreadId();
    const cacheMatchesTarget =
      !!cache?.messages?.length &&
      (!targetTid || !cache.threadId || cache.threadId === targetTid);

    if (cacheMatchesTarget && cache) {
      setMessages(cache.messages);
      if (cache.threadId) {
        setThreadId(cache.threadId);
        loadedThreadIdRef.current = cache.threadId;
        lastLoadedThreadRef.current = cache.threadId;
      }
      if (setMode && cache.mode) setMode(cache.mode);
      if (setLang && cache.lang) setLang(cache.lang);
    }
    if (targetTid && !threadFromUrl) {
      void loadThreadByIdRef.current(targetTid, { force: false });
    }
  }, [threadFromUrl, setThreadId, setMode, setLang]);

  useEffect(() => {
    if (!threadFromUrl) {
      skipUrlThreadLoadRef.current = false;
      return;
    }
    if (skipUrlThreadLoadRef.current) return;
    if (!hydratedRef.current) return;
    if (loadedThreadIdRef.current === threadFromUrl) return;
    if (inFlightThreadRef.current === threadFromUrl) return;
    void loadThreadByIdRef.current(threadFromUrl, { force: true });
  }, [threadFromUrl]);

  useEffect(() => {
    if (!messages.length) return;
    if (messages.some((m) => m.streaming)) return;
    if (!threadId) return;
    saveChatCache({
      threadId,
      messages,
      mode,
      lang,
      updatedAt: Date.now(),
    });
  }, [messages, threadId, mode, lang]);

  const sendMessage = useCallback(
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt || loading || loadingThread) return;
      streamAbortRef.current?.abort();
      const abortCtrl = new AbortController();
      streamAbortRef.current = abortCtrl;

      setError("");
      setFollowUps([]);

      const tid = ensureThreadId();
      const userMsg: UiMessage = { role: "user", content: prompt };
      const prior = messages.filter(
        (m) => !(m.role === "assistant" && m.streaming)
      );
      setMessages([...prior, userMsg]);
      setLoading(true);

      const history = sanitizeHistoryForSend(prior);

      assistantContentRef.current = "";
      gotStreamMetaRef.current = false;
      clearStreamIdleTimer();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          streaming: true,
          streamStatus:
            mode === "knowledge_base"
              ? "Searching your knowledge base…"
              : mode === "deep_case" || mode === "hybrid"
                ? "Searching your uploaded documents…"
                : "Understanding your question…",
        },
      ]);
      scheduleStreamIdleFinalize({ idleMs: mode === "knowledge_base" ? 180000 : 90000 });

      try {
        await streamChat(
          {
            message: prompt,
            mode,
            lang,
            session_id: sessionId,
            thread_id: tid,
            matter_id:
              matterId && (mode === "deep_case" || mode === "hybrid")
                ? matterId
                : undefined,
            matter_mode: matterModeFromUrl || undefined,
            history,
          },
          (token) => {
            setError("");
            assistantContentRef.current += token;
            scheduleStreamIdleFinalize({ requireTokens: true });
            const displayContent = stripVendorNamesFromText(
              assistantContentRef.current
            );
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = {
                  ...last,
                  content: displayContent,
                  streaming: true,
                  streamStatus: "",
                };
              }
              return copy;
            });
          },
          (meta) => {
            setError("");
            gotStreamMetaRef.current = true;
            clearStreamIdleTimer();
            if (meta.session_id) setSessionId(meta.session_id as string);
            if (meta.thread_id) {
              const savedTid = String(meta.thread_id);
              loadedThreadIdRef.current = savedTid;
              setThreadId(savedTid);
              if (typeof window !== "undefined") {
                const url = new URL(window.location.href);
                url.searchParams.set("thread", String(meta.thread_id));
                window.history.replaceState({}, "", url.pathname + url.search);
              }
            }
            bumpHistory();
            const fu = meta.follow_ups as string[] | undefined;
            if (fu?.length) setFollowUps(fu);
            const rd = meta.retrieval_debug as RetrievalDebugPayload | undefined;
            if (rd && Object.keys(rd).length) {
              setRetrievalDebug({
                ...rd,
                chunk_count: rd.chunk_count ?? (rd.retrieved_chunks?.length || 0),
              });
            }
            const sc = meta.similar_cases as Record<string, unknown>[] | undefined;
            const ws = meta.web_sources as Record<string, unknown>[] | undefined;
            const label = formatSources(sc, ws);
            const finalText = ensureNonEmptyAssistantText(
              cleanAssistantText(
                pickFinalAnswer(assistantContentRef.current, meta, mode)
              ),
              mode
            );
            const sourceMeta = parseSourceMeta(meta, finalText);
            assistantContentRef.current = finalText;
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = {
                  ...last,
                  content: finalText,
                  sourcesLabel: label,
                  sourceMeta,
                  webSources: (ws as WebSourceItem[]) || [],
                  streaming: false,
                  streamStatus: "",
                  interactionId: String(meta.interaction_id || ""),
                  chatId: String(meta.chat_id || meta.thread_id || tid || ""),
                };
              }
              const savedThread = (meta.thread_id as string) || tid;
              if (savedThread) {
                saveChatCache({
                  threadId: savedThread,
                  messages: copy,
                  mode,
                  lang,
                  updatedAt: Date.now(),
                });
              }
              return copy;
            });
          },
          (msg) => setError(msg),
          (status) => {
            scheduleStreamIdleFinalize();
            const statusText = (status || "")
              .replace(/\*+/g, "")
              .replace(/\s+/g, " ")
              .trim();
            if (!statusText) return;
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant" && last.streaming) {
                copy[copy.length - 1] = {
                  ...last,
                  streamStatus: statusText,
                  content: last.content || "",
                };
              }
              return copy;
            });
          },
          abortCtrl.signal
        );
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : "Chat failed");
        setMessages((prev) => prev.filter((m) => !m.streaming));
      } finally {
        streamAbortRef.current = null;
        clearStreamIdleTimer();
        setLoading(false);
        if (!gotStreamMetaRef.current && assistantContentRef.current.trim()) {
          finalizeStreamingMessage({
            follow_ups: [],
            similar_cases: [],
            web_sources: [],
          });
        }
        const fallback = stripVendorNamesFromText(assistantContentRef.current);
        setMessages((prev) =>
          prev.map((m, idx, arr) => {
            if (!m.streaming) return m;
            const isLast = idx === arr.length - 1;
            const content = isLast
              ? ensureNonEmptyAssistantText(cleanAssistantText(fallback), mode)
              : m.content;
            return {
              ...m,
              content,
              streaming: false,
              streamStatus: "",
            };
          })
        );
      }
    },
    [
      loading,
      loadingThread,
      messages,
      mode,
      lang,
      matterId,
      sessionId,
      ensureThreadId,
      setThreadId,
      bumpHistory,
      clearStreamIdleTimer,
      finalizeStreamingMessage,
      scheduleStreamIdleFinalize,
    ]
  );

  const regenerateAt = useCallback(
    async (assistantIndex: number) => {
      if (loading || loadingThread || assistantIndex < 1) return;
      let userQuery = "";
      for (let j = assistantIndex - 1; j >= 0; j--) {
        if (messages[j]?.role === "user") {
          userQuery = messages[j].content;
          break;
        }
      }
      if (!userQuery.trim()) return;
      setMessages(messages.slice(0, assistantIndex));
      await sendMessage(userQuery);
    },
    [loading, loadingThread, messages, sendMessage]
  );

  const lastAssistantInteractionId = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === "assistant" && messages[i]?.interactionId) {
        return messages[i].interactionId;
      }
    }
    return "";
  })();

  return {
    messages,
    loading,
    loadingThread,
    followUps,
    error,
    sendMessage,
    regenerateAt,
    lastAssistantInteractionId,
    resetChat,
    sessionId,
    threadId,
    loadThreadById,
    openThread,
    threadAttachment,
    attachFile,
    attachBusy,
    clearAttachment,
    retrievalDebug,
    debugBusy,
    runRetrievalDebug: async (query: string) => {
      if (!query.trim()) return;
      setDebugBusy(true);
      try {
        const { kbDebugQuery } = await import("@/lib/api");
        const out = await kbDebugQuery(query.trim(), sessionId);
        const dc = (out.debug_console || out) as RetrievalDebugPayload;
        setRetrievalDebug(dc);
      } catch {
        /* ignore */
      } finally {
        setDebugBusy(false);
      }
    },
  };
}
