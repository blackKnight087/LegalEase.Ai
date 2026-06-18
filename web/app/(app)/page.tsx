"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ChatMobileControls from "@/components/chat/ChatMobileControls";
import ChatViewport from "@/components/chat/ChatViewport";
import InputDock from "@/components/chat/InputDock";
import ModePills from "@/components/chat/ModePills";
import EngineStatusBar from "@/components/chat/EngineStatusBar";
import KbScopeHealth from "@/components/chat/KbScopeHealth";
import RetrievalDebugPanel from "@/components/chat/RetrievalDebugPanel";
import SuggestionPills from "@/components/chat/SuggestionPills";
import { useAuth } from "@/components/providers/AuthProvider";
import { useChat } from "@/hooks/useChat";
import * as api from "@/lib/api";

const LANGS = ["English", "Hindi", "Tamil", "Marathi", "Bengali", "Gujarati"];
const MATTER_STORAGE = "legalease_active_matter";

function ChatPageInner() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState("knowledge_base");
  const [lang, setLang] = useState("English");
  const [matters, setMatters] = useState<api.Matter[]>([]);
  const [matterId, setMatterId] = useState("");

  useEffect(() => {
    api.listMatters().then((r) => {
      const list = r.matters || [];
      setMatters(list);
      const fromUrl = searchParams.get("matter") || "";
      const saved =
        typeof window !== "undefined" ? localStorage.getItem(MATTER_STORAGE) : "";
      const pick =
        fromUrl && list.some((m) => m.matter_id === fromUrl)
          ? fromUrl
          : saved && list.some((m) => m.matter_id === saved)
            ? saved
            : list[0]?.matter_id || "";
      setMatterId(pick);
    });
  }, [searchParams]);

  useEffect(() => {
    if (matterId && typeof window !== "undefined") {
      localStorage.setItem(MATTER_STORAGE, matterId);
    }
  }, [matterId]);

  const {
    messages,
    loading,
    loadingThread,
    followUps,
    error,
    sendMessage,
    regenerateAt,
    lastAssistantInteractionId,
    threadId,
    threadAttachment,
    attachFile,
    attachBusy,
    clearAttachment,
    retrievalDebug,
    debugBusy,
    runRetrievalDebug,
  } = useChat(mode, lang, setMode, setLang, matterId, setMatterId);

  const lastUserQuery = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === "user") return messages[i].content;
    }
    return "";
  })();

  const escalateToOpenLaw = useCallback(
    (query: string) => {
      setMode("web_search");
      if (query.trim()) {
        setTimeout(() => sendMessage(query.trim()), 100);
      }
    },
    [sendMessage, setMode]
  );

  const prevModeRef = useRef(mode);
  const lastAssistantRef = useRef<{
    interactionId?: string;
    mode?: string;
    query?: string;
  }>({});

  useEffect(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m?.role === "assistant" && m.interactionId && !m.streaming) {
        let userQuery = "";
        for (let j = i - 1; j >= 0; j--) {
          if (messages[j]?.role === "user") {
            userQuery = messages[j].content;
            break;
          }
        }
        lastAssistantRef.current = {
          interactionId: m.interactionId,
          mode,
          query: userQuery,
        };
        break;
      }
    }
  }, [messages, mode]);

  useEffect(() => {
    const prev = prevModeRef.current;
    if (prev === mode) return;
    const kbModes = new Set(["knowledge_base", "kb"]);
    const webModes = new Set(["open_law", "web_search", "deep_case", "hybrid"]);
    const last = lastAssistantRef.current;
    if (
      kbModes.has(prev) &&
      webModes.has(mode) &&
      last.interactionId &&
      last.mode &&
      kbModes.has(last.mode)
    ) {
      api
        .learningSignal({
          signal: "mode_switch",
          interaction_id: last.interactionId,
          metadata: {
            from_mode: prev,
            to_mode: mode,
            query: last.query || "",
          },
        })
        .catch(() => {});
    }
    prevModeRef.current = mode;
  }, [mode]);

  const lastIsAssistant =
    messages.length > 0 && messages[messages.length - 1]?.role === "assistant";

  const showMatterSelect = mode === "deep_case" || mode === "hybrid";

  return (
    <div className="flex flex-col h-full min-h-0 max-w-chat mx-auto w-full">
      {/* Mobile: ~72px toolbar — chat gets the rest */}
      <div className="lg:hidden shrink-0">
        <ChatMobileControls
          mode={mode}
          onModeChange={setMode}
          membership={user?.membership || "Free"}
          lang={lang}
          onLangChange={setLang}
          matterId={matterId}
          onMatterChange={setMatterId}
          matters={matters}
        />
      </div>

      {/* Desktop controls */}
      <div className="hidden lg:block shrink-0">
        <header className="px-6 pt-4 pb-2 flex grid grid-cols-[1fr_auto] gap-4 items-center">
          <div className="min-w-0">
            <h1 className="font-serif text-xl font-bold text-navy m-0">
              LegalEase Assistant
            </h1>
            <p className="text-[0.68rem] text-slate-500 m-0 mt-0.5 line-clamp-2">
              Memory + adaptive learning on — remembers your style and improves from feedback
            </p>
          </div>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="text-xs border border-slate-300 rounded-lg px-3 py-1 bg-white"
            aria-label="Language"
          >
            {LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </header>
        <div className="px-6 pb-2 space-y-2">
          <EngineStatusBar matterId={matterId} />
          <KbScopeHealth matterId={matterId} mode={mode} />
          {mode !== "knowledge_base" && (
            <RetrievalDebugPanel
              debug={retrievalDebug}
              busy={debugBusy}
              onRunDebug={
                lastUserQuery
                  ? () => runRetrievalDebug(lastUserQuery)
                  : undefined
              }
            />
          )}
          <ModePills
            mode={mode}
            onChange={setMode}
            membership={user?.membership || "Free"}
          />
          {showMatterSelect && (
            <div className="flex items-center gap-2 text-sm">
              <label className="text-slate-600 shrink-0">
                Case file (Matter KB scope):
              </label>
              <select
                className="flex-1 max-w-md border border-slate-300 rounded-lg px-3 py-1 bg-white"
                value={matterId}
                onChange={(e) => setMatterId(e.target.value)}
              >
                <option value="">Select a matter…</option>
                {matters.map((m) => (
                  <option key={m.matter_id} value={m.matter_id}>
                    {m.matter_name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {loadingThread && (
        <div className="shrink-0 mx-2 sm:mx-6 mb-1 text-xs sm:text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 sm:px-4 sm:py-2">
          Loading saved chat…
        </div>
      )}

      {error && (
        <div className="shrink-0 mx-2 sm:mx-6 mb-1 text-xs sm:text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5 sm:px-4 sm:py-2">
          {error}
        </div>
      )}

      {messages.length === 0 && !loading && !loadingThread && (
        <div className="hidden lg:block shrink-0 mx-6 mb-2 text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
          Use <strong>📎</strong> below to attach a PDF or image to <em>this chat only</em>, or
          upload to the global Knowledge Base under <strong>Documents</strong>. Open{" "}
          <strong>Saved Chats</strong> in the sidebar to continue a past thread.
        </div>
      )}

      <ChatViewport
        messages={messages}
        loading={loading || loadingThread}
        mode={mode}
        threadId={threadId || ""}
        onRegenerateAt={regenerateAt}
        onEscalateToOpenLaw={escalateToOpenLaw}
      />

      {lastIsAssistant && !loading && (
        <SuggestionPills
          items={followUps}
          onSelect={sendMessage}
          disabled={loading}
          interactionId={lastAssistantInteractionId}
          mode={mode}
        />
      )}

      <InputDock
        onSend={sendMessage}
        onAttach={attachFile}
        attachment={threadAttachment}
        onRemoveAttachment={clearAttachment}
        attachBusy={attachBusy}
        disabled={loading}
        lang={lang}
      />
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full text-slate-500 text-sm">
          Loading chat…
        </div>
      }
    >
      <ChatPageInner />
    </Suspense>
  );
}
