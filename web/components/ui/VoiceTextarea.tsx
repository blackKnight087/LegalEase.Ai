"use client";

import { useCallback } from "react";
import SpeechMicButton from "@/components/ui/SpeechMicButton";
import SpeechPanel from "@/components/speech/SpeechPanel";
import { useSpeechToText } from "@/hooks/useSpeechToText";

type Props = {
  value: string;
  onChange: (value: string) => void;
  lang?: string;
  polishOnStop?: boolean;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
  rows?: number;
  id?: string;
  matterId?: string;
};

export default function VoiceTextarea({
  value,
  onChange,
  lang = "English",
  polishOnStop = false,
  disabled,
  className = "",
  placeholder,
  rows = 4,
  id,
  matterId,
}: Props) {
  const appendTranscript = useCallback(
    (text: string) => {
      const sep = value.trim() ? (value.endsWith(" ") ? "" : " ") : "";
      onChange(`${value}${sep}${text}`);
    },
    [onChange, value]
  );

  const speech = useSpeechToText({
    language: lang,
    polishOnStop,
    matterId,
    getBaseText: () => value,
    onLiveUpdate: onChange,
    onTranscript: appendTranscript,
  });

  const showPanel =
    speech.status !== "idle" ||
    speech.isListening ||
    speech.isBusy ||
    !!speech.error;

  return (
    <div className="space-y-2">
      {showPanel && (
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
      )}
      <div className="flex gap-2 items-start">
        <textarea
          id={id}
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || speech.isBusy}
          placeholder={
            speech.isListening
              ? "Speak now — words appear here live…"
              : placeholder
          }
          className={`flex-1 border rounded-lg px-3 py-2 text-sm resize-y ${className}`}
        />
        <SpeechMicButton
          isListening={speech.isListening}
          isBusy={speech.isBusy}
          isStopping={speech.isStopping}
          disabled={disabled}
          onClick={speech.toggle}
          title={
            polishOnStop
              ? "Dictate (legal polish on stop)"
              : "Dictate with live captions"
          }
        />
      </div>
    </div>
  );
}
