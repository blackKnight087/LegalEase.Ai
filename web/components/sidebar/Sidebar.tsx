"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLearnerMode } from "@/hooks/useLearnerMode";

const NAV_SECTIONS: Array<{
  label: string;
  items: Array<{ href: string; label: string; icon: string; learnerHide?: boolean }>;
}> = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "🏠" },
      { href: "/", label: "AI Assistant", icon: "💬" },
      { href: "/documents", label: "Documents", icon: "📂" },
    ],
  },
  {
    label: "Practice",
    items: [
      { href: "/matters", label: "Matters", icon: "📁" },
      { href: "/litigation", label: "Litigation", icon: "⚖️", learnerHide: true },
      { href: "/intake", label: "Intake Desk", icon: "📥", learnerHide: true },
      { href: "/collaboration", label: "Firm Chat", icon: "💬" },
      { href: "/billing", label: "Billing", icon: "💰", learnerHide: true },
      { href: "/discovery", label: "Evidence", icon: "🔍", learnerHide: true },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/drafting", label: "Drafting", icon: "📝" },
      { href: "/tools", label: "Legal Tools", icon: "🛠️" },
      { href: "/enterprise", label: "Enterprise", icon: "🚀", learnerHide: true },
      { href: "/analytics", label: "Analytics", icon: "📊", learnerHide: true },
    ],
  },
];

function isAdminUser(user: { username?: string; role?: string }) {
  const role = String(user.role || "").toLowerCase();
  if (role === "admin" || role === "superadmin") return true;
  return String(user.username || "").toLowerCase() === "admin";
}

export default function Sidebar({
  user,
  apiOnline,
  llmOnline,
  systemMessage = "",
  history,
  activeThreadId,
  historyError,
  onRefreshHistory,
  onNewChat,
  onLoadSession,
  onDeleteSession,
  onLogout,
  historyFilterMatterId = "",
  onHistoryFilterChange,
  mattersForFilter = [],
  mobileOpen = false,
  onMobileClose,
}: {
  user: { username: string; membership: string; role?: string };
  apiOnline: boolean;
  llmOnline: boolean;
  systemMessage?: string;
  historyError?: string;
  onRefreshHistory?: () => void;
  historyFilterMatterId?: string;
  onHistoryFilterChange?: (matterId: string) => void;
  mattersForFilter?: Array<{ matter_id: string; matter_name: string }>;
  history: Array<{
    thread_id?: string;
    id?: string;
    question: string;
    preview?: string;
    matter_id?: string;
    matter_name?: string;
  }>;
  activeThreadId?: string;
  onNewChat?: () => void;
  onLoadSession?: (s: {
    thread_id?: string;
    id?: string;
    question: string;
    preview?: string;
  }) => void;
  onDeleteSession?: (s: {
    thread_id?: string;
    id?: string;
    question: string;
    preview?: string;
  }) => void;
  onLogout: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}) {
  const pathname = usePathname();
  const { learnerMode } = useLearnerMode();
  const closeMobile = () => onMobileClose?.();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const navClass = (href: string) => {
    const active = isActive(href);
    return `le-nav-item le-interactive flex items-center gap-3 px-3 py-2.5 rounded-xl text-[0.8125rem] font-medium min-h-[44px] lg:min-h-0 ${
      active
        ? "le-nav-active text-white"
        : "text-slate-400 hover:bg-white/[0.07] hover:text-white"
    }`;
  };

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-50 flex flex-col justify-between
        w-[min(18rem,calc(100vw-2rem))] max-w-[85vw]
        bg-[var(--le-sidebar-bg)] text-white p-4 border-r border-[var(--le-sidebar-border)]
        transform transition-transform duration-300 ease-out
        lg:relative lg:translate-x-0 lg:w-72 lg:max-w-none lg:z-auto lg:shrink-0
        h-[100dvh] safe-top safe-bottom
        ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}
    >
      <div className="space-y-4 overflow-y-auto le-scroll flex-1 min-h-0 overscroll-contain">
        <div className="flex items-start gap-2.5">
          <span className="text-2xl">⚖️</span>
          <div className="min-w-0 flex-1">
            <h1 className="font-serif text-lg font-bold leading-tight">LegalEase.AI</h1>
            <p className="text-[0.68rem] text-slate-400">AI-Powered Legal Intelligence</p>
          </div>
          <button
            type="button"
            onClick={closeMobile}
            className="lg:hidden shrink-0 w-10 h-10 rounded-lg text-slate-300 hover:bg-white/10 hover:text-white"
            aria-label="Close menu"
          >
            ✕
          </button>
        </div>

        <div className="flex items-center gap-2 px-1">
          <span className="text-lg">👤</span>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate">{user.username}</p>
            <span className="inline-block mt-1 text-[0.62rem] font-bold px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-200 ring-1 ring-blue-400/20">
              {user.membership}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => onNewChat?.()}
          className="le-interactive w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-sm hover:shadow-md"
        >
          + New Chat
        </button>

        {learnerMode && (
          <p className="text-[0.65rem] text-emerald-300 px-2 py-1 bg-emerald-900/30 rounded-lg">
            Learner mode — simpler AI answers
          </p>
        )}

        <nav className="space-y-5">
          {NAV_SECTIONS.map((section) => {
            const items = section.items.filter((item) => !learnerMode || !item.learnerHide);
            if (!items.length) return null;
            return (
              <div key={section.label}>
                <p className="text-[0.6rem] font-bold uppercase tracking-[0.12em] text-slate-500 px-3 mb-1.5">
                  {section.label}
                </p>
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={navClass(item.href)}
                      onClick={closeMobile}
                    >
                      <span className="text-base opacity-90 w-5 text-center">{item.icon}</span>
                      {item.label}
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
          <div>
            <p className="text-[0.6rem] font-bold uppercase tracking-[0.12em] text-slate-500 px-3 mb-1.5">
              Account
            </p>
            <Link href="/settings" className={navClass("/settings")} onClick={closeMobile}>
              <span className="text-base opacity-90 w-5 text-center">⚙️</span>
              Settings
            </Link>
            {isAdminUser(user) && (
              <Link href="/admin" className={navClass("/admin")} onClick={closeMobile}>
                <span className="text-base opacity-90 w-5 text-center">🛡️</span>
                Admin
              </Link>
            )}
          </div>
        </nav>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[0.65rem] text-slate-500 font-semibold uppercase tracking-wider">
              Saved Chats
            </p>
            {onRefreshHistory && (
              <button
                type="button"
                onClick={onRefreshHistory}
                className="text-[0.65rem] text-slate-400 hover:text-white"
                title="Refresh chat list"
              >
                ↻
              </button>
            )}
          </div>
          {onHistoryFilterChange && mattersForFilter.length > 0 && (
            <select
              className="w-full mb-2 text-[0.65rem] bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
              value={historyFilterMatterId}
              onChange={(e) => onHistoryFilterChange(e.target.value)}
            >
              <option value="">All matters</option>
              {mattersForFilter.map((m) => (
                <option key={m.matter_id} value={m.matter_id}>
                  {m.matter_name}
                </option>
              ))}
            </select>
          )}
          {historyError && (
            <p className="text-[0.65rem] text-red-300 mb-2">{historyError}</p>
          )}
          {history.length === 0 && !historyError && (
            <p className="text-[0.65rem] text-slate-500 mb-2">
              No saved chats yet. Send a message to save one.
            </p>
          )}
          {history.length > 0 && (
            <div className="space-y-1 max-h-48 overflow-y-auto le-scroll">
              {history.map((h) => {
                const tid = h.thread_id || h.id || "";
                const active =
                  !!activeThreadId &&
                  (h.thread_id === activeThreadId || h.id === activeThreadId);
                return (
                  <div
                    key={tid || h.question}
                    className={`group flex items-center gap-0.5 rounded transition-colors ${
                      active ? "bg-blue-500/20" : "hover:bg-white/5"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onLoadSession?.(h)}
                      title={h.preview || h.question}
                      className={`flex-1 min-w-0 text-left text-xs truncate py-1.5 pl-2 pr-0.5 rounded-l ${
                        active ? "text-white" : "text-slate-400 group-hover:text-white"
                      }`}
                    >
                      <span className="block truncate">{h.question || "Chat"}</span>
                      {h.matter_name && (
                        <span className="block text-[0.55rem] text-blue-300/80 truncate">
                          {h.matter_name}
                        </span>
                      )}
                    </button>
                    {onDeleteSession && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(h);
                        }}
                        title="Delete chat"
                        aria-label={`Delete chat: ${h.question || "Chat"}`}
                        className="shrink-0 px-1.5 py-1 rounded-r text-[0.6rem] font-semibold text-red-300/90 hover:text-red-200 hover:bg-red-500/20 border-l border-white/5"
                      >
                        Del
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="pt-3 border-t border-white/10 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <span
            className={`w-2 h-2 rounded-full ${apiOnline ? "bg-green-400" : "bg-red-400"}`}
          />
          <span className="text-xs text-slate-400">
            {apiOnline ? "API connected" : "Connecting to API…"}
          </span>
        </div>
        <div className="flex items-center gap-2 mb-2">
          <span
            className={`w-2 h-2 rounded-full ${llmOnline ? "bg-green-400" : "bg-amber-400"}`}
          />
          <span className="text-xs text-slate-400">
            {llmOnline
              ? "LLM ready"
              : apiOnline
                ? "LLM starting…"
                : "LLM waiting for API"}
          </span>
        </div>
        {systemMessage ? (
          <p className="text-[0.65rem] text-slate-500 mb-2 leading-snug" title={systemMessage}>
            {systemMessage}
          </p>
        ) : null}
        <button
          type="button"
          onClick={onLogout}
          className="text-xs text-slate-500 hover:text-white w-full text-left py-1"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
