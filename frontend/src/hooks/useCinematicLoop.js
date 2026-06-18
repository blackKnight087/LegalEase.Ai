import { useCallback, useEffect, useState } from "react";

const PHASE_COUNT = 5;
const CYCLE_MS = 10000;

/**
 * 10s cinematic sequence (2s per phase):
 * 0 chamber · 1 figures · 2 network · 3 logo reveal · 4 tagline + login
 */
export function useCinematicLoop() {
  const [phase, setPhase] = useState(0);
  const [loginReady, setLoginReady] = useState(false);
  const [cycle, setCycle] = useState(0);

  const phaseMs = CYCLE_MS / PHASE_COUNT;

  const skipToReady = useCallback(() => {
    setPhase(4);
    setLoginReady(true);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setPhase((p) => {
        if (p >= PHASE_COUNT - 1) {
          setCycle((c) => c + 1);
          return p;
        }
        return p + 1;
      });
    }, phaseMs);
    return () => clearInterval(timer);
  }, [phaseMs]);

  useEffect(() => {
    if (!loginReady && (cycle >= 1 || phase >= 4)) {
      const t = setTimeout(() => setLoginReady(true), phase >= 4 ? 700 : 0);
      return () => clearTimeout(t);
    }
  }, [phase, cycle, loginReady]);

  return { phase, loginReady, skipToReady, phaseMs };
}
