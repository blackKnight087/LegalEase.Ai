"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import MarkdownBox from "@/components/ui/MarkdownBox";
import VoiceTextarea from "@/components/ui/VoiceTextarea";

export default function MatterHearingsPanel({ matterId }: { matterId: string }) {
  const [hearings, setHearings] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");
  const [prepPack, setPrepPack] = useState("");
  const [causeListText, setCauseListText] = useState("");
  const [voiceNote, setVoiceNote] = useState("");

  const [hearingDate, setHearingDate] = useState("");
  const [courtName, setCourtName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [judgeName, setJudgeName] = useState("");
  const [notes, setNotes] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.listMatterHearings(matterId);
      setHearings(r.hearings || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load hearings");
      setHearings([]);
    }
  }, [matterId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const pollIntel = async () => {
      try {
        const s = await api.getMatterIntelStatus(matterId);
        const stage = String(s.stage || "idle");
        if (stage === "ready" || stage === "failed") {
          await load();
        }
      } catch {
        /* ignore */
      }
    };
    void pollIntel();
    const t = setInterval(() => void pollIntel(), 5000);
    return () => clearInterval(t);
  }, [matterId, load]);

  const extract = async () => {
    setBusy(true);
    setErr("");
    setSuccess("");
    try {
      const r = await api.extractMatterHearings(matterId);
      setHearings(r.hearings || []);
      setSuccess(
        `Extracted ${r.inserted ?? 0} hearing(s). Total: ${r.count ?? hearings.length}.`
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Hearing extraction failed");
    } finally {
      setBusy(false);
    }
  };

  const schedule = async () => {
    if (!hearingDate.trim()) {
      setErr("Hearing date is required");
      return;
    }
    setBusy(true);
    setErr("");
    setSuccess("");
    try {
      const r = await api.addMatterHearing(matterId, {
        hearing_date: hearingDate,
        court_name: courtName,
        purpose,
        judge_name: judgeName,
        notes,
      });
      setSuccess(r.message || "Hearing scheduled successfully");
      setHearingDate("");
      setCourtName("");
      setPurpose("");
      setJudgeName("");
      setNotes("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to schedule hearing");
    } finally {
      setBusy(false);
    }
  };

  const loadPrepPack = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.fetchHearingPrepPack(matterId);
      setPrepPack(String(r.markdown || ""));
      setSuccess("Hearing prep pack generated");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Prep pack failed");
    } finally {
      setBusy(false);
    }
  };

  const importCauseList = async () => {
    if (causeListText.length < 20) {
      setErr("Paste cause list text (at least 20 characters)");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await api.importCauseList(matterId, causeListText);
      setSuccess(`Imported ${r.inserted ?? 0} hearing row(s)`);
      setCauseListText("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const saveVoiceNote = async () => {
    if (voiceNote.length < 10) {
      setErr("Dictate or type a court note (min 10 characters)");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await api.hearingFromVoice(matterId, voiceNote);
      if (!r.ok) {
        setErr(String(r.error || "Could not parse hearing date from note"));
      } else {
        setSuccess("Hearing saved from voice note");
        setVoiceNote("");
        await load();
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Voice note failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void extract()}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Working…" : "Extract from documents"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void loadPrepPack()}
          className="px-3 py-2 bg-violet-700 text-white rounded-lg text-sm disabled:opacity-50"
        >
          Hearing prep pack
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          Refresh
        </button>
      </div>

      {success && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 m-0">
          {success}
        </p>
      )}
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 m-0">
          {err}
        </p>
      )}

      {prepPack && (
        <section className="rounded-xl border bg-white p-4">
          <h3 className="text-sm font-semibold text-navy m-0 mb-2">Prep pack</h3>
          <MarkdownBox content={prepPack} />
        </section>
      )}

      <section className="rounded-xl border bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-navy m-0">Voice → hearing note</h3>
        <p className="text-xs text-slate-500 m-0">
          After court, dictate the order, next date, and judge — we parse dates into a hearing record.
        </p>
        <VoiceTextarea
          value={voiceNote}
          onChange={setVoiceNote}
          rows={4}
          matterId={matterId}
          placeholder="e.g. Matter adjourned to 15 June 2026. Hon'ble Justice Mukherjee. Next hearing for arguments."
        />
        <button
          type="button"
          disabled={busy || voiceNote.length < 10}
          onClick={() => void saveVoiceNote()}
          className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          Save from voice note
        </button>
      </section>

      <section className="rounded-xl border bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-navy m-0">Import cause list</h3>
        <textarea
          className="w-full border rounded-lg px-2 py-2 text-sm min-h-[100px]"
          placeholder="Paste cause list text from court website…"
          value={causeListText}
          onChange={(e) => setCauseListText(e.target.value)}
        />
        <button
          type="button"
          disabled={busy || causeListText.length < 20}
          onClick={() => void importCauseList()}
          className="px-4 py-2 border rounded-lg text-sm disabled:opacity-50"
        >
          Import hearings
        </button>
      </section>

      <section className="rounded-xl border bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-navy m-0">Schedule hearing</h3>
        <div className="grid sm:grid-cols-2 gap-2">
          <label className="text-xs text-slate-600 block">
            Date *
            <input
              type="date"
              className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm"
              value={hearingDate}
              onChange={(e) => setHearingDate(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600 block">
            Court name
            <input
              className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm"
              placeholder="Kolkata High Court"
              value={courtName}
              onChange={(e) => setCourtName(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600 block sm:col-span-2">
            Purpose
            <input
              className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm"
              placeholder="Initial hearing"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600 block">
            Judge
            <input
              className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm"
              placeholder="Justice A.K. Mukherjee"
              value={judgeName}
              onChange={(e) => setJudgeName(e.target.value)}
            />
          </label>
          <label className="text-xs text-slate-600 block sm:col-span-2">
            Notes
            <textarea
              className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm min-h-[60px]"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          disabled={busy || !hearingDate}
          onClick={() => void schedule()}
          className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          Schedule hearing
        </button>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-navy m-0">
          Hearings ({hearings.length})
        </h3>
        {hearings.length === 0 && !busy && (
          <p className="text-sm text-slate-500 m-0">
            No hearings yet. Schedule manually, import a cause list, or extract from documents.
          </p>
        )}
        {hearings.map((h) => (
          <article
            key={String(h.hearing_id)}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-2"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <p className="text-lg font-bold text-navy m-0">{String(h.hearing_date)}</p>
                <p className="text-sm text-slate-600 m-0">{String(h.court_name || "Court TBD")}</p>
              </div>
              <span className="text-[0.65rem] uppercase font-semibold text-slate-500 px-2 py-1 bg-slate-100 rounded">
                {String(h.source || h.status || "scheduled")}
              </span>
            </div>
            {h.purpose ? (
              <p className="text-sm m-0">
                <span className="font-semibold">Purpose:</span> {String(h.purpose)}
              </p>
            ) : null}
            {h.judge_name || h.judge ? (
              <p className="text-sm m-0">
                <span className="font-semibold">Judge:</span>{" "}
                {String(h.judge_name || h.judge)}
              </p>
            ) : null}
            {h.summary ? (
              <p className="text-sm m-0">
                <span className="font-semibold">Summary:</span> {String(h.summary)}
              </p>
            ) : null}
            {h.next_hearing_date ? (
              <p className="text-sm m-0 text-amber-800">
                <span className="font-semibold">Next hearing:</span>{" "}
                {String(h.next_hearing_date)}
              </p>
            ) : null}
            {h.notes ? (
              <p className="text-sm text-slate-600 m-0">{String(h.notes)}</p>
            ) : null}
          </article>
        ))}
      </section>
    </div>
  );
}
