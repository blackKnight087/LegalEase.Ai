"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import MissionControlTab from "@/components/litigation/MissionControlTab";
import HearingsTab from "@/components/litigation/HearingsTab";
import CalendarTab from "@/components/litigation/CalendarTab";
import LitigationTasksTab from "@/components/litigation/LitigationTasksTab";
import OrdersTab from "@/components/litigation/OrdersTab";
import AnalyticsTab from "@/components/litigation/AnalyticsTab";
import LitigationAITab from "@/components/litigation/LitigationAITab";
import WarRoomTab from "@/components/litigation/WarRoomTab";
import CourtDayTab from "@/components/litigation/CourtDayTab";
import EvidenceTab from "@/components/litigation/EvidenceTab";
import LimitationTab from "@/components/litigation/LimitationTab";
import CourtSyncTab from "@/components/litigation/CourtSyncTab";
import WatchlistTab from "@/components/litigation/WatchlistTab";
import * as api from "@/lib/api";

const TAB_IDS = [
  "mission-control",
  "hearings",
  "calendar",
  "court-day",
  "court-sync",
  "tasks",
  "orders",
  "evidence",
  "limitation",
  "watchlist",
  "analytics",
  "ai",
  "war-room",
] as const;

type TabId = (typeof TAB_IDS)[number];

const TAB_LABELS: Record<TabId, string> = {
  "mission-control": "Mission Control",
  hearings: "Hearings",
  calendar: "Calendar",
  "court-day": "Cause List",
  "court-sync": "Court Sync",
  tasks: "Tasks",
  orders: "Orders",
  evidence: "Evidence",
  limitation: "Limitation",
  watchlist: "Watchlist",
  analytics: "Analytics",
  ai: "AI Assistant",
  "war-room": "War Room",
};

function LitigationNotifications() {
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    void api.fetchLitigationNotifications().then((r) => {
      setCount(r.unread_count || 0);
      setItems(r.notifications || []);
    }).catch(() => {
      /* optional */
    });
  }, []);

  if (count === 0) return null;

  return (
    <div className="relative">
      <button
        type="button"
        className="relative p-2 rounded-lg border border-slate-200 hover:bg-slate-50"
        aria-label="Notifications"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>🔔</span>
        <span className="absolute -top-1 -right-1 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center">
          {count > 9 ? "9+" : count}
        </span>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-72 max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lg z-20 p-2 text-xs">
          {items.slice(0, 8).map((n, i) => (
            <Link
              key={i}
              href={`/litigation?tab=${n.href_tab || "mission-control"}${n.matter_id ? `&matter=${n.matter_id}` : ""}`}
              className="block px-2 py-1.5 rounded hover:bg-slate-50 text-amber-900"
              onClick={() => setOpen(false)}
            >
              {String(n.message)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function LitigationDeskContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const tabParam = searchParams.get("tab") || "";
  const activeTab: TabId = TAB_IDS.includes(tabParam as TabId) ? (tabParam as TabId) : "mission-control";

  const setTab = useCallback(
    (tab: TabId) => {
      const q = tab === "mission-control" ? "" : `?tab=${tab}`;
      const matter = searchParams.get("matter");
      const mq = matter && tab === "war-room" ? `${q ? q + "&" : "?"}matter=${matter}` : q;
      router.replace(`/litigation${mq}`, { scroll: false });
    },
    [router, searchParams]
  );

  const tabs = useMemo(() => TAB_IDS.map((id) => ({ id, label: TAB_LABELS[id] })), []);

  return (
    <>
      <div className="border-b border-slate-200 bg-white px-3 sm:px-6 lg:px-8 overflow-x-auto touch-scroll-x">
        <div className="flex gap-1 min-w-max">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`le-interactive px-3 py-3 text-xs sm:text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${
                activeTab === t.id
                  ? "border-navy text-navy"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-6xl mx-auto w-full">
        {activeTab === "mission-control" && <MissionControlTab />}
        {activeTab === "hearings" && <HearingsTab />}
        {activeTab === "calendar" && <CalendarTab />}
        {activeTab === "court-day" && <CourtDayTab />}
        {activeTab === "court-sync" && <CourtSyncTab />}
        {activeTab === "tasks" && <LitigationTasksTab />}
        {activeTab === "orders" && <OrdersTab />}
        {activeTab === "evidence" && <EvidenceTab />}
        {activeTab === "limitation" && <LimitationTab />}
        {activeTab === "watchlist" && <WatchlistTab />}
        {activeTab === "analytics" && <AnalyticsTab />}
        {activeTab === "ai" && <LitigationAITab />}
        {activeTab === "war-room" && <WarRoomTab />}
      </div>
    </>
  );
}

export default function LitigationDeskPage() {
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-start justify-between gap-3 px-3 sm:px-6 lg:px-8 pt-2">
        <PageHeader
          title="Litigation Desk"
          subtitle="Mission Control for hearings, deadlines, cause lists, evidence, and court practice"
        />
        <div className="pt-4 shrink-0">
          <LitigationNotifications />
        </div>
      </div>
      <Suspense fallback={<p className="p-6 text-slate-500 text-sm">Loading Litigation Desk…</p>}>
        <LitigationDeskContent />
      </Suspense>
    </div>
  );
}
