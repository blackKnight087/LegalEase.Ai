"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";

export default function EngineStatusBar({
  matterId = "",
  compact = false,
}: {
  matterId?: string;
  compact?: boolean;
}) {
  const [status, setStatus] = useState<api.EngineStatusPayload | null>(null);
  const [progress, setProgress] = useState<api.LearningProgressPayload | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      if (document.visibilityState === "hidden") return;
      api
        .fetchEngineStatus(matterId || undefined)
        .then((s) => {
          if (alive) setStatus(s);
        })
        .catch(() => {
          if (alive) setStatus(null);
        });
      api
        .fetchLearningProgress()
        .then((p) => {
          if (alive) setProgress(p);
        })
        .catch(() => {
          if (alive) setProgress(null);
        });
    };
    load();
    const t = setInterval(load, 60000);
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      clearInterval(t);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [matterId]);

  if (!status && !progress) return null;

  const chips: { key: string; chip: { ok?: boolean; label?: string }; tone: string }[] = status
    ? [
        {
          key: "kb",
          chip: status.kb ?? {},
          tone: status.kb?.ok
            ? "bg-emerald-50 text-emerald-800 border-emerald-200"
            : "bg-amber-50 text-amber-800 border-amber-200",
        },
        {
          key: "web",
          chip: status.gemini ?? {},
          tone: status.gemini?.ok
            ? "bg-blue-50 text-blue-800 border-blue-200"
            : "bg-slate-100 text-slate-600 border-slate-200",
        },
        {
          key: "llm",
          chip: status.llm ?? {},
          tone: status.llm?.ok
            ? "bg-violet-50 text-violet-800 border-violet-200"
            : "bg-slate-100 text-slate-600 border-slate-200",
        },
        {
          key: "learning",
          chip: status.learning ?? {},
          tone: "bg-amber-50 text-amber-900 border-amber-200",
        },
        ...(status.embeddings
          ? [
              {
                key: "embed",
                chip: status.embeddings,
                tone: status.embeddings.ok
                  ? "bg-teal-50 text-teal-800 border-teal-200"
                  : "bg-amber-50 text-amber-800 border-amber-200",
              },
            ]
          : []),
      ]
    : [];

  const usage = status?.usage;
  const thumbs = progress?.thumbs_up ?? 0;
  const minThumbs = progress?.min_thumbs_for_export ?? 20;
  const pct = progress?.thumbs_progress_pct ?? 0;

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
        {chips.map(({ key, chip, tone }) => (
          <span
            key={key}
            className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 font-medium uppercase whitespace-nowrap ${tone}`}
            title={`${key}: ${chip?.label || (chip?.ok ? "ready" : "off")}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${chip?.ok ? "bg-emerald-500" : "bg-slate-400"}`}
            />
            {key}
          </span>
        ))}
        {progress ? (
          <span
            className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-amber-900"
            title={progress.next_milestone || ""}
          >
            L {thumbs}/{minThumbs}
          </span>
        ) : null}
        {usage ? (
          <span className="text-slate-500" title="Web Intel usage today">
            W {usage.gemini_calls_today}/{usage.gemini_limit}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-[0.65rem] overflow-x-auto touch-scroll-x flex-nowrap pb-0.5 -mx-0.5 px-0.5">
        {chips.map(({ key, chip, tone }) => (
          <span
            key={key}
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 sm:py-0.5 font-semibold uppercase tracking-wide whitespace-nowrap ${tone}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${chip?.ok ? "bg-emerald-500" : "bg-slate-400"}`}
            />
            {key === "embed" ? "embed" : key}: {chip?.label || (chip?.ok ? "ready" : "off")}
          </span>
        ))}
        {progress ? (
          <span
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-semibold text-amber-900"
            title={progress.next_milestone || ""}
          >
            Learning {thumbs}/{minThumbs}
            <span className="inline-block h-1.5 w-12 rounded-full bg-amber-200 overflow-hidden">
              <span
                className="block h-full bg-amber-600 transition-all"
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </span>
          </span>
        ) : null}
        {usage ? (
          <span className="shrink-0 text-slate-500 font-medium whitespace-nowrap">
            Web Intel {usage.gemini_calls_today}/{usage.gemini_limit} today
          </span>
        ) : null}
        {status?.strict_citations ? (
          <span className="shrink-0 text-red-700 font-semibold whitespace-nowrap">
            Strict citations
          </span>
        ) : null}
      </div>
      {progress?.next_milestone ? (
        <p className="text-[0.62rem] text-slate-500 m-0 hidden sm:block">{progress.next_milestone}</p>
      ) : null}
    </div>
  );
}
