"use client";

import type { AnalysisJson } from "./crmUtils";
import { scoreBandColor } from "./crmUtils";

type Props = {
  analysis: AnalysisJson;
  leadScore?: number;
  leadScoreBand?: string;
};

function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span>{label}</span>
        <span>{percent}%</span>
      </div>
      <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-600 rounded-full transition-all"
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
    </div>
  );
}

export default function LeadAnalysisPanel({ analysis, leadScore, leadScoreBand }: Props) {
  const cls = analysis.classification || {};
  const juris = analysis.jurisdiction || {};
  const score = analysis.lead_score || {};
  const total = leadScore ?? score.total ?? 0;
  const band = leadScoreBand || score.band || "weak";
  const docR = analysis.document_readiness || {};
  const evR = analysis.evidence_readiness || {};
  const strength = analysis.case_strength || {};

  return (
    <div className="space-y-4">
      {analysis.executive_summary && (
        <section className="bg-white border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-navy mb-2">Executive summary</h3>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{analysis.executive_summary}</p>
        </section>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <section className="bg-white border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-navy mb-2">Classification</h3>
          <p className="text-sm">
            <b>Primary:</b> {cls.primary || "—"}
          </p>
          <p className="text-sm">
            <b>Secondary:</b> {cls.secondary || "—"}
          </p>
          {cls.subcategory && (
            <p className="text-sm">
              <b>Detail:</b> {cls.subcategory}
            </p>
          )}
          <p className="text-xs text-slate-500 mt-2">
            Confidence: {Math.round(Number(cls.confidence || 0) * 100)}%
          </p>
        </section>

        <section className="bg-white border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-navy mb-2">Jurisdiction</h3>
          <p className="text-sm">City: {String(juris.city || "—")}</p>
          <p className="text-sm">Court: {String(juris.likely_court || "—")}</p>
          <p className="text-sm">Police: {String(juris.likely_police_station || "—")}</p>
          <p className="text-xs text-slate-500 mt-2">
            Confidence: {Math.round(Number(juris.confidence || 0) * 100)}%
          </p>
        </section>
      </div>

      <section className="bg-white border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-navy">Lead score</h3>
          <span className={`text-2xl font-bold ${scoreBandColor(band)}`}>
            {total}
            <span className="text-sm font-normal text-slate-500"> / 100</span>
          </span>
        </div>
        {score.explanation && <p className="text-xs text-slate-600 mb-3">{score.explanation}</p>}
        <div className="space-y-2">
          {(score.factors || []).map((f) => (
            <div key={f.name}>
              <div className="flex justify-between text-xs">
                <span>{f.name}</span>
                <span>
                  {f.score}/{f.max}
                </span>
              </div>
              <div className="h-1.5 bg-slate-200 rounded-full mt-0.5">
                <div
                  className="h-full bg-navy rounded-full"
                  style={{ width: `${(f.score / Math.max(f.max, 1)) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white border rounded-xl p-4">
        <h3 className="text-sm font-semibold text-navy mb-2">Case strength</h3>
        <p className="text-sm capitalize mb-2">Rating: {strength.rating || "—"}</p>
        {!!strength.strengths?.length && (
          <ul className="text-xs list-disc pl-4 text-emerald-800">
            {strength.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        )}
        {!!strength.weaknesses?.length && (
          <ul className="text-xs list-disc pl-4 text-red-800 mt-2">
            {strength.weaknesses.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid md:grid-cols-2 gap-4">
        <section className="bg-white border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold text-navy">Document readiness</h3>
          <ProgressBar percent={Number(docR.percent || 0)} label="Documents" />
          <ul className="text-xs space-y-1">
            {(docR.required || []).map((r) => (
              <li
                key={r.label}
                className={r.status === "present" ? "text-emerald-700" : "text-amber-700"}
              >
                {r.status === "present" ? "✓" : "○"} {r.label}
              </li>
            ))}
          </ul>
        </section>
        <section className="bg-white border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold text-navy">Evidence readiness</h3>
          <ProgressBar percent={Number(evR.percent || 0)} label="Evidence" />
          <ul className="text-xs space-y-1">
            {(evR.types || []).map((t) => (
              <li key={t.type} className={t.present ? "text-emerald-700" : "text-slate-500"}>
                {t.present ? "✓" : "○"} {t.type}
              </li>
            ))}
          </ul>
        </section>
      </div>

      {!!analysis.applicable_laws?.length && (
        <section className="bg-white border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-navy mb-2">Applicable laws</h3>
          {analysis.applicable_laws.map((law, i) => (
            <div key={i} className="text-sm mb-2">
              <b>{law.act}</b>
              {law.sections?.length ? `: ${law.sections.join(", ")}` : ""}
            </div>
          ))}
        </section>
      )}

      {!!analysis.contradictions?.length && (
        <section className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">Contradictions</h3>
          {analysis.contradictions.map((c, i) => (
            <div key={i} className="text-xs mb-2">
              <span className="font-medium uppercase text-amber-800">{c.severity}</span>
              <p>A: {c.a}</p>
              <p>B: {c.b}</p>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
