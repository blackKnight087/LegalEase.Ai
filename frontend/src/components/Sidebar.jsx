import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import LegalEaseLogo from "./LegalEaseLogo.jsx";

const navClass = ({ isActive }) =>
  `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
    isActive
      ? "bg-blue-500/25 text-white shadow-sm"
      : "text-slate-300 hover:bg-white/10 hover:text-white"
  }`;

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "🏠" },
  { to: "/", label: "AI Assistant", icon: "💬", end: true },
  { to: "/documents", label: "Documents", icon: "📂" },
  { to: "/tools", label: "Legal Tools", icon: "🛠️" },
  { to: "/drafting", label: "Drafting", icon: "📝" },
  { to: "/analytics", label: "Analytics", icon: "📊" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

export default function Sidebar({ history = [], onNewChat, onLoadSession, llmOnline }) {
  const { user, logout } = useAuth();

  return (
    <aside className="w-72 h-full flex flex-col justify-between bg-navy text-white p-4 select-none shrink-0">
      <div className="space-y-4 overflow-y-auto le-scroll flex-1 min-h-0">
        <div className="flex items-start gap-2.5">
          <LegalEaseLogo size={40} showText={false} />
          <div>
            <h1 className="font-serif text-lg font-bold leading-tight">LegalEase.AI</h1>
            <p className="text-[0.68rem] text-slate-400">AI-Powered Legal Intelligence</p>
          </div>
        </div>

        {user && (
          <div className="flex items-center gap-2 px-1">
            <span className="text-lg">👤</span>
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{user.username}</p>
              <span className="inline-block mt-0.5 text-[0.62rem] font-bold px-2 py-0.5 rounded-full bg-blue-600/50 text-blue-100">
                {user.membership}
              </span>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={onNewChat}
          className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
        >
          + New Chat
        </button>

        <nav className="space-y-0.5">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {history?.length > 0 && (
          <div>
            <p className="text-[0.65rem] text-slate-500 font-semibold uppercase tracking-wider mb-2">
              Recent
            </p>
            <div className="space-y-1">
              {history.map((h) => (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => onLoadSession?.(h)}
                  className="w-full text-left text-xs text-slate-400 hover:text-white truncate py-1 px-2 rounded hover:bg-white/5"
                >
                  {h.title || "Session"}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-white/10 shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <span className={`w-2 h-2 rounded-full ${llmOnline ? "bg-green-400" : "bg-red-400"}`} />
          <span className="text-xs text-slate-400">{llmOnline ? "LLM Online" : "LLM Offline"}</span>
        </div>
        <button type="button" onClick={logout} className="text-xs text-slate-500 hover:text-white w-full text-left py-1">
          Logout
        </button>
      </div>
    </aside>
  );
}
