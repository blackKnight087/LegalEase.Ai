"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import MobileBottomNav from "@/components/layout/MobileBottomNav";
import MobileTopBar from "@/components/layout/MobileTopBar";
import Sidebar from "@/components/sidebar/Sidebar";
import { useApiConnection } from "@/components/providers/ApiConnectionProvider";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  ChatSessionProvider,
  useChatSession,
  type HistoryItem,
} from "@/components/providers/ChatSessionProvider";
import { deleteChatThread, getChatHistory, listMattersSummary } from "@/lib/api";
import { clearChatCache } from "@/lib/chatStorage";

const PAGE_TITLES: Record<string, string> = {
  "/": "AI Assistant",
  "/dashboard": "Dashboard",
  "/intake": "Intake Desk",
  "/collaboration": "Firm Chat",
  "/matters": "Matters",
  "/documents": "Documents",
  "/settings": "Settings",
  "/billing": "Billing",
  "/litigation": "Litigation",
  "/drafting": "Drafting",
  "/discovery": "Evidence Intelligence",
  "/tools": "Legal Tools",
  "/analytics": "Analytics",
  "/enterprise": "Enterprise",
  "/admin": "Admin",
  "/tools/ipc-bns": "IPC ↔ BNS",
};

function mobilePageTitle(pathname: string): string {
  if (pathname.startsWith("/intake/")) return "Intake";
  if (pathname.startsWith("/matters/")) return "Matter";
  if (pathname.startsWith("/drafting/")) return "Drafting";
  if (pathname.startsWith("/settings/")) return "Settings";
  for (const [prefix, title] of Object.entries(PAGE_TITLES)) {
    if (prefix === "/" ? pathname === "/" : pathname.startsWith(prefix)) return title;
  }
  return "LegalEase.AI";
}

function AppLayoutInner({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const { apiOnline, llmOnline, checking, connectionChecked, systemMessage } =
    useApiConnection();
  const { clearChat, historyVersion, threadId, openThread, bumpHistory } =
    useChatSession();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyError, setHistoryError] = useState("");
  const lastHistoryFetchRef = useRef(0);
  const [historyMatterFilter, setHistoryMatterFilter] = useState("");
  const [mattersForFilter, setMattersForFilter] = useState<
    Array<{ matter_id: string; matter_name: string }>
  >([]);

  const fetchHistory = useCallback((opts?: { force?: boolean }) => {
    if (!user) return;
    const now = Date.now();
    if (!opts?.force && now - lastHistoryFetchRef.current < 8000) {
      return;
    }
    lastHistoryFetchRef.current = now;
    getChatHistory(50, historyMatterFilter)
      .then((r) => {
        setHistoryError("");
        const items = (r.sessions || [])
          .map((s) => ({
            thread_id: String(s.thread_id || s.id || ""),
            id: String(s.thread_id || s.id || ""),
            question: String(s.question || "Chat"),
            preview: String(s.preview || ""),
            mode: String(s.mode || ""),
            language: String(s.language || ""),
            created_at: String(s.created_at || ""),
            matter_id: String(s.matter_id || ""),
            matter_name: String(s.matter_name || ""),
          }))
          .filter((s) => s.thread_id);
        setHistory(items);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "Could not load chat history";
        if (/429|rate limit/i.test(msg)) {
          setHistoryError("Too many requests — wait a moment, then click ↻ refresh.");
        } else {
          setHistoryError(msg);
        }
        setHistory([]);
      });
  }, [user, historyMatterFilter]);

  useEffect(() => {
    if (!user) return;
    listMattersSummary().then((r) =>
      setMattersForFilter(
        (r.matters || []).map((m) => ({
          matter_id: m.matter_id,
          matter_name: m.matter_name,
        }))
      )
    );
  }, [user]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [navOpen]);

  useEffect(() => {
    fetchHistory({ force: true });
  }, [user, historyVersion, fetchHistory]);

  useEffect(() => {
    const onFocus = () => fetchHistory();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetchHistory]);

  const onNewChat = () => {
    clearChat();
    router.replace("/");
  };

  const onLoadSession = (item: HistoryItem) => {
    const tid = (item.thread_id || item.id || "").trim();
    if (!tid) return;
    openThread(tid);
    router.push(`/?thread=${encodeURIComponent(tid)}`);
  };

  const onDeleteSession = useCallback(
    async (item: HistoryItem) => {
      const tid = (item.thread_id || item.id || "").trim();
      if (!tid) return;
      const label = item.question || item.preview || "this chat";
      if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return;
      try {
        await deleteChatThread(tid);
        setHistory((prev) =>
          prev.filter((h) => (h.thread_id || h.id || "") !== tid)
        );
        if (threadId === tid) {
          clearChatCache();
          clearChat();
          router.replace("/");
        }
        bumpHistory();
      } catch (e) {
        setHistoryError(
          e instanceof Error ? e.message : "Could not delete chat"
        );
      }
    },
    [threadId, clearChat, router, bumpHistory]
  );

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-slate-500 px-6 text-center">
        <p>Loading…</p>
        {connectionChecked && !checking && !apiOnline && (
          <p className="text-sm text-amber-700 max-w-md">
            {typeof window !== "undefined" &&
            (window.location.hostname === "localhost" ||
              window.location.hostname === "127.0.0.1") ? (
              <>
                Backend not reachable. Run{" "}
                <code className="bg-slate-100 px-1 rounded">.\run_backend.ps1</code> in a
                terminal.
              </>
            ) : (
              <>Server not reachable — it may be restarting. Try again in a moment.</>
            )}
          </p>
        )}
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-[100dvh] overflow-hidden le-app-bg">
      {navOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          aria-label="Close menu"
          onClick={() => setNavOpen(false)}
        />
      )}
      <Sidebar
        user={user}
        apiOnline={apiOnline}
        llmOnline={llmOnline}
        systemMessage={systemMessage}
        history={history}
        historyError={historyError}
        onRefreshHistory={() => fetchHistory({ force: true })}
        activeThreadId={threadId}
        onNewChat={() => {
          onNewChat();
          setNavOpen(false);
        }}
        onLoadSession={(item) => {
          onLoadSession(item);
          setNavOpen(false);
        }}
        onDeleteSession={onDeleteSession}
        onLogout={logout}
        historyFilterMatterId={historyMatterFilter}
        onHistoryFilterChange={setHistoryMatterFilter}
        mattersForFilter={mattersForFilter}
        mobileOpen={navOpen}
        onMobileClose={() => setNavOpen(false)}
      />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <MobileTopBar
          onOpenMenu={() => setNavOpen(true)}
          title={mobilePageTitle(pathname)}
        />
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden min-h-0 le-main-pad-bottom lg:pb-0">
          {children}
        </main>
        <MobileBottomNav onOpenMenu={() => setNavOpen(true)} />
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ChatSessionProvider>
      <AppLayoutInner>{children}</AppLayoutInner>
    </ChatSessionProvider>
  );
}
