"use client";

import type { SpeechDebugInfo, SpeechEngine, SpeechUiStatus, MicSignalHealth } from "@/lib/speech/types";
import type { AudioInputDevice } from "@/lib/speech/types";
import { deriveSpeechUiFlags } from "@/lib/speech/uiFlags";
import SpeechMicButton from "@/components/ui/SpeechMicButton";

function statusMessage(
  status: SpeechUiStatus,
  hearing: boolean,
  hasLiveText: boolean,
  signalHealth: MicSignalHealth,
  error: string | null,
  signalMessage: string | null
): string {
  if (error) return error;
  if (signalMessage && !error) return signalMessage;
  switch (status) {
    case "checking":
      return "Checking microphone…";
    case "listening":
      return hearing
        ? hasLiveText
          ? "🟢 Hearing you — live captions active"
          : "🟢 Hearing you — speak clearly"
        : signalHealth === "silent"
          ? "⚠ We cannot hear anything — check mic / Bluetooth mode"
          : "🔴 Listening… speak into your microphone";
    case "hearing":
      return "🟢 Hearing voice";
    case "live":
      return "🟢 Live captions — text updating as you speak";
    case "stopping":
      return "⏹ Finalizing transcript…";
    case "transcribing":
      return "⏳ Converting speech (server)…";
    case "polishing":
      return "⏳ Polishing legal text…";
    case "stopped":
      return "⏹ Recording stopped";
    default:
      return "Click the mic to speak";
  }
}

type Props = {
  status: SpeechUiStatus;
  micLabel: string | null;
  audioLevel: number;
  engine: SpeechEngine;
  error: string | null;
  signalHealth?: MicSignalHealth;
  signalMessage?: string | null;
  bluetoothWarning?: string | null;
  refreshingDevices?: boolean;
  devices: AudioInputDevice[];
  selectedDeviceId: string;
  onSelectDevice: (deviceId: string) => void;
  onRefreshDevices: () => void;
  onToggle: () => void;
  micDisabled?: boolean;
  debug?: SpeechDebugInfo | null;
  showDebug?: boolean;
};

export default function SpeechPanel({
  status,
  micLabel,
  audioLevel,
  engine,
  error,
  signalHealth = "unknown",
  signalMessage,
  bluetoothWarning,
  refreshingDevices,
  devices,
  selectedDeviceId,
  onSelectDevice,
  onRefreshDevices,
  onToggle,
  micDisabled,
  debug,
  showDebug,
}: Props) {
  const flags = deriveSpeechUiFlags(status, {
    refreshingDevices,
    signalHealth,
  });
  const { isListening, isBusy, isStopping, showWaveform } = flags;

  const levelPct = Math.round(Math.min(100, audioLevel * 100));
  const hearing = audioLevel > 0.025 || signalHealth === "ok";
  const hasLiveText =
    (debug?.interimText?.length ?? 0) > 0 || (debug?.finalText?.length ?? 0) > 0;
  const msg = statusMessage(
    status,
    hearing,
    hasLiveText,
    signalHealth,
    error,
    signalMessage ?? null
  );

  const showPanel =
    status !== "idle" ||
    !!micLabel ||
    !!error ||
    !!bluetoothWarning ||
    isListening ||
    isBusy ||
    devices.length > 0;

  if (!showPanel) return null;

  return (
    <div
      className={`rounded-xl border px-3 py-2.5 text-xs space-y-2 ${
        error ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50"
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <p className={`m-0 font-medium ${error ? "text-red-800" : "text-slate-800"}`}>
          {msg}
        </p>
        <SpeechMicButton
          isListening={isListening}
          isBusy={isBusy}
          isStopping={isStopping}
          disabled={micDisabled}
          onClick={onToggle}
          className="!py-1.5 !px-2.5"
        />
      </div>

      {bluetoothWarning && (
        <p className="m-0 text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5">
          {bluetoothWarning}
        </p>
      )}

      {micLabel && (
        <p className="m-0 text-slate-700">
          <span className="font-semibold">Connected:</span> {micLabel}
          {engine === "hybrid" && (
            <span className="ml-1 text-emerald-700">· record + live captions</span>
          )}
          {engine === "server" && (
            <span className="ml-1 text-blue-700">· server STT on stop</span>
          )}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-slate-600 shrink-0">Input device:</label>
        <select
          className="flex-1 min-w-[160px] text-xs border rounded-md px-2 py-1 bg-white"
          value={selectedDeviceId}
          onChange={(e) => onSelectDevice(e.target.value)}
          disabled={!flags.micInteractive}
        >
          <option value="">⚙ System default</option>
          {devices.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.displayLabel}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onRefreshDevices}
          disabled={!flags.micInteractive}
          className="text-xs px-2 py-1 border rounded-md bg-white hover:bg-slate-100 disabled:opacity-50"
          title="Stop streams, re-request permission, refresh device list (use after connecting Bluetooth)"
        >
          {refreshingDevices ? "…" : "↻ Refresh"}
        </button>
      </div>

      {devices.length === 0 && !refreshingDevices && (
        <p className="m-0 text-slate-500">
          No labeled mics yet — click Refresh after allowing microphone access.
        </p>
      )}

      {showWaveform && (
        <div className="space-y-1">
          <div className="flex items-end gap-0.5 h-10" aria-label="Microphone level">
            {Array.from({ length: 20 }).map((_, i) => {
              const phase = (Date.now() / 80 + i) % 20;
              const barBoost = hearing ? 0.25 + audioLevel * 0.75 : 0.06;
              const wave = 0.5 + 0.5 * Math.sin(i * 0.55 + phase * 0.3);
              const h = Math.max(3, barBoost * 36 * wave);
              return (
                <div
                  key={i}
                  className={`flex-1 rounded-sm transition-all duration-75 ${
                    hearing ? "bg-emerald-500" : "bg-amber-400"
                  }`}
                  style={{ height: `${h}px` }}
                />
              );
            })}
            <span
              className={`ml-2 shrink-0 self-center font-mono text-[0.65rem] ${
                hearing ? "text-emerald-700" : "text-amber-700"
              }`}
            >
              {levelPct}%
            </span>
          </div>
          {!hearing && isListening && !isStopping && (
            <p className="m-0 text-amber-700">
              ⚠ No voice detected yet — speak louder or switch mic above.
            </p>
          )}
        </div>
      )}

      {showDebug && debug && (
        <pre className="m-0 p-2 bg-slate-900 text-emerald-300 rounded text-[0.62rem] overflow-x-auto max-h-40">
          {JSON.stringify(debug, null, 2)}
        </pre>
      )}
    </div>
  );
}
