"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clearFirmChat429, recordFirmChat429 } from "@/lib/firmChatDiagnostics";

const BANNER_MS = 5000;

export function isRateLimitError(message: string): boolean {
  return /429|rate limit exceeded/i.test(message);
}

export function parseLimiterRule(message: string): string {
  const m = message.match(/X-RateLimit-Rule[:\s]+(\w+)/i);
  return m?.[1] || "";
}

/** Show rate-limit banner only on genuine 429; auto-hide after 5s; clear on success. */
export function useFirmChatRateLimitBanner() {
  const [banner, setBanner] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearBanner = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setBanner("");
    clearFirmChat429();
  }, []);

  const showRateLimit = useCallback((source: string, message?: string) => {
    if (!isRateLimitError(message || "429")) return;
    const rule = parseLimiterRule(message || "");
    recordFirmChat429(source, rule);
    setBanner("Rate limit exceeded. Try again in a minute.");
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setBanner("");
      timerRef.current = null;
    }, BANNER_MS);
  }, []);

  const onRequestSuccess = useCallback(() => {
    clearBanner();
  }, [clearBanner]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return { banner, showRateLimit, onRequestSuccess, clearBanner };
}
