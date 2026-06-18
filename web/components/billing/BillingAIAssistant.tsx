"use client";

import { useState } from "react";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import * as api from "@/lib/api";

type Props = {
  matterId: string;
  onApply: (text: string) => void;
};

export default function BillingAIAssistant({ matterId, onApply }: Props) {
  const [raw, setRaw] = useState("worked on bail");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);

  const polish = async () => {
    setBusy(true);
    try {
      const r = await api.previewBillingNarrative({
        raw_activity: raw,
        units_logged: 1,
        matter_id: matterId,
      });
      setOut(r.narrative);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border border-slate-200 rounded-xl bg-gradient-to-br from-slate-50 to-white p-4 space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-navy">AI billing assistant</h2>
        <p className="text-xs text-slate-500">Convert rough notes into professional invoice narratives</p>
      </div>
      <VoiceTextarea className="min-h-[4rem] text-sm" rows={3} value={raw} onChange={setRaw} polishOnStop={false} />
      <button type="button" disabled={busy} onClick={polish} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">
        {busy ? "Polishing…" : "Generate narrative"}
      </button>
      {out && (
        <div className="p-3 bg-white border border-slate-200 rounded-lg text-sm text-slate-700">
          {out}
          <button type="button" className="mt-2 text-xs text-emerald-700 font-semibold underline" onClick={() => onApply(out)}>
            Use in time entry
          </button>
        </div>
      )}
    </section>
  );
}
