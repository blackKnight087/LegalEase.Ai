"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/dashboard", label: "Home", icon: "🏠", match: (p: string) => p === "/dashboard" },
  { href: "/", label: "Chat", icon: "💬", match: (p: string) => p === "/" },
  { href: "/matters", label: "Matters", icon: "📁", match: (p: string) => p.startsWith("/matters") },
  { href: "/documents", label: "Docs", icon: "📂", match: (p: string) => p.startsWith("/documents") },
] as const;

type Props = {
  onOpenMenu: () => void;
};

export default function MobileBottomNav({ onOpenMenu }: Props) {
  const pathname = usePathname();

  return (
    <nav
      className="lg:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-200/90 bg-white/95 backdrop-blur-md safe-bottom pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]"
      aria-label="Main navigation"
    >
      <div className="grid grid-cols-5 h-[3.25rem] max-w-lg mx-auto">
        {ITEMS.map((item) => {
          const active = item.match(pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center gap-0.5 text-[0.6rem] font-semibold no-underline transition-colors min-h-[52px] ${
                active ? "text-blue-600" : "text-slate-500"
              }`}
            >
              <span className={`text-lg leading-none ${active ? "scale-110" : ""}`} aria-hidden>
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={onOpenMenu}
          className="flex flex-col items-center justify-center gap-0.5 text-[0.6rem] font-semibold text-slate-500 min-h-[52px]"
          aria-label="More menu"
        >
          <span className="text-lg leading-none" aria-hidden>
            ☰
          </span>
          More
        </button>
      </div>
    </nav>
  );
}
