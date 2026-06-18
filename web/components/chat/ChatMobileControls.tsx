"use client";

import { useState } from "react";
import EngineStatusBar from "@/components/chat/EngineStatusBar";
import KbScopeHealth from "@/components/chat/KbScopeHealth";
import ModePills from "@/components/chat/ModePills";
import type { Matter } from "@/lib/api";

const LANGS = ["English", "Hindi", "Tamil", "Marathi", "Bengali", "Gujarati"] as const;

type Props = {
  mode: string;
  onModeChange: (m: string) => void;
  membership: string;
  lang: string;
  onLangChange: (l: string) => void;
  matterId: string;
  onMatterChange: (id: string) => void;
  matters: Matter[];
};

export default function ChatMobileControls({
  mode,
  onModeChange,
  membership,
  lang,
  onLangChange,
  matterId,
  onMatterChange,
  matters,
}: Props) {
  const [statusOpen, setStatusOpen] = useState(false);
  const showMatter = mode === "knowledge_base" || mode === "deep_case" || mode === "hybrid";

  return (
    <div className="shrink-0 border-b border-slate-200/80 bg-white/95 px-2 py-1.5 space-y-1.5">
      <ModePills
        mode={mode}
        onChange={onModeChange}
        membership={membership}
        compact
      />
      <div className="flex items-center gap-1.5 min-w-0">
        {showMatter ? (
          <select
            className="flex-1 min-w-0 h-8 text-[11px] font-medium border border-slate-200 rounded-lg px-2 bg-slate-50 text-slate-800 truncate"
            value={matterId}
            onChange={(e) => onMatterChange(e.target.value)}
            aria-label="Case file scope"
          >
            <option value="">All unlinked docs</option>
            {matters.map((m) => (
              <option key={m.matter_id} value={m.matter_id}>
                {m.matter_name}
              </option>
            ))}
          </select>
        ) : (
          <span className="flex-1 text-[11px] text-slate-500 truncate px-1">
            Live web sources
          </span>
        )}
        <select
          className="shrink-0 h-8 max-w-[5.25rem] text-[11px] font-medium border border-slate-200 rounded-lg px-1.5 bg-white text-slate-800"
          value={lang}
          onChange={(e) => onLangChange(e.target.value)}
          aria-label="Language"
        >
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {l === "English" ? "EN" : l.slice(0, 3)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setStatusOpen((v) => !v)}
          className={`shrink-0 h-8 w-8 flex items-center justify-center rounded-lg border text-xs font-bold transition-colors ${
            statusOpen
              ? "border-blue-300 bg-blue-50 text-blue-700"
              : "border-slate-200 bg-white text-slate-500"
          }`}
          aria-expanded={statusOpen}
          aria-label={statusOpen ? "Hide engine status" : "Show engine status"}
        >
          {statusOpen ? "▲" : "ⓘ"}
        </button>
      </div>
      <KbScopeHealth matterId={matterId} mode={mode} warnOnly />
      {statusOpen ? (
        <div className="pt-1 border-t border-slate-100">
          <EngineStatusBar matterId={matterId} compact />
        </div>
      ) : null}
    </div>
  );
}
