import {
  acquireMicStream,
  detectBluetoothOutputOnly,
  ensureMicPermission,
  enumerateAudioInputs,
  getStreamMicLabel,
  pickBestDeviceId,
} from "./devices";
import { sampleMicLevelRms } from "./audioLevel";
import type { MicDiagnosticResult } from "./types";

function browserSttAvailable(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as Window & {
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
  };
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export async function runMicDiagnostics(
  deviceId?: string
): Promise<
  MicDiagnosticResult & { stream?: MediaStream; label?: string; peakLevel?: number }
> {
  const issues: string[] = [];
  let permission: MicDiagnosticResult["permission"] = "unknown";

  if (!navigator.mediaDevices?.getUserMedia) {
    issues.push("Microphone API not supported in this browser.");
    return {
      permission,
      hasDevice: false,
      streamActive: false,
      hasAudioSignal: false,
      browserSttAvailable: browserSttAvailable(),
      bluetoothOutputOnly: false,
      issues,
      ok: false,
    };
  }

  const perm = await ensureMicPermission();
  permission = perm.permission;
  if (!perm.granted) {
    issues.push("Microphone permission denied. Allow mic access for this site.");
    return {
      permission,
      hasDevice: false,
      streamActive: false,
      hasAudioSignal: false,
      browserSttAvailable: browserSttAvailable(),
      bluetoothOutputOnly: false,
      issues,
      ok: false,
    };
  }

  const inputs = await enumerateAudioInputs();
  const bt = await detectBluetoothOutputOnly();
  if (bt.outputOnly) {
    issues.push(
      "Bluetooth headset may be in stereo output-only mode. In Windows Sound settings, set your earbuds as the Default Communication Device, or reconnect in Hands-Free mode."
    );
  }

  const hasDevice = inputs.length > 0;
  if (!hasDevice) issues.push("No microphone devices found. Connect a mic and click Refresh.");

  const effectiveId = deviceId || pickBestDeviceId(inputs, deviceId);

  let stream: MediaStream | undefined;
  try {
    stream = await acquireMicStream(effectiveId || undefined);
    const streamActive =
      stream.active && stream.getAudioTracks().some((t) => t.readyState === "live");
    const label = getStreamMicLabel(stream);
    if (!streamActive) issues.push("Microphone stream is not active.");

    const peak = await sampleMicLevelRms(stream, 600);
    const hasAudioSignal = peak > 0.02;

    const browserStt = browserSttAvailable();
    if (!browserStt) {
      issues.push("Browser live captions unavailable — server transcription on stop.");
    }

    const ok = streamActive && hasDevice && permission !== "denied";
    return {
      permission,
      hasDevice,
      streamActive,
      hasAudioSignal,
      browserSttAvailable: browserStt,
      bluetoothOutputOnly: bt.outputOnly,
      issues,
      ok,
      stream,
      label,
      peakLevel: peak,
    };
  } catch (e) {
    if (e instanceof DOMException && e.name === "NotAllowedError") {
      permission = "denied";
      issues.push("Microphone permission denied.");
    } else if (e instanceof DOMException && e.name === "NotFoundError") {
      issues.push("Selected microphone not found. Click Refresh and pick another device.");
    } else {
      issues.push(e instanceof Error ? e.message : "Could not open microphone.");
    }
    stream?.getTracks().forEach((t) => t.stop());
    return {
      permission,
      hasDevice,
      streamActive: false,
      hasAudioSignal: false,
      browserSttAvailable: browserSttAvailable(),
      bluetoothOutputOnly: bt.outputOnly,
      issues,
      ok: false,
    };
  }
}
