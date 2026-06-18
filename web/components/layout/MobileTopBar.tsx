"use client";

type Props = {
  onOpenMenu: () => void;
  title?: string;
};

export default function MobileTopBar({ onOpenMenu, title = "LegalEase.AI" }: Props) {
  return (
    <header className="lg:hidden sticky top-0 z-30 border-b border-slate-200/90 bg-white/95 backdrop-blur-md safe-top pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
      <div className="h-0.5 w-full bg-gradient-to-r from-blue-600 via-indigo-500 to-blue-400" />
      <div className="flex items-center gap-3 px-3 py-2.5">
        <button
          type="button"
          onClick={onOpenMenu}
          className="shrink-0 flex items-center justify-center w-11 h-11 rounded-xl border border-slate-200/80 bg-white text-slate-700 shadow-sm hover:bg-slate-50 active:scale-[0.98] transition-transform"
          aria-label="Open menu"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M4 7h16M4 12h16M4 17h16"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <div className="min-w-0 flex-1 flex items-center gap-2">
          <span className="text-lg" aria-hidden>
            ⚖️
          </span>
          <p className="font-semibold text-sm text-slate-900 truncate m-0">{title}</p>
        </div>
      </div>
    </header>
  );
}
