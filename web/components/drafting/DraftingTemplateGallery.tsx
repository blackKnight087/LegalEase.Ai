"use client";

import {
  FEATURED_TEMPLATE_IDS,
  formatDocumentType,
  templateMonogram,
} from "@/lib/draftingUi";
import { LEGAL_TEMPLATES, type LegalTemplateId, type LegalTemplateMeta } from "@/lib/legalDocumentTemplates";

type Props = {
  onSelect: (id: LegalTemplateId) => void;
  busy?: boolean;
  highlightId?: string;
  compact?: boolean;
};

const CATEGORY_ACCENT: Record<string, string> = {
  Criminal: "drafting-cat--criminal",
  Litigation: "drafting-cat--litigation",
  Commercial: "drafting-cat--commercial",
  Employment: "drafting-cat--employment",
  General: "drafting-cat--general",
};

const CATEGORY_ORDER = ["Criminal", "Commercial", "Litigation", "Employment", "General"] as const;

function TemplateCard({
  t,
  busy,
  highlightId,
  featured,
  onSelect,
}: {
  t: LegalTemplateMeta;
  busy?: boolean;
  highlightId?: string;
  featured?: boolean;
  onSelect: (id: LegalTemplateId) => void;
}) {
  const catClass = CATEGORY_ACCENT[t.category] || CATEGORY_ACCENT.General;
  const active = highlightId === t.id;

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => onSelect(t.id)}
      className={[
        "drafting-template-card group",
        featured ? "drafting-template-card--featured" : "drafting-template-card--standard",
        catClass,
        active ? "drafting-template-card--active" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="drafting-template-card__inner">
        <div className="drafting-template-card__top">
          <div className="drafting-template-monogram" aria-hidden>
            {templateMonogram(t.label)}
          </div>
          <span className="drafting-template-card__category">{t.category}</span>
        </div>
        <p className="drafting-template-card__title">{t.label}</p>
        <p className="drafting-template-card__desc">{t.description}</p>
        <span className="drafting-template-card__cta">Create document</span>
      </div>
    </button>
  );
}

export default function DraftingTemplateGallery({ onSelect, busy, highlightId, compact }: Props) {
  const featured = FEATURED_TEMPLATE_IDS.map((id) => LEGAL_TEMPLATES.find((t) => t.id === id)).filter(
    Boolean
  ) as LegalTemplateMeta[];

  const secondary = CATEGORY_ORDER.flatMap((cat) =>
    LEGAL_TEMPLATES.filter(
      (t) =>
        t.category === cat &&
        t.id !== "custom" &&
        !(FEATURED_TEMPLATE_IDS as readonly string[]).includes(t.id)
    )
  );

  return (
    <div className={`drafting-template-gallery ${compact ? "drafting-template-gallery--compact" : ""}`}>
      {!compact && featured.length > 0 && (
        <section className="drafting-template-section">
          <div className="drafting-template-section__head">
            <h3 className="drafting-template-section__title">Quick start</h3>
            <p className="drafting-template-section__sub">Most used firm templates</p>
          </div>
          <div className="drafting-template-featured">
            {featured.map((t) => (
              <TemplateCard
                key={t.id}
                t={t}
                busy={busy}
                highlightId={highlightId}
                featured
                onSelect={onSelect}
              />
            ))}
          </div>
        </section>
      )}

      {secondary.length > 0 && (
        <section className="drafting-template-section">
          <div className="drafting-template-section__head">
            <h3 className="drafting-template-section__title">
              {compact ? "All templates" : "More document types"}
            </h3>
            <p className="drafting-template-section__sub">
              {secondary.length} templates · full clauses and execution blocks
            </p>
          </div>
          <div className="drafting-template-grid">
            {(compact ? [...featured, ...secondary] : secondary).map((t) => (
              <TemplateCard
                key={t.id}
                t={t}
                busy={busy}
                highlightId={highlightId}
                onSelect={onSelect}
              />
            ))}
          </div>
        </section>
      )}

      <div className="drafting-template-footer">
        <button
          type="button"
          disabled={busy}
          onClick={() => onSelect("custom")}
          className="drafting-template-blank"
        >
          <span className="drafting-template-monogram drafting-template-monogram--muted">BL</span>
          <span>
            <span className="drafting-template-blank__title">Structured blank</span>
            <span className="drafting-template-blank__sub">Minimal sections with execution block</span>
          </span>
        </button>
      </div>
    </div>
  );
}

export function DocumentTypePill({ type }: { type?: string }) {
  if (!type) return null;
  return (
    <span className="inline-flex text-[10px] font-semibold uppercase tracking-wide text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">
      {formatDocumentType(type)}
    </span>
  );
}
