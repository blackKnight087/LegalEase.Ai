"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, FileText, LogOut, MessageSquare, Scale } from "lucide-react";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { useAuthStore } from "@/store/authStore";
import { useEffect } from "react";

const nav = [
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText },
];

const routeMeta: Record<string, { section: string; page: string }> = {
  "/assistant": { section: "Research", page: "Legal Research Chamber" },
  "/documents": { section: "Archive", page: "Document Archive & Indexing" },
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, userEmail, isAuthenticated } = useAuthStore();
  const meta = routeMeta[pathname] ?? { section: "Workspace", page: "Legal Intelligence Archive" };

  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  if (!isAuthenticated) return null;

  return (
    <div className="min-h-screen w-full archive-bg">
      <div className="mx-auto flex min-h-screen max-w-[1500px] gap-6 p-4">
        <aside className="glass-card archive-panel-enter w-72 shrink-0 rounded-2xl border border-white/10 p-4">
          <div className="mb-6 flex items-center gap-3">
            <Scale className="h-7 w-7 text-amber-400" />
            <div>
              <div className="text-lg font-semibold text-slate-100">LegalEase.AI</div>
              <div className="text-xs uppercase tracking-[0.14em] text-slate-400">Legal Intelligence Archive</div>
            </div>
          </div>

          <ConnectionStatus />
          <nav className="mt-6 space-y-1.5" aria-label="Primary">
            {nav.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`nav-link group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors duration-300 ${
                    active ? "bg-amber-500/14 text-amber-50" : "text-slate-300 hover:bg-white/8 hover:text-slate-100"
                  }`}
                >
                  <span
                    className={`nav-rail absolute bottom-2 left-0 top-2 w-1 rounded-r-full bg-amber-400 transition-all duration-300 ${
                      active ? "opacity-100" : "opacity-0 group-hover:opacity-40"
                    }`}
                    aria-hidden
                  />
                  <Icon className={`h-4 w-4 transition-colors duration-300 ${active ? "text-amber-300" : "text-slate-400"}`} />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-8 border-t border-white/10 pt-4 text-xs text-slate-400">
            Authorized profile: {userEmail ?? "Not signed in"}
          </div>
          <button
            onClick={logout}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 transition-colors duration-300 hover:bg-rose-500/20"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </aside>

        <main className="glass-card archive-panel-enter min-h-[calc(100vh-2rem)] flex-1 rounded-2xl border border-white/10 p-6 [animation-delay:80ms]">
          <nav aria-label="Archive context" className="archive-breadcrumb mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-4 py-2.5 text-xs">
            <span className="uppercase tracking-[0.16em] text-slate-500">Archive</span>
            <ChevronRight className="h-3.5 w-3.5 text-slate-600" aria-hidden />
            <span className="font-medium text-slate-300">{meta.section}</span>
            <ChevronRight className="h-3.5 w-3.5 text-slate-600" aria-hidden />
            <span className="text-amber-100/90">{meta.page}</span>
          </nav>
          <div className="archive-content-enter">{children}</div>
        </main>
      </div>
    </div>
  );
}
