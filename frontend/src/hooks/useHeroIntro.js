import { useCallback, useEffect, useState } from "react";

const KEY = "legalease_intro_seen";

/** 10s full / 3s returning — drives hero cinematic only */
export function useHeroIntro() {
  const seen = (() => {
    try {
      return localStorage.getItem(KEY) === "true";
    } catch {
      return false;
    }
  })();

  const totalMs = seen ? 3000 : 10000;
  const phaseMs = totalMs / 5;

  const [phase, setPhase] = useState(0);
  const [complete, setComplete] = useState(seen);

  const skip = useCallback(() => {
    setPhase(4);
    setComplete(true);
    try {
      localStorage.setItem(KEY, "true");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (complete) return;
    if (phase >= 4) {
      const t = setTimeout(() => {
        setComplete(true);
        try {
          localStorage.setItem(KEY, "true");
        } catch {
          /* ignore */
        }
      }, phaseMs);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setPhase((p) => p + 1), phaseMs);
    return () => clearTimeout(t);
  }, [phase, phaseMs, complete]);

  return { phase, complete, skip, seen, phaseMs };
}
