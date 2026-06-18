"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "", label: "Overview" },
  { href: "/documents", label: "Docs" },
  { href: "/timeline", label: "Timeline" },
  { href: "/hearings", label: "Hearings" },
  { href: "/tasks", label: "Tasks" },
  { href: "/evidence", label: "Evidence" },
  { href: "/entities", label: "Parties" },
  { href: "/contradictions", label: "Issues" },
  { href: "/knowledge", label: "KB" },
  { href: "/ai", label: "AI" },
  { href: "/discussion", label: "Case Chat" },
  { href: "/history", label: "Chats" },
  { href: "/settings", label: "Settings" },
];

const TAB_KEY = "legalease_matter_tab";

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`shrink-0 rounded-lg px-3 py-2 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap min-h-[40px] sm:min-h-0 flex items-center ${
        active ? "bg-navy text-white shadow-sm" : "text-slate-700 hover:bg-slate-100 bg-white border border-slate-200/80 sm:border-0 sm:bg-transparent"
      }`}
    >
      {label}
    </Link>
  );
}

export default function MatterWorkspaceNav({ matterId }: { matterId: string }) {
  const pathname = usePathname();
  const base = `/matters/${matterId}`;

  useEffect(() => {
    if (typeof window === "undefined" || !pathname.startsWith(base)) return;
    window.sessionStorage.setItem(`${TAB_KEY}:${matterId}`, pathname);
  }, [pathname, matterId, base]);

  return (
    <>
      {/* Mobile: horizontal scroll */}
      <nav
        className="lg:hidden flex gap-1.5 overflow-x-auto touch-scroll-x pb-1 -mx-1 px-1 snap-x-child"
        aria-label="Matter sections"
      >
        {LINKS.map((l) => {
          const href = `${base}${l.href}`;
          const active =
            l.href === ""
              ? pathname === base || pathname === `${base}/`
              : pathname.startsWith(href);
          return <NavLink key={l.href} href={href} label={l.label} active={active} />;
        })}
      </nav>

      {/* Desktop: vertical */}
      <nav className="hidden lg:flex flex-col gap-0.5 text-sm">
        {LINKS.map((l) => {
          const href = `${base}${l.href}`;
          const active =
            l.href === ""
              ? pathname === base || pathname === `${base}/`
              : pathname.startsWith(href);
          return (
            <Link
              key={l.href}
              href={href}
              className={`rounded-lg px-3 py-2 font-medium transition-colors ${
                active ? "bg-navy text-white" : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              {l.label === "Docs" ? "Documents" : l.label === "Parties" ? "Entities" : l.label === "Issues" ? "Contradictions" : l.label === "KB" ? "Knowledge" : l.label === "Chats" ? "Chat history" : l.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
