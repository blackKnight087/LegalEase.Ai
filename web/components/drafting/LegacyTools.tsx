"use client";

import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import MarkdownBox from "@/components/ui/MarkdownBox";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import { useSpeechToText } from "@/hooks/useSpeechToText";
import SpeechMicButton from "@/components/ui/SpeechMicButton";
import SpeechPanel from "@/components/speech/SpeechPanel";
import * as api from "@/lib/api";

const SAMPLE = `LEASE AGREEMENT

Section 4 — Maintenance
The Tenant shall bear all maintenance costs.

Section 7 — Termination
Either party may terminate with 30 days notice.`;

type Tab = "smart" | "templates" | "clauses" | "redline";

export default function DraftingLegacyTools() {
  const [tab, setTab] = useState<Tab>("smart");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const [draftTypes, setDraftTypes] = useState<Array<{ id: string; label: string }>>([]);
  const [draftType, setDraftType] = useState("");
  const [questions, setQuestions] = useState<Array<{ id: string; label: string; required?: boolean }>>(
    []
  );
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [smartOut, setSmartOut] = useState("");

  const [templates, setTemplates] = useState<api.DocTemplate[]>([]);
  const [tplId, setTplId] = useState("");
  const [varsJson, setVarsJson] = useState("{}");
  const [tplOut, setTplOut] = useState("");

  const [clauses, setClauses] = useState<
    Array<{ clause_id: string; clause_tag: string; clause_text_content: string }>
  >([]);
  const [clausePick, setClausePick] = useState("");

  const [doc, setDoc] = useState(SAMPLE);
  const [revised, setRevised] = useState("");
  const [instruction, setInstruction] = useState("Make section 4 more favorable to the lessor");
  const [diffHtml, setDiffHtml] = useState("");
  const [polishDictation, setPolishDictation] = useState(false);

  const appendInstruction = useCallback((text: string) => {
    setInstruction((prev) => {
      const sep = prev.trim() ? (prev.endsWith(" ") ? "" : " ") : "";
      return `${prev}${sep}${text}`;
    });
  }, []);

  const instructionSpeech = useSpeechToText({
    language: "English",
    polishOnStop: polishDictation,
    getBaseText: () => instruction,
    onLiveUpdate: setInstruction,
    onTranscript: appendInstruction,
  });

  const loadBase = useCallback(async () => {
    try {
      const [types, tpl, cl] = await Promise.all([
        api.listSmartDraftTypes(),
        api.listDocTemplates(),
        api.listClauses(),
      ]);
      setDraftTypes(types.types || []);
      if (types.types?.length && !draftType) {
        setDraftType(types.types[0].id);
      }
      setTemplates(tpl.templates || []);
      if (tpl.templates?.length && !tplId) setTplId(tpl.templates[0].template_id);
      setClauses(cl.clauses || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load drafting data");
    }
  }, [draftType, tplId]);

  useEffect(() => {
    loadBase();
  }, [loadBase]);

  useEffect(() => {
    if (!draftType || tab !== "smart") return;
    api.getSmartDraftQuestions(draftType).then((q) => {
      setQuestions(q.questions || []);
      const init: Record<string, string> = {};
      (q.questions || []).forEach((item) => {
        init[item.id] = "";
      });
      setAnswers(init);
    });
  }, [draftType, tab]);

  const generateSmart = async (polish: boolean) => {
    setBusy(true);
    setErr("");
    try {
      const out = await api.generateSmartDraft(draftType, answers, polish);
      setSmartOut(out.rendered || "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Generate failed");
    } finally {
      setBusy(false);
    }
  };

  const generateTpl = async () => {
    setBusy(true);
    setErr("");
    try {
      const vars = JSON.parse(varsJson) as Record<string, string>;
      const out = await api.generateFromTemplate(tplId, vars);
      setTplOut(out.rendered);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Invalid JSON or generate failed");
    } finally {
      setBusy(false);
    }
  };

  const applyRedline = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.draftingRedline(doc, instruction);
      setRevised(String(r.revised || ""));
      setDiffHtml(String(r.diff_html || ""));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Redline failed");
    } finally {
      setBusy(false);
    }
  };

  const insertClause = () => {
    const c = clauses.find((x) => x.clause_id === clausePick);
    if (!c) return;
    const block = `\n\n## ${c.clause_tag}\n${c.clause_text_content}\n`;
    if (tab === "smart") setSmartOut((p) => p + block);
    else if (tab === "templates") setTplOut((p) => p + block);
    else setDoc((p) => p + block);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Drafting Studio"
        subtitle="Smart drafts, templates, clause library, and redline — separate from Knowledge Base Q&A"
      />
      <div className="flex-1 flex flex-col min-h-0 p-3 sm:p-4 gap-3 min-w-0">
        <div className="flex gap-2 overflow-x-auto touch-scroll-x flex-nowrap pb-1 sm:flex-wrap sm:overflow-visible">
          {(
            [
              ["smart", "Smart draft"],
              ["templates", "Templates"],
              ["clauses", "Clause library"],
              ["redline", "Redline"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`shrink-0 px-4 py-2.5 sm:py-2 rounded-lg text-sm font-medium min-h-[44px] sm:min-h-0 flex items-center ${
                tab === id ? "bg-navy text-white" : "border bg-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {err && (
          <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-2">
            {err}
          </p>
        )}

        {tab === "smart" && (
          <div className="flex-1 overflow-y-auto le-scroll space-y-4">
            <div className="flex flex-wrap gap-3 items-center">
              <select
                className="border rounded-lg px-3 py-2 text-sm"
                value={draftType}
                onChange={(e) => setDraftType(e.target.value)}
              >
                {draftTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={busy || !draftType}
                onClick={() => generateSmart(false)}
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Generate draft
              </button>
              <button
                type="button"
                disabled={busy || !draftType}
                onClick={() => generateSmart(true)}
                className="px-4 py-2 border rounded-lg text-sm"
              >
                Generate + Ollama polish
              </button>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              {questions.map((q) => (
                <label key={q.id} className="text-sm">
                  {q.label}
                  {q.required ? " *" : ""}
                  <input
                    className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                    value={answers[q.id] || ""}
                    onChange={(e) =>
                      setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
            {smartOut && <MarkdownBox content={smartOut} />}
          </div>
        )}

        {tab === "templates" && (
          <div className="flex-1 overflow-y-auto le-scroll space-y-4">
            <div className="flex flex-wrap gap-2">
              <select
                className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[200px]"
                value={tplId}
                onChange={(e) => setTplId(e.target.value)}
              >
                {templates.map((t) => (
                  <option key={t.template_id} value={t.template_id}>
                    {t.template_name} ({t.practice_area})
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={busy || !tplId}
                onClick={generateTpl}
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Generate from template
              </button>
            </div>
            <textarea
              className="w-full border rounded-lg px-3 py-2 font-mono text-xs h-24"
              value={varsJson}
              onChange={(e) => setVarsJson(e.target.value)}
              placeholder='{"party_a": "..."}'
            />
            {tplOut && <MarkdownBox content={tplOut} />}
          </div>
        )}

        {tab === "clauses" && (
          <div className="flex-1 overflow-y-auto le-scroll space-y-4">
            <p className="text-xs text-slate-600">
              Drag-drop style: select a clause and insert into your active draft or redline document.
            </p>
            <div className="flex gap-2">
              <select
                className="flex-1 border rounded-lg px-3 py-2 text-sm"
                value={clausePick}
                onChange={(e) => setClausePick(e.target.value)}
              >
                <option value="">Select clause…</option>
                {clauses.map((c) => (
                  <option key={c.clause_id} value={c.clause_id}>
                    {c.clause_tag}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!clausePick}
                onClick={insertClause}
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm"
              >
                Insert into draft
              </button>
            </div>
            <ul className="grid md:grid-cols-2 gap-3">
              {clauses.map((c) => (
                <li
                  key={c.clause_id}
                  className="p-3 border rounded-lg text-xs bg-slate-50 cursor-pointer hover:border-blue-300"
                  onClick={() => setClausePick(c.clause_id)}
                >
                  <b className="text-navy">{c.clause_tag}</b>
                  <p className="mt-2 text-slate-700 line-clamp-4">{c.clause_text_content}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "redline" && (
          <div className="flex-1 flex flex-col min-h-0 gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={polishDictation}
                onChange={(e) => setPolishDictation(e.target.checked)}
              />
              Legal polish after voice dictation
            </label>
            <div className="flex flex-wrap gap-2 items-center">
              <input
                className="flex-1 min-w-[200px] border rounded-lg px-3 py-2 text-sm"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={instructionSpeech.isBusy}
              />
              <SpeechMicButton
                isListening={instructionSpeech.isListening}
                isBusy={instructionSpeech.isBusy}
                isStopping={instructionSpeech.isStopping}
                onClick={instructionSpeech.toggle}
                title={
                  polishDictation
                    ? "Dictate redline instruction (legal polish)"
                    : "Dictate redline instruction"
                }
              />
              <button
                type="button"
                disabled={busy}
                onClick={applyRedline}
                className="px-5 py-2 bg-navy text-white rounded-lg text-sm"
              >
                {busy ? "Applying…" : "Apply redline"}
              </button>
            </div>
            {(instructionSpeech.status !== "idle" ||
              instructionSpeech.isListening ||
              instructionSpeech.isBusy ||
              instructionSpeech.error) && (
              <SpeechPanel
                status={instructionSpeech.status}
                micLabel={instructionSpeech.micDeviceLabel}
                audioLevel={instructionSpeech.audioLevel}
                engine={instructionSpeech.engine}
                error={instructionSpeech.error}
                signalHealth={instructionSpeech.signalHealth}
                signalMessage={instructionSpeech.signalMessage}
                bluetoothWarning={instructionSpeech.bluetoothWarning}
                refreshingDevices={instructionSpeech.refreshingDevices}
                devices={instructionSpeech.devices}
                selectedDeviceId={instructionSpeech.selectedDeviceId}
                onSelectDevice={instructionSpeech.selectDevice}
                onRefreshDevices={instructionSpeech.refreshDevices}
                onToggle={instructionSpeech.toggle}
                showDebug={instructionSpeech.showDebug}
                debug={instructionSpeech.debugInfo}
              />
            )}
            <div className="flex-1 grid lg:grid-cols-2 gap-3 min-h-0">
              <VoiceTextarea
                className="font-mono text-xs border rounded-xl p-3 le-scroll min-h-[12rem]"
                rows={16}
                value={doc}
                onChange={setDoc}
                polishOnStop={polishDictation}
              />
              <textarea
                className="border rounded-xl p-3 font-mono text-xs resize-none le-scroll bg-slate-50"
                value={revised || doc}
                readOnly={!!revised}
              />
            </div>
            {diffHtml && (
              <div
                className="border rounded-xl p-3 max-h-40 overflow-y-auto le-scroll bg-white text-xs"
                dangerouslySetInnerHTML={{ __html: diffHtml }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
