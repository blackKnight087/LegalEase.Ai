export type SpeechUiStatus =
  | "idle"
  | "checking"
  | "listening"
  | "hearing"
  | "live"
  | "stopping"
  | "transcribing"
  | "polishing"
  | "stopped"
  | "error"
  | "unsupported";

export type SpeechEngine = "hybrid" | "browser" | "server" | null;

export type MicSignalHealth = "unknown" | "ok" | "low" | "silent" | "testing";

export type AudioInputDevice = {
  deviceId: string;
  label: string;
  displayLabel: string;
  groupId: string;
  isBluetooth: boolean;
  isCommunications: boolean;
  isDefault: boolean;
};

export type MicTestResult = {
  deviceId: string;
  label: string;
  streamActive: boolean;
  peakLevel: number;
  health: MicSignalHealth;
  message: string;
};

export type MicDiagnosticResult = {
  permission: "granted" | "denied" | "prompt" | "unknown";
  hasDevice: boolean;
  streamActive: boolean;
  hasAudioSignal: boolean;
  browserSttAvailable: boolean;
  bluetoothOutputOnly: boolean;
  issues: string[];
  ok: boolean;
};

export type SpeechDebugInfo = {
  micLabel: string;
  deviceId: string;
  permission: string;
  browserStarted: boolean;
  browserResultCount: number;
  browserDisabled: boolean;
  noSpeechRetries: number;
  audioLevel: number;
  interimText: string;
  finalText: string;
  lastError: string;
  engine: string;
  blobSize: number;
  devices: Array<{ deviceId: string; label: string; groupId: string }>;
  signalHealth: string;
};
