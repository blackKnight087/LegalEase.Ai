"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import MatterWorkspaceNav from "@/components/matters/MatterWorkspaceNav";
import MatterDeleteButton from "@/components/matters/MatterDeleteButton";
import { ButtonLink } from "@/components/ui/Button";
import * as api from "@/lib/api";
import { useMatterNotifications } from "@/hooks/useMatterNotifications";

export default function MatterWorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const matterId = String(params.matterId || "");
  const [matter, setMatter] = useState<api.Matter | null>(null);
  const { items: notifications } = useMatterNotifications(true);

  useEffect(() => {
    if (!matterId) return;
    api.getMatter(matterId).then(setMatter).catch(() => setMatter(null));
    if (typeof window !== "undefined") {
      localStorage.setItem("legalease_active_matter", matterId);
    }
  }, [matterId]);

  useEffect(() => {
    if (!matterId || typeof window === "undefined") return;
    const base = `/matters/${matterId}`;
    if (pathname !== base && pathname !== `${base}/`) return;
    const saved = window.sessionStorage.getItem(`legalease_matter_tab:${matterId}`);
    if (saved && saved.startsWith(base) && saved !== pathname) {
      router.replace(saved);
    }
  }, [matterId, pathname, router]);

  const matterAlerts = notifications.filter((n) => n.matter_id === matterId);

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-50/80">
      <PageHeader
        title={matter?.matter_name || "Matter workspace"}
        subtitle={
          matter
            ? `${matter.matter_type || matter.practice_area} · ${matter.status_tier || "Open"}${matter.venue ? ` · ${matter.venue}` : ""}`
            : "Loading…"
        }
      >
        <ButtonLink href={`/?matter=${matterId}`} variant="secondary" size="sm">
          Chat
        </ButtonLink>
        {matter && (
          <MatterDeleteButton
            matterId={matterId}
            matterName={matter.matter_name || ""}
            onDeleted={() => router.push("/matters")}
          />
        )}
      </PageHeader>

      {matterAlerts.length > 0 && (
        <div className="mx-3 sm:mx-6 mb-2 text-xs bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-amber-900 lg:mx-6">
          {matterAlerts.slice(0, 3).map((n, i) => (
            <span key={i} className="block truncate">
              {String(n.title)}
              {n.date ? ` — ${String(n.date)}` : ""}
            </span>
          ))}
        </div>
      )}

      {/* Mobile: nav strip + content stack */}
      <div className="lg:hidden shrink-0 border-b border-slate-200 bg-white px-3 py-2">
        <MatterWorkspaceNav matterId={matterId} />
        <div className="flex gap-2 mt-2">
          <Link
            href="/matters"
            className="text-xs text-slate-500 hover:text-navy py-1"
          >
            ← All matters
          </Link>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden">
        <aside className="hidden lg:flex w-52 shrink-0 border-r border-slate-200 bg-white p-4 flex-col gap-3">
          <MatterWorkspaceNav matterId={matterId} />
          <ButtonLink href={`/?matter=${matterId}`} variant="secondary" size="sm" className="w-full">
            Open in main chat
          </ButtonLink>
          <Link href="/matters" className="text-xs text-slate-500 hover:text-navy text-center">
            All matters
          </Link>
        </aside>
        <main className="flex-1 overflow-y-auto overflow-x-hidden le-scroll p-3 sm:p-6 min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
