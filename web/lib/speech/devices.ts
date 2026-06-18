import type { AudioInputDevice, MicTestResult } from "./types";

const STORAGE_KEY = "legalease_mic_device_id";

const BT_RE =
  /bluetooth|airpods|buds|earbuds|headset|hands-?free|hfp|wh-|wf-|boat|rockerz|jbl|sony|bose|galaxy buds|pixel buds/i;
const COMM_RE = /^communications\s*[-–]/i;

export function getSavedMicDeviceId(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(STORAGE_KEY) || "";
}

export function saveMicDeviceId(deviceId: string) {
  if (typeof window === "undefined") return;
  if (deviceId) localStorage.setItem(STORAGE_KEY, deviceId);
  else localStorage.removeItem(STORAGE_KEY);
}

function iconForDevice(rawLabel: string, isBluetooth: boolean): string {
  if (isBluetooth) return "🎧";
  if (/usb|external|condenser|yeti|blue/i.test(rawLabel)) return "Mic";
  if (/array|realtek|internal|built/i.test(rawLabel)) return "Mic";
  return "Mic";
}

function formatDisplayLabel(raw: string, isBluetooth: boolean): string {
  const icon = iconForDevice(raw, isBluetooth);
  let name = raw
    .replace(/^Default\s*[-–]\s*/i, "")
    .replace(/^Communications\s*[-–]\s*/i, "")
    .trim();
  if (!name) name = raw.trim() || "Microphone";
  if (COMM_RE.test(raw)) return `📞 ${name} (Communications)`;
  if (/^default\s/i.test(raw)) return `⚙ ${name} (System default)`;
  return `${icon} ${name}`;
}

/** Brief getUserMedia unlocks device labels in Chrome/Edge. */
export async function ensureMicPermission(): Promise<{
  granted: boolean;
  permission: "granted" | "denied" | "prompt" | "unknown";
}> {
  if (!navigator.mediaDevices?.getUserMedia) {
    return { granted: false, permission: "unknown" };
  }
  let permission: "granted" | "denied" | "prompt" | "unknown" = "unknown";
  try {
    const perm = await navigator.permissions?.query({
      name: "microphone" as PermissionName,
    });
    if (perm?.state === "granted") permission = "granted";
    else if (perm?.state === "denied") permission = "denied";
    else if (perm?.state === "prompt") permission = "prompt";
  } catch {
    /* optional */
  }

  let stream: MediaStream | null = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    permission = "granted";
    return { granted: true, permission };
  } catch (e) {
    if (e instanceof DOMException && e.name === "NotAllowedError") {
      return { granted: false, permission: "denied" };
    }
    return { granted: false, permission };
  } finally {
    stream?.getTracks().forEach((t) => t.stop());
  }
}

export async function enumerateAudioInputs(): Promise<AudioInputDevice[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];

  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    const inputs = all.filter((d) => d.kind === "audioinput");
    const seen = new Set<string>();

    const list: AudioInputDevice[] = [];
    for (const d of inputs) {
      if (!d.deviceId || d.deviceId === "default") continue;
      if (seen.has(d.deviceId)) continue;
      seen.add(d.deviceId);

      const raw = d.label?.trim() || "";
      const isBluetooth = BT_RE.test(raw);
      const isCommunications = COMM_RE.test(raw);
      const isDefault = /^default\s/i.test(raw);

      list.push({
        deviceId: d.deviceId,
        label: raw || `Microphone (${d.deviceId.slice(0, 8)}…)`,
        displayLabel: formatDisplayLabel(raw || "Microphone", isBluetooth),
        groupId: d.groupId || "",
        isBluetooth,
        isCommunications,
        isDefault,
      });
    }

    list.sort((a, b) => {
      if (a.isBluetooth !== b.isBluetooth) return a.isBluetooth ? -1 : 1;
      if (a.isCommunications !== b.isCommunications) return a.isCommunications ? -1 : 1;
      return a.label.localeCompare(b.label);
    });

    return list;
  } catch {
    return [];
  }
}

/** Bluetooth output without matching input — headset may be in stereo-only mode. */
export async function detectBluetoothOutputOnly(): Promise<{
  outputOnly: boolean;
  bluetoothOutputs: string[];
  bluetoothInputs: string[];
}> {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return { outputOnly: false, bluetoothOutputs: [], bluetoothInputs: [] };
  }
  const all = await navigator.mediaDevices.enumerateDevices();
  const outputs = all
    .filter((d) => d.kind === "audiooutput" && BT_RE.test(d.label || ""))
    .map((d) => d.label || "Bluetooth output");
  const inputs = all
    .filter((d) => d.kind === "audioinput" && BT_RE.test(d.label || ""))
    .map((d) => d.label || "Bluetooth input");

  return {
    outputOnly: outputs.length > 0 && inputs.length === 0,
    bluetoothOutputs: outputs,
    bluetoothInputs: inputs,
  };
}

export function buildAudioConstraints(deviceId?: string): MediaTrackConstraints {
  if (deviceId) {
    return {
      deviceId: { exact: deviceId },
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    };
  }
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
}

export async function acquireMicStream(deviceId?: string): Promise<MediaStream> {
  const id = (deviceId || getSavedMicDeviceId()).trim();
  return navigator.mediaDevices.getUserMedia({
    audio: buildAudioConstraints(id || undefined),
  });
}

/** Prefer communications / Bluetooth input when available. */
export function pickBestDeviceId(
  devices: AudioInputDevice[],
  preferredId?: string
): string {
  if (preferredId && devices.some((d) => d.deviceId === preferredId)) {
    return preferredId;
  }
  const bt = devices.find((d) => d.isBluetooth);
  if (bt) return bt.deviceId;
  const comm = devices.find((d) => d.isCommunications);
  if (comm) return comm.deviceId;
  return devices[0]?.deviceId || "";
}

export function getStreamMicLabel(stream: MediaStream): string {
  const track = stream.getAudioTracks()[0];
  return track?.label?.trim() || "Default microphone";
}

export async function listAudioInputDeviceLabels(): Promise<string[]> {
  const list = await enumerateAudioInputs();
  return list.map((d) => d.displayLabel);
}

let activeProbeStream: MediaStream | null = null;

export function stopActiveProbeStream() {
  activeProbeStream?.getTracks().forEach((t) => t.stop());
  activeProbeStream = null;
}

/** Stop streams, re-request permission, re-enumerate (for refresh button / hot-plug). */
export async function forceRefreshAudioDevices(): Promise<AudioInputDevice[]> {
  stopActiveProbeStream();
  await ensureMicPermission();
  return enumerateAudioInputs();
}

/** Live test selected mic — open stream and sample ~1.5s peak level. */
export async function testMicDeviceHealth(
  deviceId: string,
  sampleMs = 1500
): Promise<MicTestResult> {
  stopActiveProbeStream();

  const devices = await enumerateAudioInputs();
  const meta = devices.find((d) => d.deviceId === deviceId);
  const label = meta?.displayLabel || meta?.label || "Microphone";

  let stream: MediaStream;
  try {
    stream = await acquireMicStream(deviceId);
    activeProbeStream = stream;
  } catch (e) {
    const msg =
      e instanceof DOMException && e.name === "NotAllowedError"
        ? "Microphone permission denied."
        : e instanceof Error
          ? e.message
          : "Could not open microphone.";
    return {
      deviceId,
      label,
      streamActive: false,
      peakLevel: 0,
      health: "silent",
      message: `❌ ${msg}`,
    };
  }

  const { sampleMicLevelRms } = await import("./audioLevel");
  const peak = await sampleMicLevelRms(stream, sampleMs);

  if (!deviceId) {
    stopActiveProbeStream();
  }

  let health: MicTestResult["health"] = "silent";
  let message = "❌ No signal from selected microphone.";
  if (peak >= 0.08) {
    health = "ok";
    message = `✓ Hearing microphone (${Math.round(peak * 100)}% level)`;
  } else if (peak >= 0.02) {
    health = "low";
    message = `⚠ Very low audio (${Math.round(peak * 100)}%) — speak louder or check Windows input volume.`;
  }

  return {
    deviceId,
    label,
    streamActive: stream.active,
    peakLevel: peak,
    health,
    message,
  };
}

export function subscribeDeviceChanges(onChange: () => void): () => void {
  if (!navigator.mediaDevices?.addEventListener) return () => {};
  const handler = () => onChange();
  navigator.mediaDevices.addEventListener("devicechange", handler);
  return () => navigator.mediaDevices.removeEventListener("devicechange", handler);
}
