"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { UiMessage, WebSourceItem } from "@/hooks/useChat";
import MessageFeedback from "@/components/chat/MessageFeedback";
import * as api from "@/lib/api";
import { stripInlineWebSourcesFromBody } from "@/lib/displayLabels";

function DwellTracker({
  interactionId,
  mode,
  answerLength,
}: {
  interactionId?: string;
  mode: string;
  answerLength: number;
}) {
  const startRef = useRef(Date.now());
  const sentRef = useRef(false);

  useEffect(() => {
    startRef.current = Date.now();
    sentRef.current = false;
    return () => {
      if (sentRef.current || !interactionId) return;
      const dwellMs = Date.now() - startRef.current;
      if (dwellMs < 1500) return;
      sentRef.current = true;
      api
        .learningSignal({
          signal: "dwell_time",
          interaction_id: interactionId,
          metadata: { dwell_ms: dwellMs, mode, answer_length: answerLength },
        })
        .catch(() => {});
    };
  }, [interactionId, mode, answerLength]);

  return null;
}

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex w-full justify-end">
      <div className="le-chat-bubble-user rounded-[22px] rounded-br-[6px] bg-gradient-to-br from-[#1e40af] to-[#2563eb] px-4 sm:px-6 py-3 sm:py-3.5 text-[15px] sm:text-[16px] leading-[1.65] text-white shadow-md">
        <p className="m-0 whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}

function SourceFooter({
  filename,
  section,
  fallback,
}: {
  filename?: string;
  section?: string;
  fallback?: string | null;
}) {
  if (!filename && !section && !fallback) return null;
  return (
    <div className="mt-6 border-t border-slate-200 pt-4">
      <div className="text-[0.7rem] font-bold uppercase tracking-widest text-amber-600">
        📄 Source
      </div>
      {filename ? (
        <p className="m-0 mt-1 text-[0.9rem] font-medium text-slate-700">{filename}</p>
      ) : null}
      {section ? (
        <p className="m-0 mt-0.5 text-[0.85rem] text-slate-500">Section {section}</p>
      ) : null}
      {!filename && !section && fallback ? (
        <p className="m-0 mt-1 text-[0.85rem] text-slate-500">{fallback}</p>
      ) : null}
    </div>
  );
}

function ReportExportButtons({
  content,
  mode,
  interactionId,
  userQuery,
}: {
  content: string;
  mode: string;
  interactionId?: string;
  userQuery?: string;
}) {
  const [busy, setBusy] = useState("");
  const body = (content || "").trim();
  const exportable =
    body.length > 400 &&
    (mode === "deep_case" ||
      /## Executive Summary|Jurisprudence|Document Intelligence/i.test(body));

  if (!exportable) return null;

  const download = async (format: "docx" | "pdf", clientSafe = false) => {
    setBusy(clientSafe ? "client" : format);
    try {
      const titleMatch = body.match(/^##?\s*(.+)$/m);
      const title = titleMatch?.[1]?.slice(0, 80) || "LegalEase Jurisprudence Report";
      const { blob, filename } = await api.exportResearchReport({
        content: body,
        title,
        format,
        client_safe: clientSafe,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      const signal = clientSafe ? "export_client_safe" : format === "pdf" ? "export_pdf" : "export_docx";
      await api.learningFeedback({
        signal,
        interaction_id: interactionId,
        metadata: { mode, query: userQuery, answer_preview: body.slice(0, 800) },
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
      <button
        type="button"
        disabled={!!busy}
        onClick={() => download("docx")}
        className="text-[0.68rem] font-semibold px-2.5 py-1 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
      >
        {busy === "docx" ? "Exporting…" : "Export DOCX"}
      </button>
      <button
        type="button"
        disabled={!!busy}
        onClick={() => download("pdf")}
        className="text-[0.68rem] font-semibold px-2.5 py-1 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
      >
        {busy === "pdf" ? "Exporting…" : "Export PDF"}
      </button>
      <button
        type="button"
        disabled={!!busy}
        onClick={() => download("docx", true)}
        className="text-[0.68rem] font-semibold px-2.5 py-1 rounded-lg border border-emerald-300 text-emerald-800 hover:bg-emerald-50 disabled:opacity-50"
      >
        {busy === "client" ? "Exporting…" : "Client-safe memo"}
      </button>
    </div>
  );
}

function WebSourcesList({ sources }: { sources?: WebSourceItem[] }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-4 border-t border-slate-100 pt-3 space-y-2">
      <div className="text-[0.7rem] font-bold uppercase tracking-widest text-slate-500">
        Web sources
      </div>
      {sources.slice(0, 6).map((s, i) => {
        const href = (s.href || "").trim();
        const isGrounding = /vertexaisearch\.cloud\.google\.com\/grounding-api-redirect/i.test(
          href
        );
        const label = (s.title || "").trim() || (isGrounding ? "Web source" : href);
        return (
        <div key={i} className="text-[0.82rem] text-slate-700 flex flex-wrap items-center gap-2">
          {href && !isGrounding ? (
            <a href={href} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
              {label}
            </a>
          ) : (
            <span className="text-slate-800">{label}</span>
          )}
          {s.trust_badge ? (
            <span className="text-[0.62rem] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
              {s.trust_badge}
            </span>
          ) : null}
          {s.freshness ? (
            <span className="text-[0.62rem] text-slate-500">{s.freshness}</span>
          ) : null}
        </div>
      );
      })}
    </div>
  );
}

function isNotFoundAnswer(text: string): boolean {
  const t = (text || "").toLowerCase();
  return (
    t.includes("couldn't find a clear reference") ||
    t.includes("could not find a clear reference") ||
    t.includes("not found in the uploaded") ||
    t.includes("not_found_in_kb") ||
    t.includes("knowledge base empty") ||
    (t.includes("upload") && t.includes("couldn't find"))
  );
}

function NotFoundEscalation({
  userQuery,
  interactionId,
  onEscalate,
}: {
  userQuery: string;
  interactionId?: string;
  onEscalate?: (query: string) => void;
}) {
  if (!onEscalate || !userQuery.trim()) return null;
  return (
    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50/80 p-3 space-y-2">
      <p className="text-xs font-semibold text-navy m-0">
        Not in your uploaded documents?
      </p>
      <p className="text-[0.65rem] text-slate-600 m-0">
        Search live Indian law on the web with Open Law Intelligence.
      </p>
      <button
        type="button"
        onClick={() => {
          if (interactionId) {
            api
              .learningSignal({
                signal: "mode_switch",
                interaction_id: interactionId,
                metadata: {
                  from_mode: "knowledge_base",
                  to_mode: "open_law",
                  query: userQuery,
                },
              })
              .catch(() => {});
          }
          onEscalate(userQuery);
        }}
        className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-700 text-white hover:bg-blue-800"
      >
        Search Open Law instead
      </button>
    </div>
  );
}

const EMPTY_ANSWER_FALLBACK =
  "The answer could not be displayed. Please try again, or switch to **Open Law** for statutory questions without uploaded acts.";

function stripSourceFromBody(text: string): string {
  const raw = (text || "").trim();
  if (!raw) return "";
  let stripped = raw.replace(/\n*\*{0,2}Source\*{0,2}\s*:[\s\S]*$/i, "").trim();
  stripped = stripInlineWebSourcesFromBody(stripped);
  return stripped || raw;
}

function AssistantCard({
  content,
  sources,
  sourceMeta,
  webSources,
  streaming,
  streamStatus = "",
  interactionId,
  chatId,
  threadId,
  messageKey,
  mode = "knowledge_base",
  userQuery = "",
  onRegenerate,
  onEscalateToOpenLaw,
}: {
  content: string;
  sources?: string | null;
  sourceMeta?: { filename?: string; section?: string };
  webSources?: WebSourceItem[];
  streaming?: boolean;
  streamStatus?: string;
  interactionId?: string;
  chatId?: string;
  threadId?: string;
  messageKey?: string;
  mode?: string;
  userQuery?: string;
  onRegenerate?: () => void;
  onEscalateToOpenLaw?: (query: string) => void;
}) {
  const body = stripSourceFromBody(content || "");
  const showFooter =
    sourceMeta?.filename ||
    sourceMeta?.section ||
    (sources && !webSources?.length && !/source:/i.test(body.slice(-400)));

  return (
    <div className="flex w-full justify-start">
      <div className="le-chat-bubble-assistant rounded-2xl sm:rounded-[22px] rounded-bl-md sm:rounded-bl-[6px] border border-slate-200 border-l-[3px] sm:border-l-[5px] border-l-amber-600 bg-white px-3 py-3 shadow-sm sm:shadow-md sm:px-7 sm:py-6">
        <div className="hidden sm:block mb-3 sm:mb-4 text-[0.65rem] sm:text-[0.72rem] font-bold uppercase tracking-[0.14em] text-amber-600">
          LEGALEASE CORE INTEL
        </div>
        <div className="kb-answer prose prose-slate max-w-none text-[15px] sm:text-[16px] leading-[1.75] sm:leading-[1.8] prose-headings:font-serif prose-headings:text-[#0f172a] prose-h1:mb-3 prose-h1:mt-0 prose-h1:text-[26px] prose-h1:font-bold prose-h2:mb-2 prose-h2:mt-5 prose-h2:text-[18px] prose-h2:font-semibold prose-h3:mt-4 prose-h3:mb-2 prose-h3:text-[16px] prose-p:my-2.5 prose-li:my-1 prose-strong:text-slate-800 prose-table:my-4 prose-th:bg-slate-100 prose-th:p-2 prose-td:p-2 prose-td:text-sm prose-table:border prose-th:border-slate-200 prose-td:border-slate-200">
          {body ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
          ) : streaming ? (
            <span className="inline-flex flex-col gap-1 text-slate-600">
              <span className="inline-flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse"
                  aria-hidden
                />
                <span className="animate-pulse font-medium text-slate-700">
                  {streamStatus?.replace(/\*+/g, "").trim() ||
                    (mode === "web_search" || mode === "open_law"
                      ? "Searching live legal sources…"
                      : mode === "deep_case" || mode === "hybrid"
                        ? "Searching your uploaded documents…"
                        : "Analyzing your documents…")}
                </span>
              </span>
            </span>
          ) : (
            <p className="m-0 text-slate-600">{EMPTY_ANSWER_FALLBACK}</p>
          )}
        </div>
        {showFooter ? (
          <SourceFooter
            filename={sourceMeta?.filename}
            section={sourceMeta?.section}
            fallback={sources}
          />
        ) : null}
        {!streaming && webSources?.length ? (
          <WebSourcesList sources={webSources} />
        ) : null}
        {!streaming && content && interactionId ? (
          <DwellTracker
            interactionId={interactionId}
            mode={mode}
            answerLength={body.length}
          />
        ) : null}
        {!streaming && content ? (
            <MessageFeedback
            interactionId={interactionId}
            chatId={chatId}
            threadId={threadId}
            messageKey={messageKey}
            answerText={body}
            userQuery={userQuery}
            mode={mode}
            onRegenerate={onRegenerate}
          />
        ) : null}
        {!streaming && content && mode === "knowledge_base" && isNotFoundAnswer(body) ? (
          <NotFoundEscalation
            userQuery={userQuery}
            interactionId={interactionId}
            onEscalate={onEscalateToOpenLaw}
          />
        ) : null}
        {!streaming && content ? (
          <ReportExportButtons
            content={body}
            mode={mode}
            interactionId={interactionId}
            userQuery={userQuery}
          />
        ) : null}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <div className="flex flex-col items-center justify-center px-3 py-6 sm:py-16 text-center">
      <h3 className="m-0 mb-2 sm:mb-3 font-serif text-lg sm:text-3xl font-bold text-[#0f172a]">
        Ask your legal question
      </h3>
      <p className="m-0 max-w-lg text-xs sm:text-[0.95rem] leading-relaxed text-slate-500 hidden sm:block">
        Query statutory provisions, synthesize evidence from your documents, or
        research live Indian law with cited sources.
      </p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex w-full justify-start">
      <div className="le-chat-bubble-assistant h-24 w-full animate-pulse rounded-[22px] border border-slate-200 bg-gradient-to-r from-slate-100 via-slate-200 to-slate-100" />
    </div>
  );
}

export default function ChatViewport({
  messages,
  loading,
  mode = "knowledge_base",
  threadId = "",
  onRegenerateAt,
  onEscalateToOpenLaw,
}: {
  messages: UiMessage[];
  loading: boolean;
  mode?: string;
  threadId?: string;
  onRegenerateAt?: (assistantIndex: number) => void;
  onEscalateToOpenLaw?: (query: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const showSkeleton =
    loading && messages.length > 0 && messages[messages.length - 1]?.role === "user";

  return (
    <div
      ref={ref}
      className="le-scroll flex min-h-0 flex-1 flex-col gap-3 sm:gap-5 overflow-y-auto overflow-x-hidden px-2 sm:px-6 py-2 sm:py-5"
    >
      {messages.length === 0 && !loading && <Hero />}
      {messages.map((m, i) => {
        if (m.role === "user") {
          return <UserBubble key={i} content={m.content} />;
        }
        let userQuery = "";
        for (let j = i - 1; j >= 0; j--) {
          if (messages[j]?.role === "user") {
            userQuery = messages[j].content;
            break;
          }
        }
        return (
          <AssistantCard
            key={i}
            content={m.content}
            sources={m.sourcesLabel}
            sourceMeta={m.sourceMeta}
            webSources={m.webSources}
            streaming={m.streaming}
            streamStatus={m.streamStatus}
            interactionId={m.interactionId}
            chatId={m.chatId}
            threadId={threadId}
            messageKey={`${m.chatId || ""}-${m.interactionId || ""}-${i}`}
            mode={mode}
            userQuery={userQuery}
            onRegenerate={onRegenerateAt ? () => onRegenerateAt(i) : undefined}
            onEscalateToOpenLaw={onEscalateToOpenLaw}
          />
        );
      })}
      {showSkeleton && <Skeleton />}
    </div>
  );
}
