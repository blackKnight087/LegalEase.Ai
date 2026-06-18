"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { formatDocumentType } from "@/lib/draftingUi";
import LegalDocumentEditor from "@/components/drafting/LegalDocumentEditor";
import DraftingLegacyTools from "@/components/drafting/LegacyTools";
import DraftLitigationPanel from "@/components/drafting/DraftLitigationPanel";
import DocumentOutlinePanel from "@/components/drafting/DocumentOutlinePanel";
import ClauseLibraryDrawer from "@/components/drafting/ClauseLibraryDrawer";
import DocumentHealthPanel from "@/components/drafting/DocumentHealthPanel";
import CopilotChatPanel from "@/components/drafting/CopilotChatPanel";
import MatterContextBar from "@/components/drafting/MatterContextBar";
import DocumentTemplatePicker from "@/components/drafting/DocumentTemplatePicker";
import TrackChangesPanel from "@/components/drafting/TrackChangesPanel";
import ApprovalWorkflowPanel from "@/components/drafting/ApprovalWorkflowPanel";
import PrecedentIntelPanel from "@/components/drafting/PrecedentIntelPanel";
import AnnexureTocPanel from "@/components/drafting/AnnexureTocPanel";
import type { LegalDocumentEditorHandle } from "@/components/drafting/LegalDocumentEditor";
import {
  EXECUTION_BLOCK_HTML,
  appendHtmlFragment,
  markdownToHtml,
  normalizeContent,
  type OutlineSection,
} from "@/lib/legalDocumentFormat";
import {
  getLegalTemplateHtml,
  isDocumentEmpty,
  type LegalTemplateId,
} from "@/lib/legalDocumentTemplates";
import * as api from "@/lib/api";

type Panel = "editor" | "preview" | "review" | "versions" | "tools";
type Sidebar =
  | "health"
  | "clauses"
  | "copilot"
  | "track"
  | "approval"
  | "precedents"
  | "toc"
  | "comments"
  | "links";

const WORKFLOW = [
  "draft",
  "in_review",
  "partner_review",
  "needs_revision",
  "approved",
  "ready_to_file",
  "filed",
  "executed",
  "archived",
];

const COPILOT_CMDS = [
  ["rewrite_formal", "Rewrite formal"],
  ["shorten", "Shorten"],
  ["expand", "Expand"],
  ["summarize", "Summarize"],
  ["explain_clause", "Explain"],
  ["draft_clause", "Draft clause"],
  ["petition_section", "Petition §"],
  ["notice_section", "Notice §"],
  ["execution_block", "Execution"],
  ["signature_block", "Signatures"],
  ["precedent_language", "Precedent"],
];

export default function DraftingEditorPage() {
  const params = useParams();
  const draftId = String(params.draftId || "");
  const [doc, setDoc] = useState<api.WorkspaceDocument | null>(null);
  const [content, setContent] = useState("");
  const [contentFormat, setContentFormat] = useState<"html" | "markdown">("markdown");
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState("draft");
  const [matterId, setMatterId] = useState("");
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [versions, setVersions] = useState<
    Array<{ version_number: number; change_summary: string }>
  >([]);
  const [comments, setComments] = useState<
    Array<{ comment_id: string; author_name: string; body: string }>
  >([]);
  const [insights, setInsights] = useState<Record<string, unknown> | null>(null);
  const [clauseIntel, setClauseIntel] = useState<Record<string, unknown> | null>(null);
  const [panel, setPanel] = useState<Panel>("editor");
  const [sidebar, setSidebar] = useState<Sidebar>("health");
  const [outline, setOutline] = useState<OutlineSection[]>([]);
  const [recentClauses, setRecentClauses] = useState<string[]>([]);
  const editorRef = useRef<LegalDocumentEditorHandle>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [review, setReview] = useState<Record<string, unknown> | null>(null);
  const [diffHtml, setDiffHtml] = useState("");
  const [sideBySide, setSideBySide] = useState("");
  const [compareA, setCompareA] = useState(1);
  const [compareB, setCompareB] = useState(2);
  const [copilotInstr, setCopilotInstr] = useState("");
  const [clauses, setClauses] = useState<
    Array<{ clause_id: string; clause_tag: string; clause_text_content: string }>
  >([]);
  const [clauseTag, setClauseTag] = useState("");
  const [newComment, setNewComment] = useState("");
  const [watermark, setWatermark] = useState("");
  const [presence, setPresence] = useState<Array<{ user_name: string }>>([]);
  const [pendingChanges, setPendingChanges] = useState(0);
  const [matterVars, setMatterVars] = useState<Record<string, string>>({});
  const [liveStats, setLiveStats] = useState({ words: 0, pages: 1 });
  const [selectionText, setSelectionText] = useState("");
  const [templateOpen, setTemplateOpen] = useState(false);
  const [docHeader, setDocHeader] = useState("");
  const [docFooter, setDocFooter] = useState("Confidential · Draft");
  const lastSaved = useRef({ content: "", status: "", title: "", matterId: "" });
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showOk = useCallback((msg: string) => {
    setOkMsg(msg);
    window.setTimeout(() => setOkMsg(""), 5000);
  }, []);

  const appendToDocument = useCallback((fragment: string) => {
    const html = fragment.trim().startsWith("<") ? fragment : markdownToHtml(fragment);
    setContent((c) => appendHtmlFragment(c, html));
    setContentFormat("html");
    if (panel !== "editor") setPanel("editor");
  }, [panel]);

  const load = useCallback(async () => {
    try {
      const res = await api.getWorkspaceDocument(draftId);
      setDoc(res.document);
      const raw = res.document.content || "";
      const fmt =
        (res.document.content_format as "html" | "markdown") ||
        (raw.trim().startsWith("<") ? "html" : "markdown");
      const { html } = normalizeContent(raw, fmt);
      setContent(html);
      setContentFormat("html");
      setTitle(res.document.title || "");
      setStatus(res.document.status || "draft");
      setMatterId(res.document.matter_id || "");
      setVersions(res.versions || []);
      setComments(res.comments || []);
      lastSaved.current = {
        content: html,
        status: res.document.status || "draft",
        title: res.document.title || "",
        matterId: res.document.matter_id || "",
      };
      setErr("");
      if (res.versions.length >= 2) {
        setCompareB(res.versions[0].version_number);
        setCompareA(res.versions[1]?.version_number ?? 1);
      }
      const [ins, ci] = await Promise.all([
        api.getWorkspaceInsights(draftId),
        api.getWorkspaceClauseIntel(draftId).catch(() => null),
      ]);
      setInsights(ins);
      if (ci) setClauseIntel(ci);
      api.getCollaborationHub(draftId).then((h) => setPendingChanges(h.pending_changes || 0)).catch(() => {});
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load document");
    }
  }, [draftId]);

  const applyDocumentFromServer = (document: api.WorkspaceDocument) => {
    const { html } = normalizeContent(
      document.content || "",
      (document.content_format as "html" | "markdown") || "html"
    );
    setContent(html);
    setContentFormat("html");
    setDoc(document);
    lastSaved.current.content = html;
    api.getCollaborationHub(draftId).then((h) => setPendingChanges(h.pending_changes || 0)).catch(() => {});
  };

  useEffect(() => {
    if (draftId) load();
    api.listMatters().then((r) => setMatters(r.matters || [])).catch(() => {});
    api.draftLock(draftId).catch(() => {});
    const iv = setInterval(() => {
      api.draftPresenceHeartbeat(draftId).then((p) => setPresence(p.editors || [])).catch(() => {});
    }, 12000);
    return () => {
      clearInterval(iv);
      api.draftUnlock(draftId).catch(() => {});
    };
  }, [draftId, load]);

  useEffect(() => {
    api.listClauses("", clauseTag).then((r) => setClauses(r.clauses || [])).catch(() => {});
  }, [clauseTag]);

  useEffect(() => {
    if (!matterId) {
      setMatterVars({});
      return;
    }
    api
      .draftingMatterVariables(matterId)
      .then((r) => setMatterVars(r.variables || {}))
      .catch(() => setMatterVars({}));
  }, [matterId]);

  useEffect(() => {
    if (doc && isDocumentEmpty(content) && !templateOpen) {
      setTemplateOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only truly blank documents
  }, [doc?.draft_id]);

  const save = useCallback(
    async (summary = "Autosave") => {
      if (!draftId) return;
      setBusy(true);
      try {
        const { document, billing } = await api.saveWorkspaceContent(draftId, {
          content,
          content_format: contentFormat,
          matter_id: matterId,
          title,
          status,
          change_summary: summary,
        });
        setDoc(document);
        if (billing && (billing as { billed?: boolean }).billed) {
          setOkMsg(
            `Billing logged — ${(billing as { units_logged?: number }).units_logged ?? 0.25} hr`
          );
        }
        lastSaved.current = { content, status, title, matterId };
        const fresh = await api.getWorkspaceDocument(draftId);
        setVersions(fresh.versions || []);
        const [ins, ci] = await Promise.all([
          api.getWorkspaceInsights(draftId),
          api.getWorkspaceClauseIntel(draftId).catch(() => null),
        ]);
        setInsights(ins);
        if (ci) setClauseIntel(ci);
        setErr("");
        if (summary === "Manual save") showOk("Document saved");
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed");
      } finally {
        setBusy(false);
      }
    },
    [draftId, content, contentFormat, status, title, matterId, showOk]
  );

  useEffect(() => {
    if (!doc) return;
    const dirty =
      content !== lastSaved.current.content ||
      status !== lastSaved.current.status ||
      title !== lastSaved.current.title ||
      matterId !== lastSaved.current.matterId;
    if (!dirty) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => save("Autosave"), 5000);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [content, status, title, matterId, doc, save]);

  const onStatusChange = async (ns: string) => {
    setBusy(true);
    try {
      const { document, litigation_sync } = await api.transitionWorkspaceLifecycle(draftId, ns);
      setStatus(document.status);
      setDoc(document);
      lastSaved.current.status = document.status;
      if (litigation_sync && (litigation_sync as { ok?: boolean }).ok) {
        showOk("Synced to Litigation — court order linked");
      }
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Status change failed");
    } finally {
      setBusy(false);
    }
  };

  const autofill = async () => {
    if (!matterId) {
      setErr("Select a matter first");
      return;
    }
    setBusy(true);
    try {
      const { document, variables } = await api.autofillWorkspaceDocument(draftId);
      const { html } = normalizeContent(
        document.content || "",
        (document.content_format as "html" | "markdown") || "markdown"
      );
      setContent(html);
      setContentFormat("html");
      setDoc(document);
      lastSaved.current.content = html;
      setErr("");
      showOk(`Autofilled: ${Object.keys(variables).filter((k) => variables[k]).join(", ") || "matter fields"}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Autofill failed");
    } finally {
      setBusy(false);
    }
  };

  const runReview = async () => {
    setBusy(true);
    try {
      const [r, ci] = await Promise.all([
        api.reviewWorkspaceDocument(draftId),
        api.getWorkspaceClauseIntel(draftId),
      ]);
      setReview(r);
      setClauseIntel(ci);
      setPanel("review");
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Review failed");
    } finally {
      setBusy(false);
    }
  };

  const runCompare = async () => {
    setBusy(true);
    try {
      const r = await api.compareWorkspaceVersionsV3(draftId, compareA, compareB);
      setDiffHtml(r.diff_html || "");
      setSideBySide(r.side_by_side_html || "");
      setPanel("versions");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setBusy(false);
    }
  };

  const applyTemplate = (id: LegalTemplateId, replace: boolean) => {
    const html = getLegalTemplateHtml(id, matterVars);
    if (replace) {
      setContent(html);
      setContentFormat("html");
      lastSaved.current.content = html;
    } else {
      appendToDocument(html);
    }
    setPanel("editor");
    showOk(`Applied ${id.replace(/_/g, " ")} template`);
  };

  const runCopilot = async (cmd: string, instruction?: string) => {
    setBusy(true);
    try {
      const sel = editorRef.current?.getSelectedText() || selectionText;
      const ctx = sel.trim() ? sel : content.slice(0, 3000);
      const instr =
        instruction ??
        (sel.trim() ? `${copilotInstr}\n\n[Selected text]:\n${sel}` : copilotInstr);
      const { result } = await api.copilotWorkspaceDocument(draftId, cmd, ctx, instr);
      if (result?.trim()) {
        const html = result.trim().startsWith("<") ? result : markdownToHtml(result);
        appendToDocument(html);
        setErr("");
        showOk("Copilot suggestion added to document");
        return html;
      }
      return null;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Copilot failed");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const copilotChat = (instruction: string) => runCopilot("chat", instruction);

  const download = async (format: string, sig = false) => {
    setBusy(true);
    try {
      const { blob, filename } = await api.exportWorkspaceDocumentV3(draftId, format, {
        watermark,
        signature_blocks: sig,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setErr("");
      showOk(`Downloaded ${filename}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  const insertClause = (text: string, tag?: string) => {
    const safe = text.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    appendToDocument(`<p>${safe}</p>`);
    showOk("Clause inserted");
    if (tag) setRecentClauses((r) => [tag, ...r.filter((x) => x !== tag)].slice(0, 5));
  };

  const insertExecution = () => {
    appendToDocument(EXECUTION_BLOCK_HTML);
    showOk("Execution block added");
  };

  const insertClauseByTag = (tag: string) => {
    const c = clauses.find((x) => x.clause_tag === tag);
    if (c) insertClause(c.clause_text_content, tag);
    else setClauseTag(tag);
  };

  if (!doc && !err) {
    return <p className="p-8 text-slate-500">Loading document…</p>;
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        eyebrow="Drafting Studio"
        title={title || doc?.title || "Document"}
        subtitle={`${formatDocumentType(doc?.document_type)} · Version ${doc?.version_count || 1} · ${liveStats.words} words`}
      >
        <Button type="button" size="md" disabled={busy} onClick={() => save("Manual save")}>
          Save
        </Button>
      </PageHeader>

      <div className="drafting-editor-chrome">
        <div className="drafting-editor-chrome__row">
          <div className="drafting-editor-chrome__group">
            <span className="drafting-editor-chrome__label">Navigate</span>
            <Link href="/drafting" className="text-sm font-medium text-blue-700 no-underline hover:underline">
              Control center
            </Link>
            <Link
              href={`/drafting/${draftId}/review`}
              className="text-sm font-medium text-blue-700 no-underline hover:underline"
            >
              Review
            </Link>
          </div>
          <div className="drafting-editor-chrome__group">
            <span className="drafting-editor-chrome__label">Matter</span>
            <select
              className="le-input !min-h-[36px] !py-1.5 text-sm max-w-[160px]"
              value={matterId}
              onChange={(e) => setMatterId(e.target.value)}
            >
              <option value="">No matter</option>
              {matters.map((m) => (
                <option key={m.matter_id} value={m.matter_id}>
                  {m.matter_name || m.client_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setTemplateOpen(true)}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white font-medium hover:bg-slate-50"
            >
              Templates
            </button>
            <button
              type="button"
              onClick={autofill}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
            >
              Autofill
            </button>
          </div>
          <div className="drafting-editor-chrome__group">
            <span className="drafting-editor-chrome__label">Workflow</span>
            <select
              className="le-input !min-h-[36px] !py-1.5 text-sm capitalize"
              value={status}
              onChange={(e) => onStatusChange(e.target.value)}
            >
              {WORKFLOW.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {matterId && (
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const b = await api.logDraftBillingSession(draftId, true);
                    if ((b as { billed?: boolean }).billed) showOk("Billing entry logged (0.25 hr)");
                    else showOk(String((b as { reason?: string }).reason || "Billing skipped (cooldown)"));
                    setErr("");
                  } catch (e) {
                    setErr(e instanceof Error ? e.message : "Billing failed");
                  } finally {
                    setBusy(false);
                  }
                }}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
              >
                Log time
              </button>
            )}
            <button
              type="button"
              onClick={runReview}
              disabled={busy}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
            >
              AI review
            </button>
          </div>
          <div className="drafting-editor-chrome__group">
            <span className="drafting-editor-chrome__label">Export</span>
            <button
              type="button"
              onClick={() => download("pdf")}
              disabled={busy}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
            >
              PDF
            </button>
            <button
              type="button"
              onClick={() => download("pdf", true)}
              disabled={busy}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
            >
              PDF + signatures
            </button>
            <button
              type="button"
              onClick={() => download("docx")}
              disabled={busy}
              className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
            >
              Word
            </button>
            <input
              className="le-input !min-h-[36px] !py-1.5 text-xs w-28"
              placeholder="Watermark"
              value={watermark}
              onChange={(e) => setWatermark(e.target.value)}
            />
          </div>
          <div className="drafting-view-tabs ml-auto">
            {(["editor", "preview", "review", "versions", "tools"] as Panel[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => {
                  if (p === "review" && !review) runReview();
                  else setPanel(p);
                }}
                className={panel === p ? "is-active" : ""}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {presence.length > 0 && (
        <p className="px-4 py-1 text-xs text-slate-500 border-b bg-amber-50">
          Editing: {presence.map((p) => p.user_name).join(", ")}
        </p>
      )}
      {insights && (
        <div className="px-4 lg:px-6 py-2.5 flex flex-wrap gap-4 text-xs text-slate-600 border-b border-slate-200/80 bg-slate-50/60 items-center">
          <span className="font-semibold text-slate-800 tabular-nums">
            Health {Math.max(0, 100 - Number(insights.risk_score ?? 50))}%
          </span>
          <span>{liveStats.words || String(insights.word_count)} words</span>
          <span>~{liveStats.pages} pg</span>
          <span>v{String(insights.version_count)}</span>
          {selectionText && (
            <span className="text-navy bg-blue-50 px-2 py-0.5 rounded">
              Selection: {selectionText.slice(0, 40)}
              {selectionText.length > 40 ? "…" : ""}
            </span>
          )}
          {(insights.missing_sections as string[])?.length > 0 && (
            <span className="text-amber-700">
              {(insights.missing_sections as string[]).slice(0, 3).join(" · ")}
            </span>
          )}
          <button type="button" className="text-navy underline" onClick={() => setSidebar("health")}>
            Open health center
          </button>
        </div>
      )}

      {okMsg && (
        <p className="mx-4 mt-2 text-green-800 text-sm bg-green-50 border border-green-200 rounded-lg px-4 py-2">{okMsg}</p>
      )}
      {err && (
        <p className="mx-4 mt-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-2">{err}</p>
      )}

      <DocumentTemplatePicker
        open={templateOpen}
        onClose={() => setTemplateOpen(false)}
        onApply={applyTemplate}
        documentType={doc?.document_type}
      />

      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        <DocumentOutlinePanel
          sections={outline}
          onSelect={(id) => {
            if (panel !== "editor") setPanel("editor");
            window.setTimeout(() => editorRef.current?.scrollToSection(id), 80);
          }}
        />
        <div className="flex-1 flex flex-col min-h-0 p-3 gap-3 overflow-hidden min-w-0">
          <input
            className="font-serif text-lg font-semibold w-full border-b border-slate-200 focus:border-slate-400 outline-none py-2 bg-transparent shrink-0 text-slate-900 placeholder:text-slate-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label="Document title"
            placeholder="Document title"
          />
          {panel === "editor" && (
            <div className="flex flex-col flex-1 min-h-0 gap-0">
              <MatterContextBar
                matterId={matterId}
                variables={matterVars}
                busy={busy}
                onAutofill={autofill}
                onInsertVariable={(token) => appendToDocument(`<p>${token}</p>`)}
              />
              {selectionText && (
                <div className="flex flex-wrap gap-1 px-2 py-1.5 bg-blue-50 border-b text-[10px] items-center">
                  <span className="text-slate-600 shrink-0">Rewrite selection:</span>
                  {[
                    ["rewrite_formal", "Formal"],
                    ["shorten", "Shorten"],
                    ["expand", "Expand"],
                    ["explain_clause", "Explain"],
                  ].map(([cmd, label]) => (
                    <button
                      key={cmd}
                      type="button"
                      disabled={busy}
                      className="px-2 py-0.5 border rounded bg-white text-navy"
                      onClick={() => runCopilot(cmd, `Apply to selection only: ${selectionText}`)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              <LegalDocumentEditor
                ref={editorRef}
                documentTitle={title}
                headerText={docHeader || title}
                footerText={docFooter}
                onHeaderChange={setDocHeader}
                onFooterChange={setDocFooter}
                content={content}
                contentFormat={contentFormat}
                onOutlineChange={setOutline}
                onStatsChange={setLiveStats}
                onSelectionChange={setSelectionText}
                onChange={(html) => {
                  setContent(html);
                  setContentFormat("html");
                }}
              />
            </div>
          )}
          {panel === "preview" && (
            <div className="overflow-y-auto le-scroll legal-a4-canvas py-6 px-4 flex-1">
              <div
                className="legal-a4-page mx-auto legal-page-body prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: content }}
              />
            </div>
          )}
          {panel === "review" && !review && (
            <div className="flex flex-col items-center justify-center flex-1 border rounded-xl p-8 bg-white text-sm text-slate-600 gap-3">
              <p>No review yet. Run AI review to see risk flags and recommendations.</p>
              <button type="button" onClick={runReview} disabled={busy} className="px-4 py-2 bg-navy text-white rounded-lg">
                Run AI review
              </button>
            </div>
          )}
          {panel === "review" && review && (
            <div className="overflow-y-auto le-scroll space-y-3 text-sm border rounded-xl p-4 bg-white">
              <p className="font-semibold text-navy">{String(review.summary || "")}</p>
              <p>Risk score: {String(review.clause_risk_score ?? "—")}/100</p>
              {clauseIntel && (
                <>
                  <h3 className="font-medium">Clause recommendations (firm library)</h3>
                  <ul className="list-disc pl-5">
                    {((clauseIntel.recommendations as Array<{ clause: string; explanation: string; source?: string }>) || []).map(
                      (m, i) => (
                        <li key={i}>
                          {m.clause} [{m.source}]: {m.explanation}
                        </li>
                      )
                    )}
                  </ul>
                </>
              )}
              <h3 className="font-medium">Risk flags</h3>
              <ul className="list-disc pl-5">
                {((review.risk_flags as Array<{ level: string; message: string }>) || []).map((r, i) => (
                  <li key={i}>
                    [{r.level}] {r.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {panel === "versions" && (
            <div className="space-y-3 overflow-y-auto le-scroll border rounded-xl p-4 bg-white">
              <ul className="text-sm space-y-2">
                {versions.map((v) => (
                  <li key={v.version_number} className="flex justify-between border-b py-1">
                    <span>
                      v{v.version_number} — {v.change_summary}
                    </span>
                    <button
                      type="button"
                      className="text-xs text-navy underline"
                      onClick={async () => {
                        setBusy(true);
                        try {
                          const { document } = await api.restoreWorkspaceVersion(draftId, v.version_number);
                          const { html } = normalizeContent(
                            document.content || "",
                            (document.content_format as "html" | "markdown") || "markdown"
                          );
                          setContent(html);
                          setContentFormat("html");
                          lastSaved.current.content = html;
                          await load();
                          showOk(`Restored version ${v.version_number}`);
                          setPanel("editor");
                        } catch (e) {
                          setErr(e instanceof Error ? e.message : "Restore failed");
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Restore
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2 items-center flex-wrap">
                <input type="number" className="w-16 border rounded px-2 py-1 text-sm" value={compareA} onChange={(e) => setCompareA(Number(e.target.value))} />
                <span>vs</span>
                <input type="number" className="w-16 border rounded px-2 py-1 text-sm" value={compareB} onChange={(e) => setCompareB(Number(e.target.value))} />
                <button type="button" onClick={runCompare} className="px-3 py-1 border rounded-lg text-sm">
                  Compare
                </button>
              </div>
              {sideBySide && (
                <div className="overflow-auto max-h-64" dangerouslySetInnerHTML={{ __html: sideBySide }} />
              )}
              {diffHtml && (
                <div className="overflow-auto max-h-48 border rounded p-2" dangerouslySetInnerHTML={{ __html: diffHtml }} />
              )}
            </div>
          )}
          {panel === "tools" && (
            <div className="overflow-y-auto le-scroll border rounded-xl">
              <DraftingLegacyTools />
            </div>
          )}
        </div>

        <aside className="w-full md:w-[22rem] shrink-0 border-t md:border-t-0 md:border-l border-slate-200/90 bg-white flex flex-col min-h-0 max-h-[48vh] md:max-h-none shadow-sm">
          <div className="flex border-b border-slate-200 overflow-x-auto le-scroll bg-slate-50/80 p-1 gap-0.5">
            {(
              [
                ["health", "Health"],
                ["track", pendingChanges > 0 ? `Track (${pendingChanges})` : "Track"],
                ["approval", "Approve"],
                ["precedents", "Precedent"],
                ["toc", "TOC"],
                ["clauses", "Clauses"],
                ["copilot", "Copilot"],
                ["comments", "Notes"],
                ["links", "Links"],
              ] as [Sidebar, string][]
            ).map(([s, label]) => (
              <button
                key={s}
                type="button"
                onClick={() => setSidebar(s)}
                className={`shrink-0 px-2.5 py-2 text-[10px] font-semibold rounded-lg transition-colors ${
                  sidebar === s
                    ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-hidden flex flex-col min-h-0 text-sm">
            {sidebar === "health" && (
              <div className="flex-1 overflow-y-auto le-scroll">
                <DocumentHealthPanel
                  insights={insights}
                  clauseIntel={clauseIntel}
                  onInsertClause={insertClauseByTag}
                  onAddExecution={insertExecution}
                  onFilingCheck={async () => {
                    try {
                      const r = await api.getFilingReadiness(draftId);
                      const score = Number(r.filing_readiness_score ?? 0);
                      showOk(`Filing readiness: ${score}/100`);
                      setErr("");
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Filing check failed");
                    }
                  }}
                />
              </div>
            )}
            {sidebar === "track" && (
              <div className="flex-1 overflow-hidden flex flex-col min-h-0">
                <TrackChangesPanel
                  draftId={draftId}
                  selectionText={selectionText}
                  onResolved={(d) => d && applyDocumentFromServer(d)}
                  onErr={setErr}
                  onOk={showOk}
                />
              </div>
            )}
            {sidebar === "approval" && (
              <ApprovalWorkflowPanel
                draftId={draftId}
                status={status}
                onStatusChange={setStatus}
                onErr={setErr}
                onOk={showOk}
              />
            )}
            {sidebar === "precedents" && (
              <PrecedentIntelPanel
                draftId={draftId}
                onInsert={(t) => appendToDocument(t)}
                onErr={setErr}
                onOk={showOk}
              />
            )}
            {sidebar === "toc" && (
              <AnnexureTocPanel
                draftId={draftId}
                onDocumentUpdate={applyDocumentFromServer}
                onErr={setErr}
                onOk={showOk}
              />
            )}
            {sidebar === "clauses" && (
              <ClauseLibraryDrawer
                clauses={clauses}
                tag={clauseTag}
                onTagChange={setClauseTag}
                onInsert={(t) => insertClause(t, clauseTag)}
                recent={recentClauses}
              />
            )}
            {sidebar === "copilot" && (
              <div className="flex-1 flex flex-col min-h-0">
                <CopilotChatPanel
                  busy={busy}
                  onSend={copilotChat}
                  onApply={(html) => {
                    const h = html.trim().startsWith("<") ? html : markdownToHtml(html);
                    appendToDocument(h);
                    showOk("Inserted into document");
                  }}
                />
                <div className="p-2 border-t flex flex-wrap gap-1">
                  {COPILOT_CMDS.map(([cmd, label]) => (
                    <button
                      key={cmd}
                      type="button"
                      onClick={() => runCopilot(cmd)}
                      disabled={busy}
                      className="px-2 py-1 text-[10px] border rounded bg-white hover:bg-slate-100"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {sidebar === "links" && (
              <div className="flex-1 overflow-y-auto le-scroll p-3">
                <DraftLitigationPanel draftId={draftId} matterId={matterId} />
              </div>
            )}
            {sidebar === "comments" && (
              <div className="flex-1 overflow-y-auto le-scroll p-3">
                <textarea className="w-full border rounded-lg p-2 text-xs h-16 mb-2" value={newComment} onChange={(e) => setNewComment(e.target.value)} />
                <button
                  type="button"
                  onClick={async () => {
                    if (!newComment.trim()) {
                      setErr("Enter a comment");
                      return;
                    }
                    setBusy(true);
                    try {
                      await api.addWorkspaceComment(draftId, newComment);
                      setNewComment("");
                      const f = await api.getWorkspaceDocument(draftId);
                      setComments(f.comments || []);
                      showOk("Comment posted");
                      setErr("");
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Comment failed");
                    } finally {
                      setBusy(false);
                    }
                  }}
                  className="w-full py-1.5 bg-navy text-white rounded-lg text-xs mb-2"
                >
                  Post comment
                </button>
                {comments.map((c) => (
                  <div key={c.comment_id} className="mb-2 p-2 border rounded-lg bg-white text-xs">
                    <p className="font-medium">{c.author_name}</p>
                    <p>{c.body}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
