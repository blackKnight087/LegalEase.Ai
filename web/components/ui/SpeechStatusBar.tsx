"use client";

type Props = {
  micLabel?: string | null;
  audioLevel?: number;
  isListening?: boolean;
  isBusy?: boolean;
  engine?: "browser" | "server" | null;
  error?: string | null;
  hint?: string | null;
  availableMics?: string[];
};

export default function SpeechStatusBar({
  micLabel,
  audioLevel = 0,
  isListening,
  isBusy,
  engine,
  error,
  hint,
  availableMics = [],
}: Props) {
  if (!error && !hint && !isListening && !isBusy && !micLabel) return null;

  const levelPct = Math.round(Math.min(100, audioLevel * 100));
  const hearing = audioLevel > 0.04;

  return (
    <div
      className={`rounded-lg border px-3 py-2 text-xs space-y-1.5 ${
        error ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50"
      }`}
      role="status"
    >
      {micLabel && (
        <p className={`m-0 ${error ? "text-red-800" : "text-slate-700"}`}>
          <span className="font-semibold">Microphone:</span> {micLabel}
          {engine === "browser" && (
            <span className="ml-2 text-emerald-700">· live captions</span>
          )}
          {engine === "server" && (
            <span className="ml-2 text-blue-700">· server Whisper</span>
          )}
        </p>
      )}

      {isListening && engine === "browser" && (
        <p className="m-0 text-emerald-700">
          Live captions active — words appear in the box as you speak.
        </p>
      )}

      {isListening && engine !== "browser" && (
        <div className="flex items-center gap-2">
          <div
            className="flex-1 h-2 rounded-full bg-slate-200 overflow-hidden"
            aria-label="Microphone input level"
          >
            <div
              className={`h-full transition-[width] duration-75 rounded-full ${
                hearing ? "bg-emerald-500" : "bg-amber-400"
              }`}
              style={{ width: `${Math.max(levelPct, hearing ? 8 : 2)}%` }}
            />
          </div>
          <span className={`shrink-0 ${hearing ? "text-emerald-700" : "text-amber-700"}`}>
            {hearing ? "Hearing you" : "Speak now…"}
          </span>
        </div>
      )}

      {isBusy && !isListening && (
        <p className="m-0 text-slate-600 animate-pulse">Processing speech…</p>
      )}

      {(error || hint) && (
        <p className={`m-0 ${error ? "text-red-700 font-medium" : "text-slate-600"}`}>
          {error || hint}
        </p>
      )}

      {availableMics.length > 1 && isListening && (
        <p className="m-0 text-[0.65rem] text-slate-500" title={availableMics.join(", ")}>
          {availableMics.length} mics detected — using active device above. Change default in
          Windows Sound settings if needed.
        </p>
      )}
    </div>
  );
}
