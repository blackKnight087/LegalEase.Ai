"use client";

import Link from "next/link";
import { getStageEmptyContent } from "./crmKanbanStageContent";

type Props = {
  stage: string;
  stageLabel: string;
  hint?: string;
  compact?: boolean;
};

export default function CrmKanbanEmptyColumn({ stage, stageLabel, hint, compact }: Props) {
  const content = getStageEmptyContent(stage, hint);

  return (
    <div
      className={`rounded-xl border border-dashed border-slate-200 bg-white/80 text-center transition-all duration-300 ${
        compact ? "p-3" : "p-4"
      }`}
    >
      <span className="text-2xl" role="img" aria-hidden>
        {content.icon}
      </span>
      <p className="text-[0.65rem] font-bold uppercase text-slate-400 mt-2">{stageLabel}</p>
      <p className="text-xs font-semibold text-slate-700 mt-1">{content.headline}</p>
      <p className="text-[0.65rem] text-slate-500 mt-1 leading-relaxed">{content.description}</p>
      {!compact && (
        <>
          <p className="text-[0.65rem] text-slate-600 mt-2 italic">{content.nextAction}</p>
          {content.ctaHref ? (
            <Link
              href={content.ctaHref}
              className="inline-block mt-3 text-[0.65rem] font-bold px-3 py-1.5 rounded-lg bg-navy text-white hover:bg-slate-800 transition-colors"
            >
              {content.ctaLabel}
            </Link>
          ) : (
            <span className="inline-block mt-3 text-[0.65rem] font-semibold text-blue-700">
              {content.ctaLabel}
            </span>
          )}
        </>
      )}
    </div>
  );
}
