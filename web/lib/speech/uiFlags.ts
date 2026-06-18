import type { MicSignalHealth, SpeechUiStatus } from "@/lib/speech/types";

/** Coarse lifecycle for UI (maps many SpeechUiStatus values). */
export type SpeechLifecyclePhase =
  | "idle"
  | "starting"
  | "listening"
  | "processing"
  | "stopping";

export type SpeechUiFlags = {
  phase: SpeechLifecyclePhase;
  isListening: boolean;
  isBusy: boolean;
  isStopping: boolean;
  showWaveform: boolean;
  micInteractive: boolean;
};

export function mapStatusToPhase(status: SpeechUiStatus): SpeechLifecyclePhase {
  switch (status) {
    case "checking":
      return "starting";
    case "listening":
    case "hearing":
    case "live":
      return "listening";
    case "stopping":
      return "stopping";
    case "transcribing":
    case "polishing":
      return "processing";
    default:
      return "idle";
  }
}

/** Single source of truth for speech UI flags — derive from hook `status`. */
export function deriveSpeechUiFlags(
  status: SpeechUiStatus,
  options?: { refreshingDevices?: boolean; signalHealth?: MicSignalHealth }
): SpeechUiFlags {
  const refreshing = options?.refreshingDevices ?? false;
  const phase = mapStatusToPhase(status);
  const isStopping = status === "stopping";
  const isListening =
    status === "listening" || status === "hearing" || status === "live";
  const isBusy =
    status === "checking" ||
    isStopping ||
    status === "transcribing" ||
    status === "polishing" ||
    refreshing;
  const showWaveform =
    isListening ||
    isBusy ||
    isStopping ||
    options?.signalHealth === "testing";

  return {
    phase,
    isListening: isListening || isStopping,
    isBusy,
    isStopping,
    showWaveform,
    micInteractive: !isBusy,
  };
}
