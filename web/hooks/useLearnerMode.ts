"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

export function useLearnerMode() {
  const [learnerMode, setLearnerModeState] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const p = await api.fetchAccountPreferences();
      setLearnerModeState(!!p.learner_mode);
    } catch {
      setLearnerModeState(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setLearnerMode = useCallback(async (enabled: boolean) => {
    const r = await api.setLearnerMode(enabled);
    setLearnerModeState(!!r.learner_mode);
    return r;
  }, []);

  return { learnerMode, loading, setLearnerMode, refresh };
}
