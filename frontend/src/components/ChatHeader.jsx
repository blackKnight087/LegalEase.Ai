const MODES = [
  { id: "knowledge_base", label: "📚 Knowledge Base" },
  { id: "web_search", label: "🌐 Open Law" },
  { id: "deep_case", label: "⚖️ Hybrid Engine", proOnly: true },
];

export default function ChatHeader({ mode, onModeChange, membership }) {
  return (
    <header className="shrink-0 flex items-center gap-4 px-6 py-3 border-b border-slate-200/80 bg-canvas/95 backdrop-blur-sm">
      <h2 className="font-serif text-xl font-bold text-navy shrink-0">LegalEase Assistant</h2>
      <div className="flex flex-wrap gap-2 flex-1 justify-center">
        {MODES.map((m) => {
          if (m.proOnly && !["Pro", "Legal Pro"].includes(membership)) return null;
          const active = mode === m.id;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => onModeChange(m.id)}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-200 ${
                active
                  ? "bg-navy text-white border-navy shadow-sm"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
              }`}
            >
              {m.label}
            </button>
          );
        })}
      </div>
    </header>
  );
}
