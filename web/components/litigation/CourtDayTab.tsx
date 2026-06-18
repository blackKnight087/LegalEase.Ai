"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import MarkdownBox from "@/components/ui/MarkdownBox";
import CauseListImportResults, {
  buildImportSummaryFromRows,
  type CauseListImportSummary,
} from "@/components/litigation/CauseListImportResults";
import * as api from "@/lib/api";

type ParsedRow = api.CourtDayRow;

export default function CourtDayTab() {
  const [causeText, setCauseText] = useState("");
  const [rows, setRows] = useState<ParsedRow[]>([]);
  const [matters, setMatters] = useState<Array<{ matter_id: string; matter_name: string }>>([]);
  const [digest, setDigest] = useState<api.CourtDayToday | null>(null);
  const [busy, setBusy] = useState(false);
  const [prepLoadingId, setPrepLoadingId] = useState("");
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [prepMd, setPrepMd] = useState("");
  const [prepMatter, setPrepMatter] = useState("");
  const [useAiPrep, setUseAiPrep] = useState(true);
  const [parserHint, setParserHint] = useState("");
  const [importSummary, setImportSummary] = useState<CauseListImportSummary | null>(null);

  const loadToday = useCallback(async () => {
    try {
      const d = await api.fetchCourtDayToday(14);
      setDigest(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load today's board");
    }
  }, []);

  useEffect(() => {
    void loadToday();
  }, [loadToday]);

  useEffect(() => {
    void api.listMatters().then((r) => {
      const list = (r.matters || []).map((m: { matter_id?: string; matter_name?: string }) => ({
        matter_id: String(m.matter_id || ""),
        matter_name: String(m.matter_name || ""),
      }));
      setMatters(list.filter((m) => m.matter_id));
    });
  }, []);

  const parseCauseList = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.parseCourtDayCauseList(causeText);
      setRows(r.rows || []);
      setMatters(r.matters || []);
      setImportSummary(buildImportSummaryFromRows(r.rows || [], undefined, r.parser));
      setParserHint(r.parser === "llm" ? "Parsed with AI (Ollama) — review matches." : "Parsed with rules engine.");
      if (!(r.matters?.length ?? 0)) {
        setMsg(
          "No matters found. Create a matter with case number and party names for better matching."
        );
      } else {
        setMsg(`Parsed ${r.parsed_count ?? 0} listing(s). Review matches before import.`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Parse failed");
    } finally {
      setBusy(false);
    }
  };

  const importSelected = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.importCourtDayRows(rows);
      setMsg(`Imported ${r.inserted ?? 0} hearing(s).`);
      setImportSummary(buildImportSummaryFromRows(rows, r, parserHint.includes("AI") ? "llm" : "rules"));
      setRows([]);
      await loadToday();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const loadPrep = async (matterId: string, matterName: string) => {
    setPrepLoadingId(matterId);
    setErr("");
    setPrepMd("");
    try {
      const r = await api.fetchCourtDayPrepPack(matterId, useAiPrep);
      if (!r.markdown?.trim()) {
        setErr(r.error || "Prep pack is empty for this matter");
        return;
      }
      setPrepMd(r.markdown);
      setPrepMatter(matterName);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Prep pack failed");
    } finally {
      setPrepLoadingId("");
    }
  };

  const confBadge = (c: string) => {
    if (c === "high") return "bg-emerald-100 text-emerald-800";
    if (c === "medium") return "bg-amber-100 text-amber-800";
    if (c === "low") return "bg-slate-100 text-slate-600";
    return "bg-red-50 text-red-700";
  };

  const renderDigestList = (items: api.HearingDigestItem[], empty: string) => {
    if (!items.length) return <p className="text-xs text-slate-500 m-0">{empty}</p>;
    return (
      <ul className="space-y-2 m-0 p-0 list-none">
        {items.slice(0, 8).map((h, i) => (
          <li
            key={`${h.matter_id}-${h.hearing_date}-${i}`}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2"
          >
            <div className="flex flex-wrap justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-navy m-0">{h.hearing_date}</p>
                <p className="text-xs text-slate-600 m-0 truncate">{h.matter_name}</p>
              </div>
              <div className="flex gap-2 shrink-0 items-center">
                <Link
                  href={`/matters/${h.matter_id}/hearings`}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Matter
                </Link>
                <button
                  type="button"
                  className="text-xs text-navy font-medium hover:underline disabled:opacity-50"
                  disabled={Boolean(prepLoadingId)}
                  onClick={() => void loadPrep(h.matter_id, h.matter_name)}
                >
                  {prepLoadingId === h.matter_id ? "Generating…" : "Prep pack"}
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="space-y-8">
      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {err}
        </p>
      )}
      {msg && (
        <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          {msg}
        </p>
      )}

      {!matters.length && (
        <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 m-0">
          No matters yet.{" "}
          <Link href="/matters/new" className="text-blue-600 font-medium hover:underline">
            Create a matter
          </Link>{" "}
          with case number and party names before importing cause lists.
        </p>
      )}

      <section className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-navy m-0">Import cause list</h2>
          <button
            type="button"
            className="le-interactive text-xs text-blue-700 font-medium hover:underline"
            onClick={() => void api.downloadHearingsCalendar(60)}
          >
            Export hearings (.ics)
          </button>
        </div>
        <p className="text-xs text-slate-500 m-0">
          Paste text or upload PDF. Heuristic + AI (Ollama) parsing. Match lines to matters before import.
        </p>
        <label className="block text-xs text-slate-600">
          Upload PDF / .txt cause list
          <input
            type="file"
            accept=".pdf,.txt,text/plain"
            className="mt-1 block w-full text-sm"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              setBusy(true);
              setErr("");
              void api
                .parseCourtDayFile(f)
                .then((r) => {
                  setRows(r.rows || []);
                  setMatters(r.matters || []);
                  setImportSummary(buildImportSummaryFromRows(r.rows || [], undefined, r.parser));
                  setParserHint(r.parser === "llm" ? "File parsed with AI." : "File parsed with rules.");
                  setMsg(`Parsed ${r.parsed_count ?? 0} listing(s) from file.`);
                })
                .catch((ex) => setErr(ex instanceof Error ? ex.message : "File parse failed"))
                .finally(() => setBusy(false));
            }}
          />
        </label>
        <textarea
          value={causeText}
          onChange={(e) => setCauseText(e.target.value)}
          rows={8}
          className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
          placeholder="Paste cause list text here…"
        />
        <button
          type="button"
          disabled={busy || causeText.length < 20}
          className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          onClick={() => void parseCauseList()}
        >
          {busy ? "Parsing…" : "Parse & match matters"}
        </button>
        {parserHint && <p className="text-xs text-slate-500 m-0">{parserHint}</p>}
        <CauseListImportResults summary={importSummary} />

        {rows.length > 0 && (
          <div className="space-y-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b">
                    <th className="py-2 pr-2 w-8" />
                    <th className="py-2 pr-2">Import</th>
                    <th className="py-2 pr-2">Date</th>
                    <th className="py-2 pr-2">Matter</th>
                    <th className="py-2 pr-2">Match</th>
                    <th className="py-2">Snippet</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => {
                    const showAlts =
                      (row.confidence === "medium" ||
                        row.confidence === "low" ||
                        row.confidence === "none") &&
                      (row.alternatives?.length ?? 0) > 0;
                    const isExpanded = expandedRow === idx;
                    return (
                      <Fragment key={row.row_index ?? idx}>
                        <tr className="border-b border-slate-100">
                          <td className="py-2 pr-2">
                            {showAlts ? (
                              <button
                                type="button"
                                className="text-xs text-blue-600"
                                aria-expanded={isExpanded}
                                onClick={() => setExpandedRow(isExpanded ? null : idx)}
                              >
                                {isExpanded ? "−" : "+"}
                              </button>
                            ) : null}
                          </td>
                          <td className="py-2 pr-2">
                            <input
                              type="checkbox"
                              checked={Boolean(row.selected)}
                              onChange={(e) => {
                                const next = [...rows];
                                next[idx] = { ...row, selected: e.target.checked };
                                setRows(next);
                              }}
                            />
                          </td>
                          <td className="py-2 pr-2 text-xs whitespace-nowrap">
                            {row.hearing_date}
                          </td>
                          <td className="py-2 pr-2">
                            <select
                              className="text-xs border rounded px-1 py-1 max-w-[180px]"
                              value={row.matter_id || row.suggested_matter_id || ""}
                              onChange={(e) => {
                                const next = [...rows];
                                const mid = e.target.value;
                                const m = matters.find((x) => x.matter_id === mid);
                                next[idx] = {
                                  ...row,
                                  matter_id: mid,
                                  suggested_matter_id: mid,
                                  suggested_matter_name: m?.matter_name || "",
                                };
                                setRows(next);
                              }}
                            >
                              <option value="">— Select matter —</option>
                              {matters.map((m) => (
                                <option key={m.matter_id} value={m.matter_id}>
                                  {m.matter_name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="py-2 pr-2">
                            <span
                              className={`text-[0.65rem] px-2 py-0.5 rounded-full ${confBadge(
                                row.confidence || "none"
                              )}`}
                              title={
                                row.suggested_matter_name
                                  ? `Suggested: ${row.suggested_matter_name}`
                                  : undefined
                              }
                            >
                              {row.confidence || "none"}
                            </span>
                          </td>
                          <td className="py-2 text-xs text-slate-600 max-w-xs truncate">
                            {row.purpose?.slice(0, 80)}
                          </td>
                        </tr>
                        {showAlts && isExpanded && (
                          <tr key={`${idx}-alts`} className="bg-slate-50">
                            <td colSpan={6} className="py-2 px-3 text-xs text-slate-600">
                              <span className="font-semibold text-slate-700">Other matches: </span>
                              {row.alternatives?.map((a, i) => (
                                <span key={a.matter_id ?? i}>
                                  {i > 0 ? "; " : ""}
                                  {a.matter_name} (score {a.score?.toFixed(2) ?? "—"})
                                </span>
                              ))}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <button
              type="button"
              disabled={busy}
              className="px-4 py-2 border border-navy text-navy rounded-lg text-sm font-medium disabled:opacity-50"
              onClick={() => void importSelected()}
            >
              Import selected hearings
            </button>
          </div>
        )}
      </section>

      <section className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-navy m-0 mb-4">Today&apos;s board</h2>
        {digest?.digest && (
          <div className="grid sm:grid-cols-3 gap-4">
            <div>
              <h3 className="text-[0.65rem] uppercase font-bold text-amber-800 mb-2">
                Today ({digest.digest.today?.length ?? 0})
              </h3>
              {renderDigestList(digest.digest.today || [], "No hearings today")}
            </div>
            <div>
              <h3 className="text-[0.65rem] uppercase font-bold text-blue-800 mb-2">
                This week ({digest.digest.this_week?.length ?? 0})
              </h3>
              {renderDigestList(digest.digest.this_week || [], "None this week")}
            </div>
            <div>
              <h3 className="text-[0.65rem] uppercase font-bold text-slate-600 mb-2">
                Upcoming ({digest.digest.upcoming?.length ?? 0})
              </h3>
              {renderDigestList(digest.digest.upcoming || [], "None upcoming")}
            </div>
          </div>
        )}
      </section>

      {prepLoadingId && !prepMd && (
        <p className="text-sm text-slate-600 m-0">Generating prep pack…</p>
      )}

      <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
        <input
          type="checkbox"
          checked={useAiPrep}
          onChange={(e) => setUseAiPrep(e.target.checked)}
        />
        Include AI hearing brief (Ollama) in prep pack
      </label>

      {prepMd && (
        <section className="le-card rounded-2xl border border-blue-200 bg-blue-50/30 p-5">
          <h2 className="text-sm font-semibold text-navy m-0 mb-2">Prep pack — {prepMatter}</h2>
          <MarkdownBox content={prepMd} />
        </section>
      )}
    </div>
  );
}
