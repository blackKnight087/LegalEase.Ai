"use client";

import VoiceMicIcon from "@/components/ui/VoiceMicIcon";

type Props = {
  isListening: boolean;
  isBusy?: boolean;
  isStopping?: boolean;
  disabled?: boolean;
  onClick: () => void;
  title?: string;
  className?: string;
};

export default function SpeechMicButton({
  isListening,
  isBusy,
  isStopping,
  disabled,
  onClick,
  title = "Voice input",
  className = "",
}: Props) {
  const busy = Boolean(isBusy && !isListening);
  const active = isListening && !isStopping;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isBusy}
      title={title}
      aria-label={title}
      aria-pressed={isListening}
      className={`shrink-0 rounded-xl border px-3 py-3 disabled:opacity-50 transition-colors flex items-center justify-center ${
        isListening
          ? "border-red-400 bg-red-50 text-red-700"
          : "border-slate-300 bg-white hover:bg-slate-50"
      } ${className}`}
    >
      <VoiceMicIcon active={active} busy={busy || Boolean(isStopping)} size={22} />
    </button>
  );
}
