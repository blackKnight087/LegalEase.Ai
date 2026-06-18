"use client";

import { useState } from "react";

type FeedbackHandler = () => void | Promise<void> | Promise<unknown>;

type Props = {
  onUp?: FeedbackHandler;
  onDown?: FeedbackHandler;
  compact?: boolean;
};

export default function ThumbsFeedback({ onUp, onDown, compact }: Props) {
  const [busy, setBusy] = useState(false);

  const run = async (fn?: FeedbackHandler) => {
    if (!fn || busy) return;
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "mt-1" : "mt-2"}`}>
      <button
        type="button"
        disabled={busy}
        title="Relevant"
        onClick={() => run(onUp)}
        className="px-2 py-0.5 rounded border bg-white hover:bg-emerald-50 text-sm disabled:opacity-50"
      >
        👍
      </button>
      <button
        type="button"
        disabled={busy}
        title="Low priority"
        onClick={() => run(onDown)}
        className="px-2 py-0.5 rounded border bg-white hover:bg-red-50 text-sm disabled:opacity-50"
      >
        👎
      </button>
    </div>
  );
}
