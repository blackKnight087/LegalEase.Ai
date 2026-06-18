"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";

const FEEDBACK_TAGS: { id: string; label: string }[] = [
  { id: "too_long", label: "Too long" },
  { id: "too_short", label: "Too short" },
  { id: "wrong_section", label: "Wrong section" },
  { id: "not_in_documents", label: "Not in my documents" },
  { id: "good_structure", label: "Good structure" },
  { id: "good_citations", label: "Good citations" },
  { id: "wrong_tone", label: "Wrong tone" },
  { id: "missed_follow_up", label: "Missed follow-up" },
];

function storageKey(interactionId?: string, chatId?: string, messageKey?: string) {
  return `le_fb:${messageKey || interactionId || chatId || "unknown"}`;
}

export default function MessageFeedback({
  interactionId,
  chatId,
  threadId,
  messageKey,
  answerText = "",
  userQuery = "",
  mode = "knowledge_base",
  tagOptions,
  onRegenerate,
}: {
  interactionId?: string;
  chatId?: string;
  threadId?: string;
  messageKey?: string;
  answerText?: string;
  userQuery?: string;
  mode?: string;
  /** Override default feedback tags for a specific surface. */
  tagOptions?: { id: string; label: string }[];
  onRegenerate?: () => void;
}) {
  const feedbackTags = tagOptions?.length ? tagOptions : FEEDBACK_TAGS;
  const [sent, setSent] = useState<"up" | "down" | "copy" | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [detail, setDetail] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [showEditDiff, setShowEditDiff] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [coachMsg, setCoachMsg] = useState("");
  const [copied, setCopied] = useState(false);

  const key = storageKey(interactionId, chatId, messageKey);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.sessionStorage.getItem(key);
    if (saved === "up" || saved === "down" || saved === "copy") setSent(saved);
  }, [key]);

  if (!interactionId && !chatId && !messageKey) return null;
  const canPersist = Boolean(interactionId || chatId);

  const persist = (choice: "up" | "down" | "copy") => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(key, choice);
    }
  };

  const toggleTag = (id: string) => {
    setSelectedTags((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id].slice(0, 5)
    );
  };

  const feedbackMeta = {
    mode,
    thread_id: threadId,
    query: userQuery,
    answer_preview: answerText.slice(0, 500),
  };

  const sendUp = async () => {
    if (busy || sent) return;
    setBusy(true);
    setError("");
    setCoachMsg("");
    setSent("up");
    if (!canPersist) {
      persist("up");
      setBusy(false);
      return;
    }
    persist("up");
    try {
      const res = await api.learningFeedback({
        signal: "thumbs_up",
        interaction_id: interactionId,
        chat_id: chatId,
        metadata: userQuery ? { ...feedbackMeta, user_query: userQuery } : feedbackMeta,
      });
      if (!res?.ok) {
        if (typeof window !== "undefined") {
          window.sessionStorage.removeItem(key);
        }
        setSent(null);
        setError(String(res?.error || "Feedback not saved — retry"));
        return;
      }
      if ((res as { queued?: boolean }).queued) {
        setCoachMsg("Saved — tuning runs in the background.");
      }
    } catch (e) {
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem(key);
      }
      setSent(null);
      const msg = e instanceof Error ? e.message : "Feedback failed";
      setError(
        /401|unauthorized|not authenticated/i.test(msg)
          ? "Please log in again to save feedback"
          : /500|internal server/i.test(msg)
            ? "Server busy — feedback may still be queued; try again or keep chatting"
          : /fetch|reach api|connection|timeout|abort/i.test(msg)
            ? "Server unreachable — try again in a moment."
            : msg.slice(0, 120)
      );
    } finally {
      setBusy(false);
    }
  };

  const sendDownWithDetail = async () => {
    if (busy || sent) return;
    const comment = detail.trim();
    if (!comment && selectedTags.length === 0) {
      setError("Add a short note or pick at least one tag.");
      return;
    }
    setBusy(true);
    setError("");
    setCoachMsg("");
    setSent("down");
    try {
      const res = await api.learningFeedback({
        signal: "thumbs_down",
        interaction_id: interactionId,
        chat_id: chatId,
        comment,
        tags: selectedTags,
        metadata: feedbackMeta,
      });
      if (!res?.ok) {
        setSent(null);
        setError("Feedback not saved — retry");
        return;
      }
      persist("down");
      setShowDetail(false);
      const coach = res.coach as { message?: string } | undefined;
      setCoachMsg(coach?.message || "Noted — we'll use this to improve future answers.");
    } catch (e) {
      setSent(null);
      const msg = e instanceof Error ? e.message : "Feedback failed";
      setError(msg.slice(0, 120));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    if (!answerText || busy) return;
    setBusy(true);
    setError("");
    try {
      await navigator.clipboard.writeText(answerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      if (!sent) {
        await api.learningFeedback({
          signal: "copy",
          interaction_id: interactionId,
          chat_id: chatId,
          metadata: { mode, query: userQuery },
        });
        setSent("copy");
        persist("copy");
      }
      setShowEditDiff(true);
      setEditedText(answerText);
    } catch {
      setError("Could not copy text");
    } finally {
      setBusy(false);
    }
  };

  const submitEditDiff = async () => {
    const edited = editedText.trim();
    if (!edited || edited === answerText.trim()) {
      setShowEditDiff(false);
      return;
    }
    setBusy(true);
    try {
      await api.learningSignal({
        signal: "edit_diff",
        interaction_id: interactionId,
        chat_id: chatId,
        metadata: {
          query: userQuery,
          original: answerText.slice(0, 2000),
          edited: edited.slice(0, 2000),
          mode,
        },
      });
      setShowEditDiff(false);
      setCoachMsg("Your edited version was saved for style learning.");
    } catch {
      setError("Could not save edited version");
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async () => {
    if (busy || !onRegenerate) return;
    setBusy(true);
    setError("");
    try {
      await api.learningFeedback({
        signal: "regenerate",
        interaction_id: interactionId,
        chat_id: chatId,
        metadata: feedbackMeta,
      });
    } catch {
      /* Regenerate should still work even if the learning signal fails */
    }
    try {
      onRegenerate();
    } catch {
      setError("Could not regenerate — try sending your question again");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 border-t border-slate-100 pt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[0.65rem] text-slate-400 uppercase tracking-wide">
          {sent === "up"
            ? "Thanks — answer stored for learning"
            : sent === "down"
              ? "Thanks — sent to tuning pipeline"
              : sent === "copy"
                ? "Copied — saved as positive signal"
                : "Help improve answers"}
        </span>
        <button
          type="button"
          disabled={busy || !!sent}
          onClick={sendUp}
          aria-pressed={sent === "up"}
          className={`text-sm px-2 py-0.5 rounded border transition-colors ${
            sent === "up"
              ? "bg-emerald-100 text-emerald-800 border-emerald-300"
              : "border-transparent hover:bg-slate-100"
          }`}
          title="Good answer"
        >
          👍
        </button>
        <button
          type="button"
          disabled={busy || !!sent}
          onClick={() => {
            setShowDetail(true);
            setError("");
          }}
          aria-pressed={sent === "down"}
          className={`text-sm px-2 py-0.5 rounded border transition-colors ${
            sent === "down"
              ? "bg-red-100 text-red-800 border-red-300"
              : "border-transparent hover:bg-slate-100"
          }`}
          title="Poor answer"
        >
          👎
        </button>
        {answerText ? (
          <button
            type="button"
            disabled={busy}
            onClick={handleCopy}
            className="text-[0.68rem] px-2 py-0.5 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        ) : null}
        {onRegenerate ? (
          <button
            type="button"
            disabled={busy}
            onClick={handleRegenerate}
            className="text-[0.68rem] px-2 py-0.5 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
          >
            Regenerate
          </button>
        ) : null}
      </div>

      {showDetail && !sent && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 space-y-2">
          <p className="text-xs font-semibold text-navy">What went wrong?</p>
          <div className="flex flex-wrap gap-1.5">
            {feedbackTags.map((tag) => (
              <button
                key={tag.id}
                type="button"
                onClick={() => toggleTag(tag.id)}
                className={`text-[0.62rem] px-2 py-1 rounded-full border ${
                  selectedTags.includes(tag.id)
                    ? "bg-navy text-white border-navy"
                    : "bg-white border-slate-300 text-slate-600 hover:border-navy"
                }`}
              >
                {tag.label}
              </button>
            ))}
          </div>
          <textarea
            className="w-full border border-slate-200 rounded-lg px-2.5 py-2 text-xs min-h-[72px] resize-y bg-white"
            placeholder="Optional details…"
            value={detail}
            onChange={(e) => setDetail(e.target.value)}
            maxLength={500}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={sendDownWithDetail}
              className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs font-semibold disabled:opacity-50"
            >
              Submit feedback
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setShowDetail(false);
                setDetail("");
                setSelectedTags([]);
                setError("");
              }}
              className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {showEditDiff && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 space-y-2">
          <p className="text-xs font-semibold text-navy">
            Edited after copying? Paste your improved version (optional — style learning only).
          </p>
          <textarea
            className="w-full border border-slate-200 rounded-lg px-2.5 py-2 text-xs min-h-[80px] resize-y bg-white"
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            maxLength={4000}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={submitEditDiff}
              className="px-3 py-1.5 bg-navy text-white rounded-lg text-xs font-semibold disabled:opacity-50"
            >
              Save edit for learning
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setShowEditDiff(false)}
              className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {coachMsg && (sent === "down" || sent === "copy") && (
        <p className="text-[0.65rem] text-emerald-700">{coachMsg}</p>
      )}
      {error ? <span className="text-[0.65rem] text-red-500">{error}</span> : null}
    </div>
  );
}
