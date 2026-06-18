"use client";

import { useEffect, useState } from "react";
import MarkdownBox from "@/components/ui/MarkdownBox";
import * as api from "@/lib/api";

const TOOLS = [
  { id: "hearing_brief", label: "Hearing brief / prep pack" },
  { id: "timeline", label: "Case timeline" },
  { id: "contradictions", label: "Contradiction report" },
  { id: "order_summary", label: "Summarize last order" },
  { id: "cross_examination", label: "Cross-examination questions" },
  { id: "evidence_gaps", label: "Missing evidence" },
];

export default function LitigationAITab() {
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState("");
  const [tool, setTool] = useState("hearing_brief");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.listMatters().then((r) => {
      setMatters(r.matters || []);
      if (r.matters?.[0]) setMatterId(r.matters[0].matter_id);
    });
  }, []);

  const run = async () => {
    if (!matterId) return;
    setBusy(true);
    try {
      const r = await api.runLitigationAI({ tool, matter_id: matterId });
      if (r.markdown) setOut(String(r.markdown));
      else if (r.text) setOut(String(r.text));
      else if (r.pairs) setOut(JSON.stringify(r.pairs, null, 2));
      else if (r.events) setOut(JSON.stringify(r.events, null, 2));
      else setOut(JSON.stringify(r, null, 2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <h2 className="text-lg font-semibold text-navy">AI litigation assistant</h2>
      <select className="w-full border rounded-lg px-3 py-2 text-sm" value={matterId} onChange={(e) => setMatterId(e.target.value)}>
        {matters.map((m) => (
          <option key={m.matter_id} value={m.matter_id}>{m.matter_name}</option>
        ))}
      </select>
      <div className="grid sm:grid-cols-2 gap-2">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTool(t.id)}
            className={`text-left px-3 py-2 rounded-lg border text-sm ${tool === t.id ? "border-navy bg-navy text-white" : "border-slate-200"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <button type="button" disabled={busy} onClick={run} className="px-5 py-2 bg-emerald-700 text-white rounded-lg text-sm font-medium">
        {busy ? "Generating…" : "Run"}
      </button>
      {out && (
        <div className="border rounded-xl p-4 bg-slate-50 max-h-[28rem] overflow-y-auto">
          <MarkdownBox content={out.startsWith("{") ? `\`\`\`json\n${out}\n\`\`\`` : out} />
        </div>
      )}
    </div>
  );
}
