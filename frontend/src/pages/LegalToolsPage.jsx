import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import PageHeader from "../components/PageHeader.jsx";
import Tabs from "../components/Tabs.jsx";
import MarkdownBox from "../components/MarkdownBox.jsx";

const TABS = [
  { id: "ipc", label: "IPC-BNS" },
  { id: "fee", label: "Court Fee" },
  { id: "contract", label: "Contract Review" },
  { id: "predict", label: "Case Prediction" },
  { id: "cite", label: "Smart Citator" },
  { id: "odr", label: "ODR" },
];

export default function LegalToolsPage() {
  const [tab, setTab] = useState("ipc");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [regions, setRegions] = useState([]);
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    api.courtFeeRegions().then((d) => setRegions(d.regions || [])).catch(() => {});
    api.ipcCategories().then((d) => setCategories(d.categories || [])).catch(() => {});
  }, []);

  const run = async (fn) => {
    setBusy(true);
    setResult(null);
    try {
      setResult(await fn());
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Legal Tools" subtitle="IPC-BNS, court fees, contracts, citations, ODR" />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      <div className="flex-1 overflow-y-auto le-scroll p-8 max-w-4xl">
        {tab === "ipc" && (
          <IpcPanel categories={categories} run={run} busy={busy} />
        )}
        {tab === "fee" && <FeePanel regions={regions} run={run} busy={busy} />}
        {tab === "contract" && <ContractPanel run={run} busy={busy} />}
        {tab === "predict" && <PredictPanel run={run} busy={busy} />}
        {tab === "cite" && <CitePanel run={run} busy={busy} />}
        {tab === "odr" && <OdrPanel run={run} busy={busy} />}
        <ToolResult result={result} tab={tab} />
      </div>
    </>
  );
}

function ToolResult({ result, tab }) {
  if (!result) return null;
  if (result.error) return <p className="mt-6 text-red-600 text-sm">{result.error}</p>;
  if (tab === "ipc" && result.status === "mapped")
    return (
      <div className="mt-6 p-4 bg-emerald-50 rounded-xl text-sm">
        <b>{result.ipc_section}</b> → <b>{result.bns_section}</b>
        <p className="text-slate-600 mt-1">{result.description}</p>
      </div>
    );
  if (result.results)
    return (
      <table className="mt-6 w-full text-sm bg-white rounded-xl border overflow-hidden">
        <thead className="bg-slate-50">
          <tr><th className="p-2 text-left">IPC</th><th className="p-2 text-left">BNS</th><th className="p-2 text-left">Desc</th></tr>
        </thead>
        <tbody>
          {result.results.map((r, i) => (
            <tr key={i} className="border-t">
              <td className="p-2">{r.ipc_section}</td>
              <td className="p-2">{r.bns_section}</td>
              <td className="p-2 text-slate-600">{r.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  if (result.sections)
    return (
      <pre className="mt-6 text-xs bg-white p-4 rounded-xl border overflow-auto max-h-64">
        {JSON.stringify(result.sections, null, 2)}
      </pre>
    );
  if (result.final_fee != null)
    return (
      <div className="mt-6 p-6 bg-white rounded-2xl border border-amber-200/50 shadow-sm">
        <p className="text-3xl font-bold text-amber-600">₹{result.final_fee?.toLocaleString()}</p>
        <p className="text-sm text-slate-500">Estimated court fee</p>
        <pre className="mt-4 text-xs text-slate-600 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
      </div>
    );
  if (result.analysis) return <div className="mt-6"><MarkdownBox content={result.analysis} /></div>;
  if (result.prediction) return <div className="mt-6"><MarkdownBox content={result.prediction} /></div>;
  if (result.result) return <div className="mt-6"><MarkdownBox content={result.result} /></div>;
  if (result.proposal) return <div className="mt-6"><MarkdownBox content={result.proposal} /></div>;
  return null;
}

function IpcPanel({ categories, run, busy }) {
  const [section, setSection] = useState("");
  const [bulk, setBulk] = useState("");
  const [cat, setCat] = useState("murder");
  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white p-4 rounded-xl border">
          <h3 className="font-semibold text-sm mb-2">Single conversion</h3>
          <input className="w-full border rounded-lg px-3 py-2 text-sm mb-2" placeholder="e.g. 302" value={section} onChange={(e) => setSection(e.target.value)} />
          <button type="button" disabled={busy} onClick={() => run(() => api.ipcConvert(section))} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Convert</button>
        </div>
        <div className="bg-white p-4 rounded-xl border">
          <h3 className="font-semibold text-sm mb-2">Bulk</h3>
          <textarea className="w-full border rounded-lg px-3 py-2 text-sm mb-2" placeholder="302, 420, 376" value={bulk} onChange={(e) => setBulk(e.target.value)} />
          <button type="button" disabled={busy} onClick={() => run(() => api.ipcBulk(bulk.split(",").map((s) => s.trim()).filter(Boolean)))} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Convert all</button>
        </div>
      </div>
      <div className="bg-white p-4 rounded-xl border">
        <select className="border rounded-lg px-3 py-2 text-sm mr-2" value={cat} onChange={(e) => setCat(e.target.value)}>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button type="button" disabled={busy} onClick={() => run(() => api.ipcCategory(cat))} className="px-4 py-2 border rounded-lg text-sm">Browse category</button>
      </div>
    </div>
  );
}

function FeePanel({ regions, run, busy }) {
  const [v, setV] = useState(100000);
  const [region, setRegion] = useState(regions[0] || "Delhi");
  const [suit, setSuit] = useState("civil");
  const [court, setCourt] = useState("district");
  return (
    <div className="bg-white p-6 rounded-xl border space-y-3 max-w-lg">
      <input type="number" className="w-full border rounded-lg px-3 py-2" value={v} onChange={(e) => setV(+e.target.value)} />
      <select className="w-full border rounded-lg px-3 py-2" value={region} onChange={(e) => setRegion(e.target.value)}>
        {regions.map((r) => <option key={r}>{r}</option>)}
      </select>
      <select className="w-full border rounded-lg px-3 py-2" value={suit} onChange={(e) => setSuit(e.target.value)}>
        {["civil", "appeal", "revision", "divorce", "succession"].map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select className="w-full border rounded-lg px-3 py-2" value={court} onChange={(e) => setCourt(e.target.value)}>
        {["district", "high", "supreme"].map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <button type="button" disabled={busy} onClick={() => run(() => api.courtFeeCalc({ suit_value: v, region, suit_type: suit, court_level: court }))} className="w-full py-2.5 bg-navy text-white rounded-lg text-sm font-semibold">Calculate fee</button>
    </div>
  );
}

function ContractPanel({ run, busy }) {
  return (
    <div className="bg-white p-6 rounded-xl border max-w-lg">
      <input type="file" accept=".pdf" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.contractReview(f)); e.target.value = ""; }} disabled={busy} className="text-sm" />
      <p className="text-xs text-slate-500 mt-2">Upload contract PDF for AI risk analysis</p>
    </div>
  );
}

function PredictPanel({ run, busy }) {
  const [details, setDetails] = useState("");
  const [court, setCourt] = useState("District Court");
  return (
    <div className="bg-white p-6 rounded-xl border space-y-3">
      <p className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">AI predictions are informational only</p>
      <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-32" value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Case facts…" />
      <select className="w-full border rounded-lg px-3 py-2 text-sm" value={court} onChange={(e) => setCourt(e.target.value)}>
        {["District Court", "High Court", "Supreme Court", "Consumer Forum", "Labour Court"].map((c) => <option key={c}>{c}</option>)}
      </select>
      <button type="button" disabled={busy} onClick={() => run(() => api.casePrediction({ case_details: details, court_type: court }))} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Predict outcome</button>
    </div>
  );
}

function CitePanel({ run, busy }) {
  const [text, setText] = useState("");
  return (
    <div className="bg-white p-6 rounded-xl border space-y-3">
      <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="One citation per line" />
      <button type="button" disabled={busy} onClick={() => run(() => api.checkCitations(text.split("\n").map((s) => s.trim()).filter(Boolean)))} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Check citations</button>
    </div>
  );
}

function OdrPanel({ run, busy }) {
  const [form, setForm] = useState({ complainant: "", respondent: "", complaint_type: "Consumer Issue", dispute_value: 10000, details: "" });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <div className="bg-white p-6 rounded-xl border space-y-3 max-w-lg">
      <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Complainant" value={form.complainant} onChange={(e) => set("complainant", e.target.value)} />
      <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Respondent" value={form.respondent} onChange={(e) => set("respondent", e.target.value)} />
      <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-24" placeholder="Dispute details" value={form.details} onChange={(e) => set("details", e.target.value)} />
      <button type="button" disabled={busy} onClick={() => run(() => api.odrProposal(form))} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">Generate proposal</button>
    </div>
  );
}
