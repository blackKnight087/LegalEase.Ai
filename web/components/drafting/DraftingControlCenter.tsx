"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import PageShell from "@/components/ui/PageShell";
import Alert from "@/components/ui/Alert";
import { ButtonLink } from "@/components/ui/Button";
import DraftingTemplateGallery, { DocumentTypePill } from "@/components/drafting/DraftingTemplateGallery";
import * as api from "@/lib/api";
import { formatDocumentType, healthScoreTone, KANBAN_COLUMN_META } from "@/lib/draftingUi";
import {
  getLegalTemplateHtml,
  getTemplateDefaultTitle,
  type LegalTemplateId,
} from "@/lib/legalDocumentTemplates";

const COLUMNS = [
  "draft",
  "in_review",
  "partner_review",
  "needs_revision",
  "approved",
  "ready_to_file",
  "filed",
  "executed",
  "archived",
] as const;

function HealthBar({ score }: { score: number }) {
  const tone = healthScoreTone(score);
  const pct = Math.min(100, Math.max(0, score));
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] mb-0.5">
        <span className="text-slate-500">Document health</span>
        <span className={`font-semibold tabular-nums ${tone.text}`}>{pct}%</span>
      </div>
      <div className="drafting-health-bar">
        <div className={`drafting-health-bar__fill ${tone.bar}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-[88px] rounded-2xl bg-slate-100 border border-slate-200" />
      ))}
    </div>
  );
}

export default function DraftingControlCenter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const matterFilter = searchParams.get("matter") || "";
  const [cc, setCc] = useState<Awaited<ReturnType<typeof api.draftingControlCenter>> | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [precSearch, setPrecSearch] = useState("");
  const [precResults, setPrecResults] = useState<Array<Record<string, unknown>>>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.draftingControlCenter(matterFilter);
      setCc(data);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load control center");
    } finally {
      setLoading(false);
    }
  }, [matterFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const searchPrecedents = async () => {
    if (!precSearch.trim()) return;
    setBusy(true);
    try {
      const r = await api.searchPrecedents(precSearch);
      setPrecResults((r.results as Array<Record<string, unknown>>) || []);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Precedent search failed");
    } finally {
      setBusy(false);
    }
  };

  const createFromTemplate = async (templateId: LegalTemplateId) => {
    setBusy(true);
    try {
      const label = getTemplateDefaultTitle(templateId);
      const { document } = await api.createWorkspaceDocument({
        title: label,
        document_type: templateId,
        content: getLegalTemplateHtml(templateId, {}),
        content_format: "html",
      });
      router.push(`/drafting/${document.draft_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const columns = (cc?.columns || {}) as Record<
    string,
    Array<{
      draft_id: string;
      title: string;
      document_type?: string;
      snippet?: string;
      health_score?: number;
      filing_readiness_score?: number;
    }>
  >;

  const kpiItems = [
    { label: "Firm health avg", value: cc?.health_score_avg ?? "—", accent: "from-slate-600 to-slate-800" },
    { label: "Awaiting action", value: (cc?.awaiting_action || []).length, accent: "from-amber-500 to-orange-500" },
    { label: "Reviewer queue", value: (cc?.reviewer_queue || []).length, accent: "from-blue-500 to-indigo-600" },
    { label: "Near deadline", value: (cc?.near_deadline || []).length, accent: "from-red-500 to-rose-600" },
    {
      label: "Precedents",
      value: Number(cc?.analytics?.precedent_count) || 0,
      accent: "from-violet-500 to-purple-600",
    },
  ];

  const totalDrafts = COLUMNS.reduce((n, c) => n + (columns[c]?.length || 0), 0);

  return (
    <div className="flex flex-col h-full min-h-0 drafting-studio animate-fade-in">
      <PageHeader
        eyebrow="Practice"
        title="Drafting Studio"
        subtitle={
          matterFilter
            ? "Matter-filtered document lifecycle and filing readiness"
            : "Create, review, approve, and file legal documents across your firm"
        }
      >
        <button
          type="button"
          disabled={loading}
          onClick={() => void load()}
          className="text-sm px-3 py-2 min-h-[40px] border border-slate-200 rounded-xl hover:bg-slate-50 disabled:opacity-50 bg-white"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        <ButtonLink href="/matters" variant="secondary" size="md">
          Matters
        </ButtonLink>
      </PageHeader>

      {matterFilter && (
        <p className="mx-4 lg:mx-8 text-sm text-slate-600 shrink-0">
          Filtered matter{" "}
          <code className="text-xs bg-white border border-slate-200 px-1.5 py-0.5 rounded-md">
            {matterFilter.slice(0, 8)}…
          </code>
          {" · "}
          <Link href="/drafting" className="text-blue-700 font-medium no-underline hover:underline">
            All documents
          </Link>
          {" · "}
          <Link
            href={`/matters/${matterFilter}?tab=drafting`}
            className="text-blue-700 font-medium no-underline hover:underline"
          >
            Matter workspace
          </Link>
        </p>
      )}

      <PageShell maxWidth="7xl" className="space-y-6 pb-10">
        {err && (
          <Alert variant="error">
            {err}
            <button type="button" className="ml-2 text-sm underline" onClick={() => void load()}>
              Retry
            </button>
          </Alert>
        )}

        <section className="le-card rounded-2xl p-5 sm:p-6 lg:p-7">
          <header className="mb-6 pb-4 border-b border-slate-100">
            <h2 className="font-serif text-xl lg:text-2xl text-slate-900 m-0">New document</h2>
            <p className="le-section-desc m-0 mt-1.5 max-w-2xl">
              Choose a practice template. Each draft includes operative clauses, party blocks, jurisdiction, and
              execution — ready to edit in the Word-style studio.
            </p>
          </header>
          <DraftingTemplateGallery busy={busy} onSelect={createFromTemplate} />
        </section>

        {loading && !cc ? <KpiSkeleton /> : null}

        {!loading || cc ? (
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {kpiItems.map((k) => (
              <div key={k.label} className="le-metric-card min-h-[88px]">
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${k.accent}`} />
                <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500 m-0">
                  {k.label}
                </p>
                <p className="text-2xl font-bold text-slate-900 m-0 mt-1 tabular-nums">{k.value}</p>
              </div>
            ))}
          </section>
        ) : null}

        <section className="le-card rounded-2xl p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <h2 className="le-section-title m-0">Lifecycle board</h2>
              <p className="le-section-desc m-0 mt-0.5">{totalDrafts} documents across workflow stages</p>
            </div>
          </div>

          {totalDrafts === 0 && !loading ? (
            <div className="le-empty py-10">
              <p className="font-serif text-lg text-slate-800 m-0">No documents yet</p>
              <p className="text-sm text-slate-500 mt-2 max-w-md m-0">
                Choose Bail Application, Agreement, or Petition above to create your first firm-ready draft.
              </p>
            </div>
          ) : (
            <div className="drafting-kanban-board">
              {COLUMNS.map((col) => {
                const meta = KANBAN_COLUMN_META[col] || { label: col, accent: "from-slate-400 to-slate-500" };
                const items = columns[col] || [];
                return (
                  <div key={col} className="drafting-kanban-col">
                    <div className="drafting-kanban-col__head">
                      <div className="min-w-0">
                        <div className={`h-0.5 w-8 rounded-full bg-gradient-to-r ${meta.accent} mb-1.5`} />
                        <p className="text-sm font-semibold text-slate-800 m-0">{meta.label}</p>
                      </div>
                      <span className="text-xs font-bold tabular-nums text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                        {items.length}
                      </span>
                    </div>
                    <div className="drafting-kanban-col__body">
                      {items.length === 0 ? (
                        <p className="text-xs text-slate-400 text-center py-6 m-0">No documents</p>
                      ) : (
                        items.map((d) => (
                          <Link key={d.draft_id} href={`/drafting/${d.draft_id}`} className="drafting-doc-card">
                            <p className="font-semibold text-slate-900 text-sm line-clamp-2 m-0 leading-snug">
                              {d.title}
                            </p>
                            <div className="mt-1.5">
                              <DocumentTypePill type={d.document_type} />
                            </div>
                            <HealthBar score={d.health_score ?? 0} />
                          </Link>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div className="grid lg:grid-cols-2 gap-6">
          <section className="le-card rounded-2xl p-5">
            <h2 className="le-section-title m-0 mb-3">Reviewer queue</h2>
            {(cc?.reviewer_queue || []).length === 0 ? (
              <p className="text-sm text-slate-500 m-0">No pending assignments.</p>
            ) : (
              <ul className="space-y-0 divide-y divide-slate-100">
                {(cc?.reviewer_queue || []).map((a, i) => {
                  const item = a as { assignment_id?: string; draft_id: string; title: string; role?: string };
                  return (
                    <li key={item.assignment_id || i} className="flex justify-between items-center py-3 gap-3">
                      <Link
                        href={`/drafting/${item.draft_id}/review`}
                        className="text-sm font-medium text-blue-700 no-underline hover:underline truncate"
                      >
                        {item.title}
                      </Link>
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 shrink-0">
                        {item.role}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="le-card rounded-2xl p-5">
            <h2 className="le-section-title m-0 mb-3">Recent activity</h2>
            {(cc?.recent_activity || []).length === 0 ? (
              <p className="text-sm text-slate-500 m-0">Activity will appear as documents move through workflow.</p>
            ) : (
              <ul className="space-y-3 max-h-52 overflow-y-auto le-scroll">
                {(cc?.recent_activity || []).map((a, i) => {
                  const act = a as {
                    user_name: string;
                    action: string;
                    draft_id: string;
                    title: string;
                    created_at?: string;
                  };
                  return (
                    <li key={i} className="text-sm border-l-2 border-blue-200 pl-3">
                      <span className="font-medium text-slate-800">{act.user_name}</span>{" "}
                      <span className="text-slate-600">{act.action}</span>
                      <br />
                      <Link
                        href={`/drafting/${act.draft_id}`}
                        className="text-blue-700 font-medium no-underline hover:underline"
                      >
                        {act.title}
                      </Link>
                      <span className="block text-[10px] text-slate-400 mt-0.5">
                        {act.created_at ? new Date(act.created_at).toLocaleString() : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        <section className="le-card rounded-2xl p-5">
          <h2 className="le-section-title m-0">Precedent intelligence</h2>
          <p className="le-section-desc m-0 mt-1 mb-4">Search firm precedents by matter type or drafting pattern</p>
          <div className="flex flex-col sm:flex-row gap-2 max-w-xl">
            <input
              className="le-input flex-1"
              placeholder="e.g. anticipatory bail in economic offence"
              value={precSearch}
              onChange={(e) => setPrecSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchPrecedents()}
            />
            <button
              type="button"
              onClick={searchPrecedents}
              disabled={busy}
              className="px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 disabled:opacity-50 shrink-0"
            >
              Search
            </button>
          </div>
          <ul className="mt-4 space-y-2">
            {precResults.map((p) => (
              <li
                key={String(p.precedent_id)}
                className="rounded-xl border border-slate-100 bg-slate-50/60 p-3 hover:border-blue-200 transition-colors"
              >
                <p className="font-medium text-slate-900 text-sm m-0">{String(p.title)}</p>
                <p className="text-xs text-slate-500 m-0 mt-1">
                  {formatDocumentType(String(p.document_type))} · confidence {String(p.confidence)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </PageShell>
    </div>
  );
}
