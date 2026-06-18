"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getHealthLlm, pingApiLive } from "@/lib/api";

const POLL_ONLINE_MS = 15000;
const POLL_OFFLINE_MS = 10000;
const PING_TIMEOUT_MS = 10000;
const OFFLINE_FAIL_STREAK = 5;

type ApiConnectionCtx = {
  apiOnline: boolean;
  llmOnline: boolean;
  checking: boolean;
  connectionChecked: boolean;
  lastChecked: number | null;
  systemMessage: string;
  refreshConnection: () => Promise<boolean>;
};

const ApiConnectionContext = createContext<ApiConnectionCtx | null>(null);

export function ApiConnectionProvider({ children }: { children: ReactNode }) {
  const [apiOnline, setApiOnline] = useState(false);
  const [llmOnline, setLlmOnline] = useState(false);
  const [checking, setChecking] = useState(true);
  const [connectionChecked, setConnectionChecked] = useState(false);
  const [lastChecked, setLastChecked] = useState<number | null>(null);
  const [systemMessage, setSystemMessage] = useState("");
  const inflightRef = useRef<Promise<boolean> | null>(null);
  const lastOnlineRef = useRef(false);
  const failStreakRef = useRef(0);

  const refreshConnection = useCallback(async (): Promise<boolean> => {
    if (inflightRef.current) {
      return inflightRef.current;
    }

    const run = async (): Promise<boolean> => {
      setChecking(true);
      try {
        await pingApiLive(PING_TIMEOUT_MS);
        failStreakRef.current = 0;
        setApiOnline(true);
        lastOnlineRef.current = true;
        void getHealthLlm()
          .then((h) => setLlmOnline(!!h.llm_ready))
          .catch(() => {
            setLlmOnline(false);
          });
        void fetch("/api/v1/health/stability", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .then((p) => {
            if (p?.message) setSystemMessage(String(p.message));
          })
          .catch(() => {});
        return true;
      } catch {
        failStreakRef.current += 1;
        // During heavy re-index the API can be slow — do not flash offline on brief timeouts.
        if (failStreakRef.current >= OFFLINE_FAIL_STREAK) {
          setApiOnline(false);
          setLlmOnline(false);
          lastOnlineRef.current = false;
        }
        return lastOnlineRef.current;
      } finally {
        setConnectionChecked(true);
        setLastChecked(Date.now());
        setChecking(false);
        inflightRef.current = null;
      }
    };

    inflightRef.current = run();
    return inflightRef.current;
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timerId = 0;
    const tick = async () => {
      await refreshConnection();
      if (cancelled) return;
      const ms = lastOnlineRef.current ? POLL_ONLINE_MS : POLL_OFFLINE_MS;
      timerId = window.setTimeout(() => void tick(), ms);
    };
    void tick();
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshConnection();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshConnection]);

  return (
    <ApiConnectionContext.Provider
      value={{
        apiOnline,
        llmOnline,
        checking,
        connectionChecked,
        lastChecked,
        systemMessage,
        refreshConnection,
      }}
    >
      {children}
    </ApiConnectionContext.Provider>
  );
}

export function useApiConnection() {
  const ctx = useContext(ApiConnectionContext);
  if (!ctx) throw new Error("useApiConnection outside ApiConnectionProvider");
  return ctx;
}
