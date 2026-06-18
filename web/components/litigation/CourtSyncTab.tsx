"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import CauseListImportResults, {
  buildImportSummaryFromRows,
  buildImportSummaryFromSync,
  type CauseListImportSummary,
} from "@/components/litigation/CauseListImportResults";

const DEMO_CAUSE_LIST = `15-03-2025
Before Hon'ble Justice Singh
WP 99/2024 Sharma v State listed for admission`;

type SyncMode = "paste" | "ecourtsindia";
type MainTab = "cause_list" | "case_lookup";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function CourtSyncTab() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<SyncMode>("paste");
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [settings, setSettings] = useState<Awaited<ReturnType<typeof api.fetchCourtSyncSettings>> | null>(null);
  const [statusErr, setStatusErr] = useState("");
  const [text, setText] = useState("");
  const [autoSchedule, setAutoSchedule] = useState(true);
  const [apiDate, setApiDate] = useState(todayIso());
  const [apiState, setApiState] = useState("DL");
  const [apiQuery, setApiQuery] = useState("");
  const [apiAdvocate, setApiAdvocate] = useState("");
  const [apiLitigant, setApiLitigant] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saveKeyBusy, setSaveKeyBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [summary, setSummary] = useState<CauseListImportSummary | null>(null);
  const [syncHistory, setSyncHistory] = useState<Array<Record<string, unknown>>>([]);
  const [mainTab, setMainTab] = useState<MainTab>("cause_list");
  const [cnrInput, setCnrInput] = useState("");
  const [casePreview, setCasePreview] = useState<api.EcourtsCasePreview | null>(null);
  const [caseSearchAdvocate, setCaseSearchAdvocate] = useState("");
  const [caseSearchLitigant, setCaseSearchLitigant] = useState("");
  const [caseSearchResults, setCaseSearchResults] = useState<api.EcourtsSearchHit[]>([]);
  const [matters, setMatters] = useState<Array<{ matter_id: string; matter_name: string }>>([]);
  const [syncMatterId, setSyncMatterId] = useState("");
  const [importHearings, setImportHearings] = useState(true);
  const [importOrders, setImportOrders] = useState(true);
  const [courtStates, setCourtStates] = useState<Array<{ code: string; name: string }>>([]);
  const [courtDistricts, setCourtDistricts] = useState<Array<{ code: string; name: string }>>([]);
  const [apiDistrictCode, setApiDistrictCode] = useState("");
  const [availableDates, setAvailableDates] = useState<string[]>([]);

  useEffect(() => {
    void Promise.all([api.fetchCourtSyncStatus(), api.fetchCourtSyncSettings(), api.listMatters(), api.fetchCourtSyncHistory(10)])
      .then(([st, set, m, hist]) => {
        setStatus(st);
        setSettings(set);
        setSyncHistory(hist.history || []);
        setMode(set.preferred_mode === "ecourtsindia" ? "ecourtsindia" : "paste");
        setMatters((m.matters || []).map((row) => ({ matter_id: row.matter_id, matter_name: row.matter_name })));
      })
      .catch((e) => setStatusErr(e instanceof Error ? e.message : "Could not load sync status"));
  }, []);

  useEffect(() => {
    if (mode !== "ecourtsindia" || !settings?.api_configured) return;
    void api.fetchEcourtsStates().then((res) => {
      const raw = (res as { data?: { states?: unknown[] } }).data?.states ?? (res as { states?: unknown[] }).states ?? [];
      const rows = Array.isArray(raw)
        ? raw.map((row) => {
            const r = row as Record<string, string>;
            return { code: r.code || r.state || r.stateCode || "", name: r.name || r.stateName || r.code || "" };
          }).filter((row) => row.code)
        : [];
      setCourtStates(rows);
    }).catch(() => {
      /* optional enhancement */
    });
  }, [mode, settings?.api_configured]);

  useEffect(() => {
    if (!apiState || mode !== "ecourtsindia" || !settings?.api_configured) {
      setCourtDistricts([]);
      return;
    }
    void api.fetchEcourtsDistricts(apiState).then((res) => {
      const raw = (res as { data?: { districts?: unknown[] } }).data?.districts ?? (res as { districts?: unknown[] }).districts ?? [];
      const rows = Array.isArray(raw)
        ? raw.map((row) => {
            const r = row as Record<string, string>;
            return { code: r.code || r.districtCode || "", name: r.name || r.districtName || r.code || "" };
          }).filter((row) => row.code)
        : [];
      setCourtDistricts(rows);
    }).catch(() => setCourtDistricts([]));
  }, [apiState, mode, settings?.api_configured]);

  const persistMode = async (next: SyncMode) => {
    setMode(next);
    try {
      await api.saveCourtSyncSettings({ preferred_mode: next });
    } catch {
      /* non-fatal */
    }
  };

  const saveApiKey = async () => {
    setSaveKeyBusy(true);
    setErr("");
    try {
      const set = await api.saveCourtSyncSettings({ api_key: apiKeyInput.trim() });
      setSettings(set);
      setApiKeyInput("");
      setMsg("API key saved for your account.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save API key");
    } finally {
      setSaveKeyBusy(false);
    }
  };

  const clearApiKey = async () => {
    setSaveKeyBusy(true);
    try {
      const set = await api.saveCourtSyncSettings({ clear_api_key: true });
      setSettings(set);
      setMsg("Your saved API key was removed.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not clear API key");
    } finally {
      setSaveKeyBusy(false);
    }
  };

  const applySyncResult = (r: Record<string, unknown>, usedApi: boolean) => {
    const s = buildImportSummaryFromSync(r);
    setSummary(s);
    void api.fetchCourtSyncHistory(10).then((h) => setSyncHistory(h.history || []));
    if (s.parsedCount === 0) {
      setErr(
        usedApi
          ? "API returned data but nothing could be parsed. Try paste mode with the full bulletin."
          : "No hearing rows found. Include a date (DD-MM-YYYY) and case lines."
      );
      return;
    }
    if (autoSchedule && s.inserted === 0) {
      setErr(
        s.matchedCount === 0
          ? "Parsed listings but no matters matched. Create matters with case numbers and party names first."
          : "Matched matters but hearings were not imported. Check dates in the cause list."
      );
      if (s.errors.length) setErr((prev) => `${prev} ${s.errors[0]}`);
      return;
    }
    const creditNote = usedApi && s.apiCalls ? " (1 API call used)" : "";
    setMsg(
      autoSchedule
        ? `Synced ${s.parsedCount} listing(s), imported ${s.inserted} hearing(s).${creditNote}`
        : `Parsed ${s.parsedCount} listing(s), ${s.matchedCount} matched.${creditNote}`
    );
  };

  const runPasteSync = async (causeText: string) => {
    if (causeText.trim().length < 20) {
      setErr("Paste at least 20 characters of cause list text.");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    setSummary(null);
    try {
      const r = await api.syncPracticeCourtCauseList({
        source: "paste",
        text: causeText,
        auto_schedule: autoSchedule,
      });
      applySyncResult(r, false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  };

  const runApiSync = async () => {
    if (!settings?.api_configured && !apiKeyInput.trim()) {
      setErr("Add your eCourtsIndia API key below, or set ECOURTSINDIA_API_KEY in server .env.");
      return;
    }
    if (!apiDate && !apiQuery && !apiAdvocate && !apiLitigant) {
      setErr("API mode needs at least a date, case query, advocate, or litigant filter.");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    setSummary(null);
    try {
      if (apiKeyInput.trim()) {
        await api.saveCourtSyncSettings({ api_key: apiKeyInput.trim() });
      }
      const r = await api.syncPracticeCourtCauseList({
        source: "ecourtsindia",
        auto_schedule: autoSchedule,
        api_date: apiDate,
        api_state: apiState,
        api_query: apiQuery,
        api_advocate: apiAdvocate,
        api_litigant: apiLitigant,
        api_limit: 50,
        api_district_code: apiDistrictCode,
      });
      applySyncResult(r, true);
      const refreshed = await api.fetchCourtSyncSettings();
      setSettings(refreshed);
      setApiKeyInput("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "API sync failed");
    } finally {
      setBusy(false);
    }
  };

  const ensureApiKey = () => {
    if (!settings?.api_configured && !apiKeyInput.trim()) {
      setErr("Add your eCourtsIndia API key below, or set ECOURTSINDIA_API_KEY in server .env.");
      return false;
    }
    return true;
  };

  const fetchCasePreview = async (cnr?: string) => {
    const value = (cnr ?? cnrInput).replace(/\s/g, "").toUpperCase();
    if (value.length < 8) {
      setErr("Enter a valid CNR (16 characters recommended).");
      return;
    }
    if (!ensureApiKey()) return;
    setBusy(true);
    setErr("");
    setMsg("");
    setCasePreview(null);
    try {
      if (apiKeyInput.trim()) {
        await api.saveCourtSyncSettings({ api_key: apiKeyInput.trim() });
        setSettings(await api.fetchCourtSyncSettings());
        setApiKeyInput("");
      }
      const preview = await api.fetchEcourtsCase(value);
      setCasePreview(preview);
      setCnrInput(value);
      setMsg(`Loaded case ${preview.cnr || value}.`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Case lookup failed");
    } finally {
      setBusy(false);
    }
  };

  const runCaseSearch = async () => {
    if (!caseSearchAdvocate.trim() && !caseSearchLitigant.trim()) {
      setErr("Enter an advocate or litigant name to search.");
      return;
    }
    if (!ensureApiKey()) return;
    setBusy(true);
    setErr("");
    setMsg("");
    setCaseSearchResults([]);
    try {
      const out = await api.searchEcourtsCases({
        advocates: caseSearchAdvocate.trim(),
        litigants: caseSearchLitigant.trim(),
        pageSize: 20,
      });
      setCaseSearchResults(out.results || []);
      if (!(out.results || []).length) {
        setErr("No cases found for those filters.");
      } else {
        setMsg(`Found ${out.total_hits ?? out.results?.length ?? 0} case(s).`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  const syncCaseToMatter = async (cnr?: string) => {
    const value = (cnr ?? cnrInput).replace(/\s/g, "").toUpperCase();
    if (!value) {
      setErr("CNR is required.");
      return;
    }
    if (!syncMatterId) {
      setErr("Select a matter to sync into.");
      return;
    }
    if (!ensureApiKey()) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.syncEcourtsCase(value, {
        matter_id: syncMatterId,
        import_hearings: importHearings,
        import_orders: importOrders,
      });
      setMsg(
        `Synced ${value}: ${out.hearings_imported ?? 0} hearing(s), ${out.orders_imported ?? 0} order(s) imported.`
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Case sync failed");
    } finally {
      setBusy(false);
    }
  };

  const loadAvailableDates = async () => {
    if (!apiState) return;
    try {
      const out = await api.fetchEcourtsAvailableDates({
        state: apiState,
        districtCode: apiDistrictCode || undefined,
      });
      setAvailableDates(out.dates || []);
    } catch {
      setAvailableDates([]);
    }
  };

  const onFile = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    setErr("");
    setMsg("");
    setSummary(null);
    try {
      const name = file.name.toLowerCase();
      if (name.endsWith(".txt") || file.type === "text/plain") {
        const parsedText = await file.text();
        setText(parsedText);
        await runPasteSync(parsedText);
        return;
      }
      const r = await api.parseCourtDayFile(file);
      const rows = r.rows || [];
      if (!rows.length) {
        setErr("No listings found in PDF. Paste the cause list text or use the Court Day tab.");
        return;
      }
      const matchedCount = rows.filter((row) => row.selected && row.suggested_matter_id).length;
      if (autoSchedule) {
        const imp = await api.importCourtDayRows(rows);
        setSummary(buildImportSummaryFromRows(rows, imp, r.parser));
        if ((imp.inserted ?? 0) === 0) {
          setErr(
            matchedCount === 0
              ? "PDF parsed but no matters matched. Create matters with case numbers first."
              : "Matched matters but could not import hearings."
          );
        } else {
          setMsg(`Imported ${imp.inserted ?? 0} hearing(s) from PDF (free paste mode).`);
        }
      } else {
        setSummary(buildImportSummaryFromRows(rows, undefined, r.parser));
        setMsg(`Parsed ${rows.length} listing(s) from PDF.`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "File upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6">
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.txt,text/plain,application/pdf"
        className="hidden"
        onChange={(e) => void onFile(e.target.files?.[0] ?? null)}
      />
      <section className="le-card le-card-hover rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
        <h2 className="text-sm font-semibold text-navy m-0">Hybrid court sync</h2>
        <p className="text-xs text-slate-500 m-0">
          Two paths — use both. <strong>Upload / paste</strong> is free and unlimited (best for daily cause lists and saving your ₹200 credits).
          <strong> eCourtsIndia API</strong> is for live fetch when you cannot copy text (~₹3 per cause-list sync, ~₹1.50 per CNR lookup).
        </p>
        <div className="text-xs rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 px-3 py-2 space-y-1">
          <p className="m-0 font-medium">Credit saver (recommended workflow)</p>
          <p className="m-0">Daily bulletins → upload PDF or paste text (0 credits). Single-case CNR check or targeted search → API only when needed.</p>
          <p className="m-0 text-emerald-800">₹200 free credits ≈ 65 cause-list syncs or ~130 CNR lookups if you use API sparingly.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void persistMode("paste")}
            className={`text-sm px-4 py-2 rounded-lg border ${
              mode === "paste" ? "bg-navy text-white border-navy" : "bg-white hover:bg-slate-50"
            }`}
          >
            Upload / paste (free)
          </button>
          <button
            type="button"
            onClick={() => void persistMode("ecourtsindia")}
            className={`text-sm px-4 py-2 rounded-lg border ${
              mode === "ecourtsindia" ? "bg-navy text-white border-navy" : "bg-white hover:bg-slate-50"
            }`}
          >
            eCourtsIndia API (uses credits)
          </button>
        </div>
        {statusErr && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 m-0">
            {statusErr}
          </p>
        )}
        {status && (
          <div className="text-xs text-slate-600 rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-1">
            <p className="m-0">
              <strong>API key:</strong>{" "}
              {settings?.api_configured
                ? `${settings.api_key_masked} (${settings.api_key_source})`
                : "Not configured — paste mode still works"}
            </p>
            <p className="m-0">{String(status.note || "")}</p>
          </div>
        )}
      </section>

      {mode === "ecourtsindia" && mainTab === "cause_list" && (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-navy m-0">eCourtsIndia API key</h3>
          <p className="text-xs text-slate-500 m-0">
            Sign up at{" "}
            <a href="https://ecourtsindia.com/api" target="_blank" rel="noreferrer" className="text-blue-700">
              ecourtsindia.com/api
            </a>{" "}
            for ₹200 free credits. Each sync uses ~1 call (~₹3 PAYG). Search-engine keys (Google/Bing) cannot replace this.
          </p>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="flex-1 min-w-[220px] text-xs block">
              API key (eci_live_…)
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={settings?.api_configured ? "Enter new key to replace" : "Paste your key"}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-mono"
              />
            </label>
            <button
              type="button"
              disabled={saveKeyBusy || !apiKeyInput.trim()}
              onClick={() => void saveApiKey()}
              className="px-3 py-2 text-sm border rounded-lg disabled:opacity-50"
            >
              Save key
            </button>
            {settings?.save_user_key && (
              <button
                type="button"
                disabled={saveKeyBusy}
                onClick={() => void clearApiKey()}
                className="px-3 py-2 text-sm border rounded-lg text-red-700"
              >
                Remove saved key
              </button>
            )}
          </div>
        </section>
      )}

      {mainTab === "case_lookup" && (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-navy m-0">eCourtsIndia API key</h3>
          <p className="text-xs text-slate-500 m-0">
            Case lookup requires an API key (~₹1.50 per CNR lookup on PAYG).
          </p>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="flex-1 min-w-[220px] text-xs block">
              API key (eci_live_…)
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={settings?.api_configured ? "Enter new key to replace" : "Paste your key"}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-mono"
              />
            </label>
            <button
              type="button"
              disabled={saveKeyBusy || !apiKeyInput.trim()}
              onClick={() => void saveApiKey()}
              className="px-3 py-2 text-sm border rounded-lg disabled:opacity-50"
            >
              Save key
            </button>
          </div>
        </section>
      )}

      <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setMainTab("cause_list")}
            className={`text-sm px-4 py-2 rounded-lg border ${
              mainTab === "cause_list" ? "bg-navy text-white border-navy" : "bg-white hover:bg-slate-50"
            }`}
          >
            Cause list sync
          </button>
          <button
            type="button"
            onClick={() => setMainTab("case_lookup")}
            className={`text-sm px-4 py-2 rounded-lg border ${
              mainTab === "case_lookup" ? "bg-navy text-white border-navy" : "bg-white hover:bg-slate-50"
            }`}
          >
            Case lookup (CNR)
          </button>
        </div>
      </section>

      {err && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</p>
      )}
      {msg && (
        <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          {msg}
        </p>
      )}

      {mainTab === "cause_list" && (mode === "paste" ? (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50"
              onClick={() => setText(DEMO_CAUSE_LIST)}
            >
              Load demo sample
            </button>
            <button
              type="button"
              className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
            >
              Upload PDF / .txt
            </button>
            <Link href="/matters" className="text-xs px-3 py-1.5 text-blue-700 hover:underline self-center">
              Create matters for matching →
            </Link>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
            placeholder="Paste full cause list bulletin here (include dates like 15-03-2025 and case numbers)…"
          />
          <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={autoSchedule}
              onChange={(e) => setAutoSchedule(e.target.checked)}
            />
            Auto-import matched hearings after sync
          </label>
          <button
            type="button"
            disabled={busy || text.length < 20}
            className="le-interactive px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
            onClick={() => void runPasteSync(text)}
          >
            {busy ? "Syncing…" : "Run court sync (free)"}
          </button>
        </section>
      ) : (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 m-0">
            Tip: Use API for targeted lookups (one case/advocate/date). Use paste for full daily bulletins to save credits.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="text-xs block">
              Hearing date
              <input
                type="date"
                value={apiDate}
                onChange={(e) => setApiDate(e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs block">
              State
              {courtStates.length ? (
                <select
                  value={apiState}
                  onChange={(e) => {
                    setApiState(e.target.value);
                    setApiDistrictCode("");
                  }}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm uppercase"
                >
                  {courtStates.map((st) => (
                    <option key={st.code} value={st.code}>
                      {st.name} ({st.code})
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={apiState}
                  onChange={(e) => setApiState(e.target.value.toUpperCase())}
                  placeholder="DL, JH, UP…"
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm uppercase"
                />
              )}
            </label>
            {courtDistricts.length > 0 && (
              <label className="text-xs block">
                District (optional)
                <select
                  value={apiDistrictCode}
                  onChange={(e) => setApiDistrictCode(e.target.value)}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">All districts</option>
                  {courtDistricts.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="sm:col-span-2 flex flex-wrap gap-2 items-center">
              <button
                type="button"
                disabled={busy || !apiState}
                onClick={() => void loadAvailableDates()}
                className="text-xs px-3 py-1.5 border rounded-lg hover:bg-slate-50 disabled:opacity-50"
              >
                Load available cause dates
              </button>
              {availableDates.length > 0 && (
                <select
                  value={apiDate}
                  onChange={(e) => setApiDate(e.target.value)}
                  className="text-xs border rounded-lg px-2 py-1.5"
                >
                  {availableDates.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <label className="text-xs block sm:col-span-2">
              Case number / query (optional)
              <input
                value={apiQuery}
                onChange={(e) => setApiQuery(e.target.value)}
                placeholder="WP 99/2024"
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs block">
              Advocate (optional)
              <input
                value={apiAdvocate}
                onChange={(e) => setApiAdvocate(e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs block">
              Litigant / party (optional)
              <input
                value={apiLitigant}
                onChange={(e) => setApiLitigant(e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={autoSchedule}
              onChange={(e) => setAutoSchedule(e.target.checked)}
            />
            Auto-import matched hearings after sync
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runApiSync()}
            className="le-interactive px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            {busy ? "Fetching from API…" : "Run court sync (uses 1 API call)"}
          </button>
        </section>
      ))}

      {mainTab === "cause_list" && mode === "ecourtsindia" && (
        <section className="le-card rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-emerald-900 m-0">Free fallback — upload cause list PDF</h3>
          <p className="text-xs text-emerald-800 m-0">
            Have the bulletin as PDF or text? Upload here instead — no API credits used.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="text-xs px-3 py-1.5 border border-emerald-300 rounded-lg bg-white hover:bg-emerald-50"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
            >
              Upload PDF / .txt
            </button>
            <button
              type="button"
              className="text-xs px-3 py-1.5 border border-emerald-300 rounded-lg bg-white hover:bg-emerald-50"
              onClick={() => void persistMode("paste")}
            >
              Switch to full paste mode →
            </button>
          </div>
        </section>
      )}

      {mainTab === "case_lookup" && (
        <section className="le-card rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5 shadow-sm space-y-3">
          <h3 className="text-sm font-semibold text-emerald-900 m-0">Free path — upload case / order PDF</h3>
          <p className="text-xs text-emerald-800 m-0">
            Downloaded a cause list or court order PDF from eCourts? Upload it here — parses and imports hearings without spending API credits.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="text-xs px-3 py-1.5 border border-emerald-300 rounded-lg bg-white hover:bg-emerald-50"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
            >
              Upload PDF / .txt
            </button>
            <button
              type="button"
              className="text-xs px-3 py-1.5 border border-emerald-300 rounded-lg bg-white hover:bg-emerald-50"
              onClick={() => {
                setMainTab("cause_list");
                void persistMode("paste");
              }}
            >
              Open full paste workspace →
            </button>
          </div>
        </section>
      )}

      {mainTab === "case_lookup" && (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-5">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-navy m-0">Lookup by CNR</h3>
            <div className="flex flex-wrap gap-2 items-end">
              <label className="flex-1 min-w-[220px] text-xs block">
                CNR number
                <input
                  value={cnrInput}
                  onChange={(e) => setCnrInput(e.target.value.toUpperCase())}
                  placeholder="DLHC010001232024"
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm font-mono uppercase"
                />
              </label>
              <button
                type="button"
                disabled={busy || cnrInput.replace(/\s/g, "").length < 8}
                onClick={() => void fetchCasePreview()}
                className="px-4 py-2 text-sm bg-navy text-white rounded-lg disabled:opacity-50"
              >
                {busy ? "Fetching…" : "Fetch preview"}
              </button>
            </div>
            {casePreview && (
              <div className="text-xs rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-1">
                <p className="m-0"><strong>CNR:</strong> {casePreview.cnr}</p>
                <p className="m-0"><strong>Parties:</strong> {casePreview.parties}</p>
                <p className="m-0"><strong>Status:</strong> {casePreview.status}</p>
                <p className="m-0"><strong>Court:</strong> {casePreview.court}</p>
                <p className="m-0"><strong>Next hearing:</strong> {casePreview.next_hearing_date || "—"}</p>
                <p className="m-0"><strong>Orders:</strong> {casePreview.order_count ?? 0}</p>
              </div>
            )}
          </div>

          <div className="space-y-3 border-t border-slate-100 pt-4">
            <h3 className="text-sm font-semibold text-navy m-0">Search cases</h3>
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="text-xs block">
                Advocate
                <input
                  value={caseSearchAdvocate}
                  onChange={(e) => setCaseSearchAdvocate(e.target.value)}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
              <label className="text-xs block">
                Litigant / party
                <input
                  value={caseSearchLitigant}
                  onChange={(e) => setCaseSearchLitigant(e.target.value)}
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                />
              </label>
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void runCaseSearch()}
              className="px-4 py-2 text-sm border rounded-lg hover:bg-slate-50 disabled:opacity-50"
            >
              Search cases
            </button>
            {caseSearchResults.length > 0 && (
              <ul className="text-xs space-y-2 m-0 p-0 list-none">
                {caseSearchResults.map((row) => (
                  <li key={row.cnr} className="border rounded-lg p-2 flex flex-wrap gap-2 justify-between items-center">
                    <div>
                      <p className="m-0 font-mono">{row.cnr}</p>
                      <p className="m-0 text-slate-600">{row.parties}</p>
                      <p className="m-0 text-slate-500">{row.case_status} · next: {row.next_hearing_date || "—"}</p>
                    </div>
                    <button
                      type="button"
                      className="text-xs px-2 py-1 border rounded-lg"
                      onClick={() => {
                        if (row.cnr) {
                          setCnrInput(row.cnr);
                          void fetchCasePreview(row.cnr);
                        }
                      }}
                    >
                      Preview
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-3 border-t border-slate-100 pt-4">
            <h3 className="text-sm font-semibold text-navy m-0">Sync to matter</h3>
            <label className="text-xs block">
              Matter
              <select
                value={syncMatterId}
                onChange={(e) => setSyncMatterId(e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              >
                <option value="">Select matter…</option>
                {matters.map((m) => (
                  <option key={m.matter_id} value={m.matter_id}>
                    {m.matter_name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={importHearings} onChange={(e) => setImportHearings(e.target.checked)} />
                Import hearings
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={importOrders} onChange={(e) => setImportOrders(e.target.checked)} />
                Import orders
              </label>
            </div>
            <button
              type="button"
              disabled={busy || !cnrInput.trim() || !syncMatterId}
              onClick={() => void syncCaseToMatter()}
              className="px-4 py-2 text-sm bg-navy text-white rounded-lg disabled:opacity-50"
            >
              {busy ? "Syncing…" : "Sync hearings & orders"}
            </button>
            <Link href="/matters" className="text-xs text-blue-700 hover:underline block">
              Create matters →
            </Link>
          </div>
        </section>
      )}

      {mainTab === "cause_list" && summary && <CauseListImportResults summary={summary} />}

      {syncHistory.length > 0 && (
        <section className="le-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-navy m-0 mb-3">Recent sync history</h3>
          <ul className="space-y-2 m-0 p-0 list-none text-xs">
            {syncHistory.slice(0, 10).map((row) => (
              <li key={String(row.log_id)} className="flex flex-wrap justify-between gap-2 border border-slate-100 rounded-lg px-3 py-2">
                <span>{String(row.created_at || "").slice(0, 19).replace("T", " ")} · {String(row.source)}</span>
                <span className={row.status === "ok" ? "text-emerald-700 font-semibold" : "text-red-600 font-semibold"}>
                  {String(row.status)} — parsed {String(row.parsed_count)} / matched {String(row.matched_count)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
