"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type HistoryItem = {
  thread_id?: string;
  id?: string;
  question: string;
  preview?: string;
  mode?: string;
  language?: string;
  created_at?: string;
  matter_id?: string;
  matter_name?: string;
};

type ThreadLoadOptions = { force?: boolean };

type ThreadLoader = (threadId: string, opts?: ThreadLoadOptions) => Promise<void>;

type ClearHandler = () => void;

type ChatSessionContextValue = {
  threadId: string | undefined;
  setThreadId: (id: string | undefined) => void;
  clearChat: () => void;
  historyVersion: number;
  bumpHistory: () => void;
  registerThreadLoader: (fn: ThreadLoader | null) => void;
  registerClearHandler: (fn: ClearHandler | null) => void;
  openThread: (threadId: string) => void;
};

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

const THREAD_STORAGE_KEY = "legalease_active_thread";

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [threadId, setThreadIdState] = useState<string | undefined>(() => {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem(THREAD_STORAGE_KEY) || undefined;
  });

  const setThreadId = useCallback((id: string | undefined) => {
    setThreadIdState(id);
    if (typeof window === "undefined") return;
    if (id) localStorage.setItem(THREAD_STORAGE_KEY, id);
    else localStorage.removeItem(THREAD_STORAGE_KEY);
  }, []);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [pendingThreadId, setPendingThreadId] = useState<string | undefined>();
  const loaderRef = useRef<ThreadLoader | null>(null);
  const clearRef = useRef<ClearHandler | null>(null);

  const registerThreadLoader = useCallback((fn: ThreadLoader | null) => {
    loaderRef.current = fn;
  }, []);

  const registerClearHandler = useCallback((fn: ClearHandler | null) => {
    clearRef.current = fn;
  }, []);

  useEffect(() => {
    if (pendingThreadId && loaderRef.current) {
      const tid = pendingThreadId;
      setPendingThreadId(undefined);
      void loaderRef.current(tid, { force: true });
    }
  }, [pendingThreadId]);

  const openThread = useCallback((tid: string) => {
    if (!tid) return;
    if (loaderRef.current) {
      loaderRef.current(tid);
      return;
    }
    setPendingThreadId(tid);
  }, []);

  const clearChat = useCallback(() => {
    setThreadId(undefined);
    setPendingThreadId(undefined);
    clearRef.current?.();
  }, [setThreadId]);

  const bumpHistory = useCallback(() => {
    setHistoryVersion((v) => v + 1);
  }, []);

  const value = useMemo(
    () => ({
      threadId,
      setThreadId,
      clearChat,
      historyVersion,
      bumpHistory,
      registerThreadLoader,
      registerClearHandler,
      openThread,
    }),
    [
      threadId,
      setThreadId,
      clearChat,
      historyVersion,
      bumpHistory,
      registerThreadLoader,
      registerClearHandler,
      openThread,
    ]
  );

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSession() {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error("useChatSession must be used within ChatSessionProvider");
  }
  return ctx;
}
