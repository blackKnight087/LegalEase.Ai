"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

export function useMatterNotifications(enabled = true) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);

  const [hearingsToday, setHearingsToday] = useState(0);

  const refresh = useCallback(() => {
    if (!enabled) return;
    api.fetchMatterNotifications().then((r) => setItems(r.notifications || [])).catch(() => {});
    api
      .fetchHearingDigest(14)
      .then((d) => setHearingsToday(d.today?.length ?? 0))
      .catch(() => setHearingsToday(0));
  }, [enabled]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 120000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  }, [enabled]);

  const notifyBrowser = useCallback((title: string, body: string) => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission === "granted") {
      new Notification(title, { body });
    }
  }, []);

  return { items, hearingsToday, refresh, notifyBrowser };
}
