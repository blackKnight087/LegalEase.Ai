import { useCallback, useEffect, useMemo, useState } from "react";

const INTRO_KEY = "legalease_intro_seen";

/** Full story: 5 phases × 2s = 10s. Returning users: 3s total. */
export function useCinematicIntro() {
  const [introSeen] = useState(() => {
    try {
      return localStorage.getItem(INTRO_KEY) === "true";
    } catch {
      return false;
    }
  });

  const totalMs = introSeen ? 3000 : 10000;
  const phaseMs = totalMs / 5;

  const [phase, setPhase] = useState(0);
  const [done, setDone] = useState(false);
  const [skipped, setSkipped] = useState(false);

  const skip = useCallback(() => {
    setSkipped(true);
    setPhase(4);
    setDone(true);
    try {
      localStorage.setItem(INTRO_KEY, "true");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (skipped) return;
    if (phase >= 4) {
      const t = setTimeout(() => {
        setDone(true);
        try {
          localStorage.setItem(INTRO_KEY, "true");
        } catch {
          /* ignore */
        }
      }, phaseMs);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setPhase((p) => p + 1), phaseMs);
    return () => clearTimeout(t);
  }, [phase, phaseMs, skipped]);

  const showLogin = done || skipped;

  return useMemo(
    () => ({
      phase,
      done,
      skipped,
      showLogin,
      introSeen,
      totalMs,
      phaseMs,
      skip,
    }),
    [phase, done, skipped, showLogin, introSeen, totalMs, phaseMs, skip]
  );
}
