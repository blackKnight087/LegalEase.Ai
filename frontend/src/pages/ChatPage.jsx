import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import * as api from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import ChatHeader from "../components/ChatHeader.jsx";
import ChatViewport from "../components/ChatViewport.jsx";
import InputDock from "../components/InputDock.jsx";
import SuggestionPills from "../components/SuggestionPills.jsx";

const LANGS = ["English", "Hindi", "Tamil", "Marathi", "Bengali", "Gujarati"];

function formatSources(similar_cases, web_sources) {
  const parts = [];
  if (similar_cases?.[0]) parts.push(`Source: ${similar_cases[0].filename || "document"}`);
  if (web_sources?.[0]?.href) parts.push(web_sources[0].title || "Web");
  return parts.join(" · ") || null;
}

export default function ChatPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [mode, setMode] = useState("knowledge_base");
  const [lang, setLang] = useState("English");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [followUps, setFollowUps] = useState([]);
  const [error, setError] = useState("");
  const [attachment, setAttachment] = useState(null);
  const [attachOpen, setAttachOpen] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);

  useEffect(() => {
    const onNew = () => {
      setMessages([]);
      setFollowUps([]);
      setInput("");
      setError("");
      setAttachment(null);
    };
    window.addEventListener("legalease:new-chat", onNew);
    return () => window.removeEventListener("legalease:new-chat", onNew);
  }, []);

  useEffect(() => {
    const s = location.state?.session;
    if (s?.question) {
      setMessages([
        { role: "user", content: s.question },
        { role: "assistant", content: s.preview || "…" },
      ]);
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  const sendMessage = useCallback(
    async (text) => {
      const prompt = (text ?? input).trim();
      if (!prompt || loading) return;
      setError("");
      setInput("");
      setFollowUps([]);
      const userMsg = { role: "user", content: prompt };
      const prior = messages;
      setMessages([...prior, userMsg]);
      setLoading(true);
      try {
        const data = await api.sendChat({
          message: prompt,
          mode,
          lang,
          history: prior.map((m) => ({ role: m.role, content: m.content })),
          attachment: attachment
            ? { filename: attachment.filename, text: attachment.text, chars: attachment.chars }
            : null,
        });
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.content,
            sourcesLabel: formatSources(data.similar_cases, data.web_sources),
          },
        ]);
        setFollowUps(data.follow_ups || []);
      } catch (e) {
        setError(e.message);
        setMessages(prior);
      } finally {
        setLoading(false);
      }
    },
    [input, loading, messages, mode, lang, attachment]
  );

  const onAttach = async (file) => {
    setOcrLoading(true);
    try {
      setAttachment(await api.uploadOcr(file));
      setAttachOpen(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setOcrLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full justify-between overflow-hidden relative min-w-0">
      <div className="shrink-0 flex items-center gap-3 pr-4">
        <div className="flex-1 min-w-0">
          <ChatHeader mode={mode} onModeChange={setMode} membership={user?.membership} />
        </div>
        <select
          value={lang}
          onChange={(e) => setLang(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white shrink-0 mb-1"
          title="Response language"
        >
          {LANGS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
      </div>
      {error && (
        <div className="mx-6 px-4 py-2 text-sm text-red-700 bg-red-50 rounded-lg border border-red-100 shrink-0">
          {error}
        </div>
      )}
      <ChatViewport messages={messages} loading={loading} />
      <SuggestionPills items={followUps} onPick={(l) => sendMessage(l)} disabled={loading} />
      <InputDock
        value={input}
        onChange={setInput}
        onSubmit={() => sendMessage()}
        disabled={loading}
        attachment={attachment}
        onAttach={onAttach}
        onClearAttach={() => setAttachment(null)}
        attachOpen={attachOpen}
        setAttachOpen={setAttachOpen}
        ocrLoading={ocrLoading}
      />
    </div>
  );
}
