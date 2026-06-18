import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import PageHeader from "../components/PageHeader.jsx";

const FIELD_HINTS = {
  LEGAL_NOTICE: ["client_name", "client_address", "recipient_name", "recipient_address", "subject", "facts", "legal_grounds", "demands", "notice_period"],
  AFFIDAVIT: ["deponent_name", "deponent_father", "deponent_age", "deponent_address", "affidavit_content", "verification_place"],
  CONTRACT: ["party_a_name", "party_b_name", "recitals", "scope", "consideration", "start_date", "end_date", "jurisdiction"],
};

export default function DraftingPage() {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState("LEGAL_NOTICE");
  const [fields, setFields] = useState([]);
  const [context, setContext] = useState({});
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.fetchDraftTemplates().then((d) => setTemplates(d.templates || [])).catch(() => {});
  }, []);

  useEffect(() => {
    api.fetchDraftFields(selected).then((d) => {
      const f = d.fields?.length ? d.fields : FIELD_HINTS[selected] || [];
      setFields(f);
      setContext({});
      setDraft("");
    }).catch(() => setFields(FIELD_HINTS[selected] || []));
  }, [selected]);

  const generate = async (use_ai) => {
    setBusy(true);
    try {
      const res = await api.generateDraft(selected, context, use_ai);
      setDraft(res.content);
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadTxt = () => {
    const blob = new Blob([draft], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${selected}_${Date.now()}.txt`;
    a.click();
  };

  return (
    <>
      <PageHeader title="Automated Legal Drafter" subtitle="Generate professional legal documents instantly" />
      <div className="flex-1 overflow-y-auto le-scroll p-8">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-8 max-w-3xl">
          {templates.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setSelected(t.id)}
              className={`p-4 rounded-xl border text-left text-sm font-semibold transition-all ${
                selected === t.id ? "border-navy bg-navy/5 text-navy" : "border-slate-200 bg-white hover:border-slate-400"
              }`}
            >
              <span className="text-xl mr-2">{t.icon}</span>
              {t.id.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        <h2 className="font-serif text-lg font-bold text-navy mb-4">
          {selected.replace(/_/g, " ")} — Details
        </h2>
        <div className="grid md:grid-cols-2 gap-3 max-w-3xl mb-6">
          {fields.slice(0, 20).map((f) => (
            <label key={f} className="block text-sm">
              <span className="text-slate-600 capitalize">{f.replace(/_/g, " ")}</span>
              {f.includes("facts") || f.includes("content") || f.includes("recitals") ? (
                <textarea
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm h-20"
                  value={context[f] || ""}
                  onChange={(e) => setContext((c) => ({ ...c, [f]: e.target.value }))}
                />
              ) : (
                <input
                  className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                  value={context[f] || ""}
                  onChange={(e) => setContext((c) => ({ ...c, [f]: e.target.value }))}
                />
              )}
            </label>
          ))}
        </div>

        <div className="flex gap-3 mb-8">
          <button type="button" disabled={busy} onClick={() => generate(false)} className="px-5 py-2.5 bg-navy text-white rounded-xl text-sm font-semibold">
            Generate draft
          </button>
          <button type="button" disabled={busy} onClick={() => generate(true)} className="px-5 py-2.5 border border-navy text-navy rounded-xl text-sm font-semibold">
            AI-enhanced draft
          </button>
        </div>

        {draft && (
          <div className="bg-white rounded-2xl border p-6 max-w-4xl">
            <h3 className="font-semibold mb-3">Generated document</h3>
            <pre className="text-xs whitespace-pre-wrap font-sans text-slate-700 max-h-96 overflow-y-auto le-scroll">{draft}</pre>
            <button type="button" onClick={downloadTxt} className="mt-4 px-4 py-2 border rounded-lg text-sm font-semibold hover:border-navy">
              Download TXT
            </button>
          </div>
        )}
      </div>
    </>
  );
}
