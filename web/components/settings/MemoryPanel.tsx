"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import type {
  ImprovementAutomationStatus,
  LearningEngineStatus,
  LearningModeStats,
  MemoryFact,
  MemoryProfile,
  NeuralTuningStatus,
  OllamaCoachStatus,
} from "@/lib/api";

const PERSONAS = [
  { id: "warm", label: "Warm & supportive" },
  { id: "professional", label: "Professional" },
  { id: "concise", label: "Concise" },
  { id: "detailed", label: "Detailed" },
];

const MODE_LABELS: Record<string, string> = {
  knowledge_base: "Knowledge Base",
  web_search: "Web Intel",
  deep_case: "Hybrid (KB + Web Intel)",
};

function fmtMode(mode: string) {
  return MODE_LABELS[mode] || mode.replace(/_/g, " ");
}

function statusPill(status: string) {
  const s = (status || "unknown").toLowerCase();
  if (s === "completed") return "bg-emerald-100 text-emerald-800";
  if (s === "running") return "bg-blue-100 text-blue-800";
  if (s === "failed") return "bg-red-100 text-red-800";
  return "bg-slate-100 text-slate-700";
}

function MetricBar({ pct, tone = "emerald" }: { pct: number; tone?: "emerald" | "amber" | "blue" }) {
  const color =
    tone === "amber" ? "bg-amber-500" : tone === "blue" ? "bg-blue-500" : "bg-emerald-500";
  return (
    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
  );
}

function ModePerformanceCard({ m }: { m: LearningModeStats }) {
  const hit = m.hit_rate_pct ?? Math.round((1 - (m.not_found_rate || 0)) * 100);
  const acc = m.accuracy_pct;
  return (
    <div className="border border-slate-200 rounded-xl p-3 bg-slate-50/50">
      <p className="text-[0.65rem] font-bold uppercase text-slate-500">{fmtMode(m.mode)}</p>
      <p className="text-lg font-bold text-navy mt-0.5">{m.turns}</p>
      <p className="text-[0.65rem] text-slate-500">chat turns</p>
      <div className="mt-2 space-y-2">
        <div>
          <div className="flex justify-between text-[0.65rem] text-slate-600 mb-0.5">
            <span>Hit rate</span>
            <span>{hit}%</span>
          </div>
          <MetricBar pct={hit} />
        </div>
        {acc != null && (
          <div>
            <div className="flex justify-between text-[0.65rem] text-slate-600 mb-0.5">
              <span>Feedback accuracy</span>
              <span>{acc}%</span>
            </div>
            <MetricBar pct={acc} tone="blue" />
          </div>
        )}
        <p className="text-[0.6rem] text-slate-500">
          👍 {m.positive} · 👎 {m.negative}
          {m.avg_retrieval_score != null && m.avg_retrieval_score > 0
            ? ` · retrieval ${m.avg_retrieval_score}`
            : ""}
        </p>
      </div>
    </div>
  );
}

function NeuralTrainingSection({
  neural,
  busy,
  onCollect,
  onTrain,
  onAutoImprove,
}: {
  neural?: NeuralTuningStatus;
  busy: boolean;
  onCollect: () => void;
  onTrain: () => void;
  onAutoImprove: () => void;
}) {
  if (!neural) return null;
  const pairsPct = Math.min(
    100,
    Math.round((neural.unused_pairs / Math.max(neural.min_pairs_required, 1)) * 100)
  );
  const last = neural.last_run;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`text-[0.65rem] font-semibold px-2 py-0.5 rounded-full ${
            neural.enabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
          }`}
        >
          Neural training {neural.enabled ? "on" : "off"}
        </span>
        {neural.auto_train && (
          <span className="text-[0.65rem] font-semibold px-2 py-0.5 rounded-full bg-violet-100 text-violet-800">
            Auto-improve on{neural.rapid_mode ? " (rapid)" : ""}
          </span>
        )}
        {neural.active_model_loaded && (
          <span className="text-[0.65rem] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
            Custom model active
          </span>
        )}
      </div>

      <div>
        <div className="flex justify-between text-xs text-slate-600 mb-1">
          <span>Training pairs ready</span>
          <span>
            {neural.unused_pairs} / {neural.min_pairs_required} min
          </span>
        </div>
        <MetricBar pct={pairsPct} tone="amber" />
      </div>

      {last && (
        <div className="text-xs bg-white border border-slate-200 rounded-lg p-3 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-navy">Last training run</span>
            <span className={`text-[0.65rem] font-bold px-2 py-0.5 rounded-full ${statusPill(last.status)}`}>
              {last.status}
            </span>
          </div>
          <p className="text-slate-600">
            Pairs: {last.pair_count}
            {last.finished_at ? ` · ${new Date(last.finished_at).toLocaleString()}` : ""}
          </p>
          {last.error && <p className="text-red-600 text-[0.65rem]">{last.error}</p>}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onAutoImprove}
          className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs font-semibold disabled:opacity-50"
        >
          Improve automatically
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onCollect}
          className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs disabled:opacity-50"
        >
          Collect pairs
        </button>
        <button
          type="button"
          disabled={busy || neural.unused_pairs < neural.min_pairs_required}
          onClick={onTrain}
          className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs disabled:opacity-50"
          title={
            neural.unused_pairs < neural.min_pairs_required
              ? `Need ${neural.min_pairs_required} pairs`
              : "Train embedding model"
          }
        >
          Train now
        </button>
      </div>
    </div>
  );
}

function LearningProgressSection({
  progress,
  busy,
  onRunHoldout,
}: {
  progress?: api.LearningProgressPayload | null;
  busy: boolean;
  onRunHoldout: () => void;
}) {
  if (!progress) return null;

  const gate = progress.quality_gate as { passed?: boolean; reasons?: string[] } | undefined;
  const signals = progress.signals as { events_by_signal?: Record<string, number> } | undefined;
  const sched = progress.coach_schedule as {
    daily?: { due?: boolean; elapsed_days?: number };
    weekly?: { due?: boolean; elapsed_days?: number };
    monthly?: { due?: boolean; elapsed_days?: number };
  } | undefined;
  const pipe = progress.training_pipeline as {
    human_labels?: number;
    preference_pairs?: number;
    sft_ready?: boolean;
  } | undefined;

  return (
    <div className="border border-blue-200 rounded-xl p-4 bg-blue-50/30 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-navy">Learning progress</h4>
        <p className="text-xs text-slate-500 mt-0.5">{progress.next_milestone}</p>
      </div>

      <div className="space-y-1">
        <div className="flex justify-between text-xs text-slate-600">
          <span>Thumbs-up toward tuned model</span>
          <span className="font-semibold">
            {progress.thumbs_up}/{progress.min_thumbs_for_export}
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
          <div
            className="h-full bg-emerald-600 transition-all"
            style={{ width: `${Math.min(100, progress.thumbs_progress_pct || 0)}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="bg-white border rounded-lg p-2">
          <p className="text-[0.6rem] uppercase text-slate-400 font-bold">Labels</p>
          <p className="font-bold text-navy">{pipe?.human_labels ?? 0}</p>
        </div>
        <div className="bg-white border rounded-lg p-2">
          <p className="text-[0.6rem] uppercase text-slate-400 font-bold">DPO pairs</p>
          <p className="font-bold text-navy">{pipe?.preference_pairs ?? 0}</p>
        </div>
        <div className="bg-white border rounded-lg p-2">
          <p className="text-[0.6rem] uppercase text-slate-400 font-bold">Copy signals</p>
          <p className="font-bold text-navy">{signals?.events_by_signal?.copy ?? 0}</p>
        </div>
        <div className="bg-white border rounded-lg p-2">
          <p className="text-[0.6rem] uppercase text-slate-400 font-bold">Regenerates</p>
          <p className="font-bold text-navy">{signals?.events_by_signal?.regenerate ?? 0}</p>
        </div>
      </div>

      {gate && (
        <div
          className={`text-xs rounded-lg p-2 border ${
            gate.passed
              ? "bg-emerald-50 border-emerald-200 text-emerald-900"
              : "bg-amber-50 border-amber-200 text-amber-900"
          }`}
        >
          <p className="font-semibold">
            Export quality gate: {gate.passed ? "Passed" : "Not yet"}
          </p>
          {!gate.passed && gate.reasons?.length ? (
            <ul className="mt-1 list-disc pl-4 space-y-0.5">
              {gate.reasons.slice(0, 3).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      {sched && (
        <p className="text-[0.65rem] text-slate-500">
          Coach schedule — daily {sched.daily?.elapsed_days ?? 0}d · weekly{" "}
          {sched.weekly?.elapsed_days ?? 0}d · monthly {sched.monthly?.elapsed_days ?? 0}d
          {sched.daily?.due || sched.weekly?.due || sched.monthly?.due ? " · due soon" : ""}
        </p>
      )}

      <button
        type="button"
        disabled={busy}
        onClick={onRunHoldout}
        className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs disabled:opacity-50"
      >
        Run holdout retrieval eval
      </button>
    </div>
  );
}

function ImprovementAutomationSection({
  automation,
  busy,
  onRunNow,
}: {
  automation?: ImprovementAutomationStatus;
  busy: boolean;
  onRunNow: () => void;
}) {
  if (!automation) return null;

  const ready = automation.export_ready;
  const canExport = automation.can_export_modelfile ?? ready;
  const thumbs = automation.thumbs_up ?? 0;
  const minThumbs = automation.min_thumbs_for_export ?? 20;
  const gateReasons = automation.quality_gate?.reasons || [];

  return (
    <div className="border border-emerald-200 rounded-xl p-4 bg-emerald-50/40 space-y-2">
      <div>
        <h4 className="text-sm font-semibold text-navy">Auto-improvement pipeline</h4>
        <p className="text-xs text-slate-500 mt-0.5">
          Runs automatically on thumbs-up/down — neural training, KB re-index, Modelfile export,
          and <code className="text-[0.65rem]">ollama create legalease-tuned</code>. No manual
          clicks required.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[0.65rem]">
        <span
          className={`font-semibold px-2 py-0.5 rounded-full ${
            automation.enabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
          }`}
        >
          {automation.enabled ? "Automation on" : "Automation off"}
        </span>
        {automation.auto_reindex && (
          <span className="bg-blue-50 text-blue-800 px-2 py-0.5 rounded-full">Auto re-index</span>
        )}
        {automation.auto_ollama_create && (
          <span className="bg-violet-50 text-violet-800 px-2 py-0.5 rounded-full">
            Auto ollama create
          </span>
        )}
        {canExport ? (
          <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
            Export ready (quality gate passed)
          </span>
        ) : ready ? (
          <span className="bg-amber-50 text-amber-800 px-2 py-0.5 rounded-full">
            {thumbs} thumbs-up — quality gate pending
          </span>
        ) : (
          <span className="bg-amber-50 text-amber-800 px-2 py-0.5 rounded-full">
            {thumbs}/{minThumbs} thumbs-up for Modelfile
          </span>
        )}
      </div>

      {!canExport && gateReasons.length > 0 && (
        <p className="text-xs text-amber-800">{gateReasons[0]}</p>
      )}

      {automation.active_tuned_model && (
        <p className="text-xs text-slate-600">
          Active tuned model: <b>{automation.active_tuned_model}</b>
          {automation.auto_use_tuned_model ? " (used when LLM_BACKEND=ollama)" : ""}
        </p>
      )}

      <button
        type="button"
        disabled={busy || !automation.enabled}
        onClick={onRunNow}
        className="px-3 py-1.5 bg-emerald-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
      >
        Run improvement pipeline now
      </button>
    </div>
  );
}

function coachInsightSummary(insights: Record<string, unknown> | string | undefined): string {
  if (!insights) return "";
  if (typeof insights === "string") {
    try {
      const parsed = JSON.parse(insights) as Record<string, unknown>;
      return typeof parsed.summary === "string" ? parsed.summary : "";
    } catch {
      return insights.startsWith("{") ? "" : insights;
    }
  }
  return typeof insights.summary === "string" ? insights.summary : "";
}

function formatCoachCycleMessage(r: Record<string, unknown>): string {
  if (!r.ok) {
    return String(r.error || "Coaching cycle failed");
  }
  const parts: string[] = ["Full tuning cycle complete."];
  const training = r.training as { ok?: boolean; error?: string } | undefined;
  if (training?.ok) parts.push("Neural train OK");
  else if (training?.error) parts.push(`Neural: ${training.error}`);
  const exportResult = (r.ollama_export || r.export) as {
    ok?: boolean;
    ollama_create?: { ok?: boolean; model_name?: string; error?: string };
    error?: string;
  } | undefined;
  const create = exportResult?.ollama_create;
  if (create?.ok && create.model_name) {
    parts.push(`Ollama model: ${create.model_name}`);
  } else if (create?.error) {
    parts.push(`Ollama create: ${create.error}`);
  } else if (exportResult?.error) {
    parts.push(String(exportResult.error));
  }
  if (typeof r.message === "string") parts.push(r.message);
  return parts.join(" · ");
}

function OllamaCoachSection({
  coach,
  busy,
  directives,
  onDirectivesChange,
  onSaveDirectives,
  onToggle,
  onToggleSchedule,
  onRunCycle,
  onAnalyze,
  onApply,
  onExportModelfile,
}: {
  coach?: OllamaCoachStatus;
  busy: boolean;
  directives: string;
  onDirectivesChange: (v: string) => void;
  onSaveDirectives: () => void;
  onToggle: (enabled: boolean) => void;
  onToggleSchedule: (enabled: boolean) => void;
  onRunCycle: () => void;
  onAnalyze: () => void;
  onApply: () => void;
  onExportModelfile: () => void;
}) {
  if (!coach) return null;

  const insightsRaw = coach.last_insights;
  const insights =
    typeof insightsRaw === "string"
      ? (() => {
          try {
            return JSON.parse(insightsRaw) as Record<string, unknown>;
          } catch {
            return {} as Record<string, unknown>;
          }
        })()
      : ((insightsRaw || {}) as Record<string, unknown>);
  const summary = coachInsightSummary(insights);
  const healing = Array.isArray(insights.healing_actions) ? insights.healing_actions : [];
  const schedule = coach.schedule;
  const ollamaExport = coach.ollama_export;

  return (
    <div className="border border-violet-200 rounded-xl p-4 bg-violet-50/40 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-navy">AI tuning coach (Settings only)</h4>
        <p className="text-xs text-slate-500 mt-0.5">
          Uses your Gemini API key only in Settings — analyzes feedback to tune local
          Ollama style and retrieval. Never writes legal answers into KB. Open Law uses
          Gemini separately for web search only.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`text-[0.65rem] font-semibold px-2 py-0.5 rounded-full ${
            coach.available ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
          }`}
        >
          {coach.available ? "Coach available" : "Coach unavailable"}
        </span>
        {!coach.global_enabled && (
          <span className="text-[0.65rem] text-amber-800 bg-amber-50 px-2 py-0.5 rounded-full">
            Set GEMINI_OLLAMA_TUNING=1 in .env
          </span>
        )}
        {!coach.gemini_configured && (
          <span className="text-[0.65rem] text-amber-800 bg-amber-50 px-2 py-0.5 rounded-full">
            Add GEMINI_API_KEY
          </span>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={coach.user_enabled}
          disabled={busy || !coach.available}
          onChange={(e) => onToggle(e.target.checked)}
        />
        Enable automatic tuning coach
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={schedule?.auto_schedule_enabled !== false}
          disabled={busy || !coach.available || !coach.user_enabled}
          onChange={(e) => onToggleSchedule(e.target.checked)}
        />
        Daily auto-coaching when {schedule?.min_new_feedback ?? 1}+ new feedback items
      </label>
      {schedule && (
        <p className="text-[0.65rem] text-slate-500">
          {schedule.due
            ? "Auto-coaching is due — will run on next scheduler check."
            : `${schedule.new_feedback_since_last ?? 0} new feedback since last auto-coach`}
          {schedule.last_auto_coach_at
            ? ` · Last auto-coach: ${new Date(schedule.last_auto_coach_at).toLocaleString()}`
            : ""}
        </p>
      )}

      <div>
        <label className="text-xs font-semibold text-slate-600">
          Tell Ollama how to improve
        </label>
        <p className="text-[0.65rem] text-slate-500 mb-1">
          Describe how answers should be structured, tone, length, or mistakes to avoid. Gemini
          analyzes this and updates Ollama memory + neural training.
        </p>
        <textarea
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[100px] resize-y"
          placeholder="e.g. Always cite IPC sections with punishment. Keep answers under 200 words unless I ask for detail. Focus on criminal law…"
          value={directives}
          onChange={(e) => onDirectivesChange(e.target.value)}
          maxLength={4000}
          disabled={busy}
        />
        <button
          type="button"
          disabled={busy || !directives.trim()}
          onClick={onSaveDirectives}
          className="mt-2 px-3 py-1.5 bg-violet-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
        >
          Save & analyze with coach
        </button>
      </div>

      {(coach.memory_count ?? 0) > 0 && (
        <div className="text-xs space-y-1">
          <p className="font-semibold text-navy">
            Ollama remembers {coach.memory_count} tuning lesson
            {(coach.memory_count ?? 0) === 1 ? "" : "s"}
          </p>
          <ul className="text-slate-600 space-y-0.5 max-h-28 overflow-y-auto">
            {(coach.recent_memories || []).slice(0, 5).map((m) => (
              <li key={m.id} className="truncate" title={m.content}>
                <span className="text-slate-400">[{m.source}]</span> {m.content}
              </li>
            ))}
          </ul>
        </div>
      )}

      {coach.last_run_at && (
        <p className="text-[0.65rem] text-slate-500">
          Last analysis: {new Date(coach.last_run_at).toLocaleString()}
        </p>
      )}

      {summary && (
        <div className="text-xs bg-white border border-slate-200 rounded-lg p-3">
          <p className="font-semibold text-navy mb-1">Latest insights</p>
          <p className="text-slate-700">{summary}</p>
          {healing.length > 0 && (
            <ul className="mt-2 list-disc list-inside text-slate-600 space-y-0.5">
              {healing.slice(0, 4).map((h, i) => (
                <li key={i}>{String(h)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || !coach.available || !coach.user_enabled}
          onClick={onRunCycle}
          className="px-3 py-1.5 bg-violet-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
        >
          Run full tuning cycle
        </button>
        <button
          type="button"
          disabled={busy || !coach.available || !coach.user_enabled}
          onClick={onAnalyze}
          className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs disabled:opacity-50"
        >
          Analyze feedback only
        </button>
        <button
          type="button"
          disabled={busy || !coach.available || !summary}
          onClick={onApply}
          className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs disabled:opacity-50"
        >
          Apply last insights
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onExportModelfile}
          className="px-3 py-1.5 border border-emerald-300 text-emerald-800 rounded-lg text-xs disabled:opacity-50"
        >
          Export Ollama Modelfile
        </button>
      </div>

      {ollamaExport?.has_export && (
        <div className="text-xs bg-emerald-50 border border-emerald-200 rounded-lg p-3 space-y-1">
          <p className="font-semibold text-navy">Latest Modelfile export</p>
          <p className="text-slate-600 break-all">{ollamaExport.export_dir}</p>
          <p className="text-[0.65rem] text-slate-500">
            Run in that folder:{" "}
            <code className="bg-white px-1 rounded">ollama create legalease-tuned -f Modelfile</code>
            {" "}then set <code className="bg-white px-1 rounded">OLLAMA_MODEL=legalease-tuned</code>
          </p>
        </div>
      )}
    </div>
  );
}

export default function MemoryPanel() {
  const [prof, setProf] = useState<MemoryProfile | null>(null);
  const [engine, setEngine] = useState<LearningEngineStatus | null>(null);
  const [learningProgress, setLearningProgress] = useState<api.LearningProgressPayload | null>(null);
  const [directives, setDirectives] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editKey, setEditKey] = useState("");
  const [editVal, setEditVal] = useState("");

  const loadLearning = useCallback(() => {
    api.fetchLearningEngineStatus().then((st) => {
      setEngine(st);
      const d = st?.ollama_coach?.directives_text;
      if (d) setDirectives(d);
    }).catch(() => setEngine(null));
    api.fetchLearningProgress().then(setLearningProgress).catch(() => setLearningProgress(null));
    api.fetchOllamaCoachDirectives().then((r) => {
      if (r.directives_text) setDirectives(r.directives_text);
    }).catch(() => {});
  }, []);

  const load = useCallback(() => {
    api.fetchMemoryProfile().then(setProf).catch((e) => setMsg(e.message));
    loadLearning();
  }, [loadLearning]);

  useEffect(() => {
    load();
  }, [load]);

  const saveProfile = async (patch: Partial<MemoryProfile>) => {
    setBusy(true);
    setMsg("");
    try {
      const p = await api.updateMemoryProfile(patch);
      setProf(p);
      setMsg("Saved.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const removeFact = async (id: string) => {
    setBusy(true);
    try {
      await api.deleteMemoryFact(id);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const addFact = async () => {
    if (!newKey.trim() || !newVal.trim()) return;
    setBusy(true);
    try {
      await api.addMemoryFact(newKey.trim(), newVal.trim());
      setNewKey("");
      setNewVal("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Add failed");
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    if (!editId) return;
    setBusy(true);
    try {
      await api.updateMemoryFact(editId, editKey, editVal);
      setEditId(null);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const reindex = async () => {
    setBusy(true);
    try {
      const r = await api.reindexChatMemory();
      setMsg(`Indexed ${r.threads_indexed} threads (${r.chunks_added} chunks).`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Reindex failed");
    } finally {
      setBusy(false);
    }
  };

  const runAutoImprove = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.learningAutoImprove();
      setEngine(r.status);
      if (r.training_started) {
        setMsg(
          `Auto-improvement ran: ${r.pairs_added} pairs collected, embedding training started.`
        );
      } else if (r.pairs_added > 0) {
        setMsg(
          `Collected ${r.pairs_added} training pairs. Training will run when enough pairs accumulate (${r.unused_pairs_after} ready).`
        );
      } else {
        setMsg("Checked for improvements — no new training pairs yet. Use thumbs-up on good answers.");
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Auto-improve failed");
    } finally {
      setBusy(false);
    }
  };

  const runCollect = async () => {
    setBusy(true);
    try {
      const r = await api.neuralCollectPairs();
      setMsg(`Collected ${r.pairs_added} training pairs from feedback.`);
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Collect failed");
    } finally {
      setBusy(false);
    }
  };

  const runTrain = async () => {
    setBusy(true);
    try {
      const r = await api.neuralTrainEmbeddings();
      if (r.ok) {
        setMsg(r.message || "Embedding model training completed.");
        try {
          const re = await api.reindexChatMemory();
          setMsg(
            `${r.message || "Training completed."} Re-indexed ${re.threads_indexed} threads (${re.chunks_added} chunks).`
          );
        } catch {
          setMsg(
            (r.message || "Training completed.") +
              " Re-index chat memory from Settings if retrieval feels stale."
          );
        }
      } else {
        setMsg(r.error || "Training could not start.");
      }
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Training failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleCoach = async (enabled: boolean) => {
    setBusy(true);
    try {
      await api.toggleOllamaCoach(enabled);
      loadLearning();
      setMsg(enabled ? "AI tuning coach enabled." : "AI tuning coach disabled.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not update coach");
    } finally {
      setBusy(false);
    }
  };

  const runCoachCycle = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.runOllamaCoachCycle();
      setMsg(formatCoachCycleMessage(r as Record<string, unknown>));
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Coaching cycle failed");
    } finally {
      setBusy(false);
    }
  };

  const runHoldoutEval = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.runHoldoutEval();
      setMsg(typeof r.summary === "string" ? r.summary : "Holdout eval complete.");
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Holdout eval failed");
    } finally {
      setBusy(false);
    }
  };

  const runAutomationNow = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.runImprovementAutomation();
      if (r.queued && r.job_id) {
        setMsg("Pipeline queued — running in background worker…");
        const deadline = Date.now() + 600_000;
        while (Date.now() < deadline) {
          await new Promise((res) => setTimeout(res, 3000));
          const job = await api.fetchMlJob(String(r.job_id));
          if (job.status === "COMPLETED") {
            setMsg("Improvement pipeline complete.");
            break;
          }
          if (job.status === "FAILED") {
            setMsg(job.error_message || "Pipeline failed in worker");
            break;
          }
          setMsg(`Pipeline running… ${job.progress ?? 0}%`);
        }
      } else if (!r.ok) {
        setMsg(r.error || "Automation pipeline failed");
      } else {
        const ollama = r.ollama as { ollama_create?: { model_name?: string } } | undefined;
        setMsg(
          ollama?.ollama_create?.model_name
            ? `Pipeline complete · model ${ollama.ollama_create.model_name}`
            : "Improvement pipeline complete."
        );
      }
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Automation failed");
    } finally {
      setBusy(false);
    }
  };

  const runCoachAnalyze = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.analyzeOllamaCoachFeedback();
      if (!r.ok) {
        setMsg(r.error || "Analysis failed");
      } else {
        const summary =
          typeof r.insights?.summary === "string" ? r.insights.summary : "Analysis complete.";
        setMsg(summary);
      }
      loadLearning();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  const runCoachApply = async () => {
    setBusy(true);
    try {
      const r = await api.applyOllamaCoachInsights();
      if (!r.ok) {
        setMsg(r.error || "Nothing to apply");
      } else {
        const applied = r.applied as Record<string, number> | undefined;
        setMsg(
          `Applied insights: ${applied?.facts_added ?? 0} facts, ${applied?.training_pairs_added ?? 0} pairs, ${applied?.query_healings_added ?? 0} query healings.`
        );
        load();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(false);
    }
  };

  const saveDirectives = async () => {
    if (!directives.trim()) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await api.saveOllamaCoachDirectives(directives.trim(), true);
      if (!r.ok && r.error) {
        setMsg(r.error);
      } else {
        setMsg(r.message || "Instructions saved and applied to Ollama tuning.");
        loadLearning();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save instructions");
    } finally {
      setBusy(false);
    }
  };

  const toggleSchedule = async (enabled: boolean) => {
    setBusy(true);
    try {
      await api.toggleOllamaCoachSchedule(enabled);
      loadLearning();
      setMsg(enabled ? "Daily auto-coaching enabled." : "Daily auto-coaching disabled.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not update schedule");
    } finally {
      setBusy(false);
    }
  };

  const exportModelfile = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.exportOllamaModelfile();
      if (!r.ok) {
        setMsg(r.error || "Export failed — add more feedback examples first.");
      } else {
        setMsg(
          `Modelfile exported to ${r.export_dir || "Data/ollama_exports"}. Run: ${r.create_command || "ollama create legalease-tuned -f Modelfile"}`
        );
        loadLearning();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  if (!prof) {
    return <p className="text-sm text-slate-500">Loading memory…</p>;
  }

  const perf = engine?.performance || engine?.adaptive_learning?.summary;
  const modes = engine?.adaptive_learning?.modes || [];
  const neural = engine?.neural_finetuning;
  const coach = engine?.ollama_coach;
  const automation = engine?.improvement_automation;

  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
      <div>
        <h2 className="font-semibold text-navy">AI memory</h2>
        <p className="text-xs text-slate-500 mt-1">
          Control what the assistant remembers. Auto-captured facts can be wrong — delete
          transient items like one-off case mentions.
        </p>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={prof.memory_enabled !== false}
          onChange={(e) => saveProfile({ memory_enabled: e.target.checked })}
        />
        Memory enabled
      </label>

      <div>
        <label className="text-xs font-semibold text-slate-600">Persona</label>
        <select
          className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
          value={prof.persona || "warm"}
          onChange={(e) => saveProfile({ persona: e.target.value })}
          disabled={busy}
        >
          {PERSONAS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs font-semibold text-slate-600">Practice area</label>
        <input
          className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
          value={prof.practice_area || ""}
          onChange={(e) => setProf({ ...prof, practice_area: e.target.value })}
          onBlur={() => saveProfile({ practice_area: prof.practice_area })}
          placeholder="e.g. Criminal litigation, Maritime"
        />
      </div>

      <div>
        <h3 className="text-sm font-semibold text-navy mb-2">Remembered facts</h3>
        <div className="flex flex-wrap gap-2 mb-3">
          {(prof.facts || []).map((f: MemoryFact) =>
            editId === f.id ? (
              <div key={f.id} className="flex gap-1 w-full">
                <input
                  className="flex-1 border rounded px-2 py-1 text-xs"
                  value={editKey}
                  onChange={(e) => setEditKey(e.target.value)}
                />
                <input
                  className="flex-1 border rounded px-2 py-1 text-xs"
                  value={editVal}
                  onChange={(e) => setEditVal(e.target.value)}
                />
                <button type="button" className="text-xs text-emerald-700" onClick={saveEdit}>
                  Save
                </button>
              </div>
            ) : (
              <span
                key={f.id}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border ${
                  f.source === "auto"
                    ? "bg-amber-50 border-amber-200 text-amber-900"
                    : "bg-blue-50 border-blue-200 text-blue-900"
                }`}
              >
                <b>{f.key}:</b> {f.value}
                <button
                  type="button"
                  className="ml-1 opacity-60 hover:opacity-100"
                  onClick={() => {
                    setEditId(f.id);
                    setEditKey(f.key);
                    setEditVal(f.value);
                  }}
                  title="Edit"
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="opacity-60 hover:opacity-100"
                  onClick={() => removeFact(f.id)}
                  title="Delete"
                >
                  ×
                </button>
              </span>
            )
          )}
          {!prof.facts?.length && (
            <span className="text-xs text-slate-400">No facts yet — add below or chat.</span>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <input
            className="flex-1 min-w-[100px] border rounded-lg px-2 py-1.5 text-xs"
            placeholder="Key (e.g. answer_style)"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <input
            className="flex-[2] min-w-[140px] border rounded-lg px-2 py-1.5 text-xs"
            placeholder="Value"
            value={newVal}
            onChange={(e) => setNewVal(e.target.value)}
          />
          <button
            type="button"
            disabled={busy}
            onClick={addFact}
            className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs"
          >
            Add
          </button>
        </div>
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={reindex}
        className="text-xs text-slate-600 underline hover:text-navy"
      >
        Reindex past chats for “what did we conclude…” search
      </button>

      <div className="border-t border-slate-200 pt-4 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-navy">Learning & performance</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Neural training and response accuracy from your chat feedback. Improves automatically
              when you thumbs-up good answers.
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={loadLearning}
            className="text-xs text-slate-500 underline hover:text-navy shrink-0"
          >
            Refresh
          </button>
        </div>

        {perf && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="border rounded-xl p-3 bg-white">
              <p className="text-[0.65rem] uppercase text-slate-500 font-bold">Accuracy</p>
              <p className="text-xl font-bold text-navy">
                {perf.accuracy_pct != null ? `${perf.accuracy_pct}%` : "—"}
              </p>
              <p className="text-[0.6rem] text-slate-500">from feedback</p>
            </div>
            <div className="border rounded-xl p-3 bg-white">
              <p className="text-[0.65rem] uppercase text-slate-500 font-bold">Hit rate</p>
              <p className="text-xl font-bold text-navy">
                {perf.avg_hit_rate_pct != null ? `${perf.avg_hit_rate_pct}%` : "—"}
              </p>
              <p className="text-[0.6rem] text-slate-500">answers found</p>
            </div>
            <div className="border rounded-xl p-3 bg-white">
              <p className="text-[0.65rem] uppercase text-slate-500 font-bold">Chat turns</p>
              <p className="text-xl font-bold text-navy">{perf.total_turns ?? 0}</p>
              <p className="text-[0.6rem] text-slate-500">logged</p>
            </div>
            <div className="border rounded-xl p-3 bg-white">
              <p className="text-[0.65rem] uppercase text-slate-500 font-bold">Answer memory</p>
              <p className="text-xl font-bold text-navy">{engine?.answer_memory_count ?? 0}</p>
              <p className="text-[0.6rem] text-slate-500">proven Q→A</p>
            </div>
          </div>
        )}

        {modes.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-slate-600 mb-2">By chat mode</h4>
            <div className="grid sm:grid-cols-3 gap-3">
              {modes.map((m) => (
                <ModePerformanceCard key={m.mode} m={m} />
              ))}
            </div>
          </div>
        )}

        {!modes.length && engine && (
          <p className="text-xs text-slate-400">
            No performance data yet — chat and use thumbs-up/down to train the model.
          </p>
        )}

        <NeuralTrainingSection
          neural={neural}
          busy={busy}
          onCollect={runCollect}
          onTrain={runTrain}
          onAutoImprove={runAutoImprove}
        />

        <LearningProgressSection
          progress={learningProgress}
          busy={busy}
          onRunHoldout={runHoldoutEval}
        />

        <ImprovementAutomationSection
          automation={automation}
          busy={busy}
          onRunNow={runAutomationNow}
        />

        <OllamaCoachSection
          coach={coach}
          busy={busy}
          directives={directives}
          onDirectivesChange={setDirectives}
          onSaveDirectives={saveDirectives}
          onToggle={toggleCoach}
          onToggleSchedule={toggleSchedule}
          onRunCycle={runCoachCycle}
          onAnalyze={runCoachAnalyze}
          onApply={runCoachApply}
          onExportModelfile={exportModelfile}
        />

        {(engine?.adaptive_learning?.learned_queries?.length ?? 0) > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-slate-600 mb-1">Learned query patterns</h4>
            <ul className="text-xs text-slate-600 space-y-0.5">
              {engine!.adaptive_learning!.learned_queries!.slice(0, 5).map((q, i) => (
                <li key={i}>
                  <span className="font-medium">{q.query}</span>
                  <span className="text-slate-400"> → {q.expansion.slice(0, 60)}…</span>
                  <span className="text-emerald-700 ml-1">×{q.success}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {msg && <p className="text-xs text-slate-600">{msg}</p>}
    </section>
  );
}
