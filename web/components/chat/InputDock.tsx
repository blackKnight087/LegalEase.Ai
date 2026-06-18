"use client";

import { FormEvent, useCallback, useRef, useState } from "react";
import SpeechMicButton from "@/components/ui/SpeechMicButton";
import SpeechPanel from "@/components/speech/SpeechPanel";
import { useSpeechToText } from "@/hooks/useSpeechToText";

export type ThreadAttachmentInfo = {
  filename: string;
  charCount?: number;
  preview?: string;
};

export default function InputDock({
  onSend,
  onAttach,
  attachment,
  onRemoveAttachment,
  attachBusy,
  disabled,
  lang = "English",
}: {
  onSend: (text: string) => void;
  onAttach?: (file: File) => void;
  attachment?: ThreadAttachmentInfo | null;
  onRemoveAttachment?: () => void;
  attachBusy?: boolean;
  disabled?: boolean;
  lang?: string;
}) {
  const [value, setValue] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const appendTranscript = useCallback((text: string) => {
    setValue((prev) => {
      const sep = prev.trim() ? (prev.endsWith(" ") ? "" : " ") : "";
      return `${prev}${sep}${text}`;
    });
  }, []);

  const speech = useSpeechToText({
    language: lang,
    getBaseText: () => value,
    onLiveUpdate: setValue,
    onTranscript: appendTranscript,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = value.trim();
    if (!t || disabled) return;
    setValue("");
    onSend(t);
  };

  const showSpeechPanel =
    speech.status !== "idle" ||
    speech.isListening ||
    speech.isBusy ||
    !!speech.error ||
    !!speech.micDeviceLabel;

  return (
    <div className="shrink-0 z-10 pt-1 pb-0.5 sm:pt-2 sm:pb-1 border-t border-slate-200/90 bg-[#f8fafc] lg:sticky lg:bottom-0">
      {attachment && (
        <div className="max-w-chat mx-auto w-full px-2 mb-2 flex items-center gap-2 text-xs bg-blue-50 border border-blue-200 rounded-lg py-2 px-3">
          <span className="text-blue-800 truncate flex-1" title={attachment.filename}>
            📎 {attachment.filename}
            {attachment.charCount
              ? ` · ${attachment.charCount.toLocaleString()} chars (this chat only)`
              : " · this chat only"}
          </span>
          {onRemoveAttachment && (
            <button
              type="button"
              onClick={onRemoveAttachment}
              className="text-blue-600 hover:text-red-600 shrink-0"
              aria-label="Remove attachment"
            >
              ✕
            </button>
          )}
        </div>
      )}
      {showSpeechPanel && (
        <div className="max-w-chat mx-auto w-full px-2 mb-2">
          <SpeechPanel
            status={speech.status}
            micLabel={speech.micDeviceLabel}
            audioLevel={speech.audioLevel}
            engine={speech.engine}
            error={speech.error}
            signalHealth={speech.signalHealth}
            signalMessage={speech.signalMessage}
            bluetoothWarning={speech.bluetoothWarning}
            refreshingDevices={speech.refreshingDevices}
            devices={speech.devices}
            selectedDeviceId={speech.selectedDeviceId}
            onSelectDevice={speech.selectDevice}
            onRefreshDevices={speech.refreshDevices}
            onToggle={speech.toggle}
            micDisabled={disabled}
            showDebug={speech.showDebug}
            debug={speech.debugInfo}
          />
        </div>
      )}
      <form
        onSubmit={submit}
        className="flex gap-1.5 sm:gap-2 items-end max-w-chat mx-auto w-full px-2 sm:px-2"
      >
        {onAttach && (
          <>
            <button
              type="button"
              disabled={disabled || attachBusy}
              onClick={() => fileRef.current?.click()}
              title="Attach PDF or image (this conversation only)"
              className="shrink-0 rounded-xl border border-slate-300 bg-white px-3 py-3 min-w-[44px] min-h-[44px] text-sm disabled:opacity-50 hover:bg-slate-50"
              aria-label="Attach file"
            >
              {attachBusy ? "…" : "📎"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf,image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onAttach(f);
                e.target.value = "";
              }}
            />
          </>
        )}
        <SpeechMicButton
          isListening={speech.isListening}
          isBusy={speech.isBusy}
          isStopping={speech.isStopping}
          disabled={disabled}
          onClick={speech.toggle}
          title={
            speech.isListening
              ? "Stop dictation"
              : "Start voice input (live captions + server backup)"
          }
        />
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e as unknown as FormEvent);
            }
          }}
          disabled={disabled || speech.isBusy}
          autoComplete="off"
          placeholder={
            speech.isListening
              ? "Listening…"
              : attachment
                ? "Ask about the file…"
                : "Ask a legal question…"
          }
          className="le-input flex-1 shadow-dock !min-h-[40px] sm:!min-h-[44px] !py-2 text-sm"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim() || speech.isBusy}
          className="shrink-0 rounded-xl bg-navy text-white px-4 sm:px-5 py-3 min-w-[44px] min-h-[44px] text-sm font-semibold disabled:opacity-50 hover:bg-slate-800"
          aria-label="Send"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
