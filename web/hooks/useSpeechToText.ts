"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SpeechBrowserFallbackError,
  polishSpeechText,
  transcribeSpeech,
} from "@/lib/api";
import { BrowserCaptionSession } from "@/lib/speech/browserRecognition";
import { createAudioLevelMonitor } from "@/lib/speech/audioLevel";
import {
  acquireMicStream,
  detectBluetoothOutputOnly,
  ensureMicPermission,
  forceRefreshAudioDevices,
  getSavedMicDeviceId,
  getStreamMicLabel,
  pickBestDeviceId,
  saveMicDeviceId,
  stopActiveProbeStream,
  subscribeDeviceChanges,
  testMicDeviceHealth,
} from "@/lib/speech/devices";
import { runMicDiagnostics } from "@/lib/speech/diagnostics";
import { speechLog } from "@/lib/speech/logger";
import { MediaRecorderSession } from "@/lib/speech/mediaRecorder";
import { throttleMs, throttleRaf } from "@/lib/speech/throttle";
import type {
  AudioInputDevice,
  MicSignalHealth,
  SpeechDebugInfo,
  SpeechEngine,
  SpeechUiStatus,
} from "@/lib/speech/types";
import { deriveSpeechUiFlags, mapStatusToPhase } from "@/lib/speech/uiFlags";

export type { SpeechUiStatus, SpeechEngine };

const HEARING_THRESHOLD = 0.025;

function joinBaseAndSpeech(base: string, final: string, interim: string): string {
  const b = base.trim();
  const spoken = interim ? `${final} ${interim}`.trim() : final.trim();
  if (!spoken) return b;
  if (!b) return spoken;
  const sep = b.endsWith(" ") ? "" : " ";
  return `${b}${sep}${spoken}`;
}

function speechDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  if (localStorage.getItem("legalease_speech_debug") === "1") return true;
  return new URLSearchParams(window.location.search).has("speech_debug");
}

export function useSpeechToText(options: {
  language?: string;
  lang?: string;
  getBaseText?: () => string;
  onLiveUpdate?: (fullText: string) => void;
  onTranscript: (text: string) => void;
  polishOnStop?: boolean;
  matterId?: string;
  disabled?: boolean;
}) {
  const language = options.language ?? options.lang ?? "English";
  const { getBaseText, onLiveUpdate, onTranscript, polishOnStop, matterId, disabled } =
    options;

  const onLiveUpdateRef = useRef(onLiveUpdate);
  const getBaseTextRef = useRef(getBaseText);
  onLiveUpdateRef.current = onLiveUpdate;
  getBaseTextRef.current = getBaseText;

  const [status, setStatus] = useState<SpeechUiStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [micDeviceLabel, setMicDeviceLabel] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [engine, setEngine] = useState<SpeechEngine>(null);
  const [devices, setDevices] = useState<AudioInputDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [signalHealth, setSignalHealth] = useState<MicSignalHealth>("unknown");
  const [signalMessage, setSignalMessage] = useState<string | null>(null);
  const [bluetoothWarning, setBluetoothWarning] = useState<string | null>(null);
  const [refreshingDevices, setRefreshingDevices] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [debugInfo, setDebugInfo] = useState<SpeechDebugInfo | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorderSession | null>(null);
  const browserRef = useRef<BrowserCaptionSession | null>(null);
  const stopMonitorRef = useRef<(() => void) | null>(null);
  const dictationBaseRef = useRef("");
  const sessionFinalRef = useRef("");
  const sessionInterimRef = useRef("");
  const peakLevelRef = useRef(0);
  const audioLevelRef = useRef(0);
  const stoppingRef = useRef(false);
  const recordingRef = useRef(false);

  const speechFlags = useMemo(
    () =>
      deriveSpeechUiFlags(status, {
        refreshingDevices,
        signalHealth,
      }),
    [status, refreshingDevices, signalHealth]
  );
  const { isListening, isBusy, isStopping, phase: speechPhase } = speechFlags;

  const flushTextboxRef = useRef<() => void>(() => {});

  flushTextboxRef.current = () => {
    const display = joinBaseAndSpeech(
      dictationBaseRef.current,
      sessionFinalRef.current,
      sessionInterimRef.current
    );
    onLiveUpdateRef.current?.(display);
    speechLog("useSpeechToText.ts:flushTextbox", {
      message: "textbox_updated",
      data: { len: display.length, preview: display.slice(0, 80) },
    });
  };

  const scheduleTextboxUpdate = useMemo(
    () => throttleRaf(() => flushTextboxRef.current()),
    []
  );

  const scheduleLevelUpdate = useMemo(
    () =>
      throttleMs((level: number) => {
        audioLevelRef.current = level;
        setAudioLevel(level);
        if (level > peakLevelRef.current) peakLevelRef.current = level;

        if (!recordingRef.current || stoppingRef.current) return;

        if (level > HEARING_THRESHOLD) {
          setSignalHealth("ok");
          setSignalMessage("🟢 Hearing you");
          setStatus((s) =>
            s === "live" ? s : sessionInterimRef.current || sessionFinalRef.current ? "live" : "hearing"
          );
        } else if (sessionFinalRef.current || sessionInterimRef.current) {
          setStatus("live");
        } else {
          setSignalMessage("🔴 Listening…");
          setStatus((s) => (s === "live" ? "live" : "listening"));
        }
      }, 100),
    []
  );

  const releaseStreamInternal = useCallback(() => {
    stopMonitorRef.current?.();
    stopMonitorRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    browserRef.current?.abort();
    browserRef.current = null;
    audioLevelRef.current = 0;
    setAudioLevel(0);
    recordingRef.current = false;
  }, []);

  const loadDevices = useCallback(async (forcePermission = false) => {
    if (forcePermission) await ensureMicPermission();
    const list = await forceRefreshAudioDevices();
    setDevices(list);
    const bt = await detectBluetoothOutputOnly();
    if (bt.outputOnly) {
      setBluetoothWarning(
        "Bluetooth earbuds connected for audio only — enable Hands-Free / Headset mode in Windows Sound."
      );
    } else if (bt.bluetoothInputs.length > 0) {
      setBluetoothWarning(null);
    }
    return list;
  }, []);

  useEffect(() => {
    setShowDebug(speechDebugEnabled());
    setSelectedDeviceId(getSavedMicDeviceId());
    void loadDevices(true);
    const unsub = subscribeDeviceChanges(() => void loadDevices(false));
    return () => {
      unsub();
      stopActiveProbeStream();
      releaseStreamInternal();
    };
  }, [loadDevices, releaseStreamInternal]);

  const refreshDevices = useCallback(async () => {
    if (recordingRef.current) return;
    setRefreshingDevices(true);
    setError(null);
    try {
      releaseStreamInternal();
      const list = await loadDevices(true);
      if (list.length === 0) {
        setError("No microphones found. Connect a device and click Refresh.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh devices");
    } finally {
      setRefreshingDevices(false);
    }
  }, [loadDevices, releaseStreamInternal]);

  const patchDebug = useCallback((patch: Partial<SpeechDebugInfo>) => {
    if (!speechDebugEnabled()) return;
    setDebugInfo((prev) => ({
      micLabel: micDeviceLabel || "",
      deviceId: selectedDeviceId,
      permission: prev?.permission || "",
      browserStarted: true,
      browserResultCount: 0,
      browserDisabled: false,
      noSpeechRetries: 0,
      audioLevel: audioLevelRef.current,
      interimText: sessionInterimRef.current,
      finalText: sessionFinalRef.current,
      lastError: "",
      engine: engine || "",
      blobSize: 0,
      devices: devices.map((d) => ({
        deviceId: d.deviceId,
        label: d.displayLabel,
        groupId: d.groupId,
      })),
      signalHealth,
      ...patch,
    }));
  }, [micDeviceLabel, selectedDeviceId, engine, devices, signalHealth]);

  const handleTranscript = useCallback(
    (final: string, interim: string) => {
      sessionFinalRef.current = final;
      sessionInterimRef.current = interim;
      speechLog("useSpeechToText.ts:handleTranscript", {
        message: interim ? "interim_text" : "final_text",
        data: { final: final.slice(0, 60), interim: interim.slice(0, 60) },
      });
      scheduleTextboxUpdate();
      if (final || interim) {
        setStatus("live");
        setSignalMessage("🟢 Hearing you");
      }
      patchDebug({ finalText: final, interimText: interim });
    },
    [scheduleTextboxUpdate, patchDebug]
  );

  const finalize = useCallback(
    async (raw: string) => {
      let text = raw.trim();
      if (!text) {
        const heard = peakLevelRef.current > HEARING_THRESHOLD;
        setError(
          heard
            ? "No speech recognized. Try speaking longer or check language settings."
            : "No speech detected. Check mic volume or try another input device."
        );
        setStatus("error");
        releaseStreamInternal();
        return;
      }

      if (polishOnStop) {
        setStatus("polishing");
        setSignalMessage("⏳ Polishing…");
        try {
          const out = await polishSpeechText(text);
          text = (out.text || text).trim();
        } catch {
          /* keep raw */
        }
      }

      const full = joinBaseAndSpeech(dictationBaseRef.current, text, "");
      if (onLiveUpdateRef.current) onLiveUpdateRef.current(full);
      else onTranscript(text);

      speechLog("useSpeechToText.ts:finalize", {
        message: "recording_stopped",
        data: { textLen: text.length },
      });

      setStatus("stopped");
      setSignalMessage("✅ Ready");
      setTimeout(() => {
        setStatus("idle");
        setSignalMessage(null);
        setError(null);
        sessionFinalRef.current = "";
        sessionInterimRef.current = "";
      }, 600);
      releaseStreamInternal();
      speechLog("useSpeechToText.ts:cleanup", { message: "cleanup_finished" });
    },
    [onTranscript, polishOnStop, releaseStreamInternal]
  );

  const transcribeServer = useCallback(
    async (blob: Blob) => {
      setStatus("transcribing");
      setSignalMessage("⏳ Converting speech…");
      setEngine("server");
      try {
        const result = await transcribeSpeech(blob, language, matterId);
        await finalize(result.text || "");
      } catch (e) {
        const fallbackText = `${sessionFinalRef.current} ${sessionInterimRef.current}`.trim();
        if (e instanceof SpeechBrowserFallbackError && fallbackText) {
          await finalize(fallbackText);
          return;
        }
        setError(
          e instanceof SpeechBrowserFallbackError
            ? "Live captions unavailable for this language — type your question or try English."
            : e instanceof Error
              ? e.message
              : "Transcription failed"
        );
        setStatus("error");
        releaseStreamInternal();
      }
    },
    [language, matterId, finalize, releaseStreamInternal]
  );

  const start = useCallback(async () => {
    if (disabled || isBusy || recordingRef.current || stoppingRef.current) return;

    setError(null);
    setSignalMessage(null);
    sessionFinalRef.current = "";
    sessionInterimRef.current = "";
    peakLevelRef.current = 0;
    dictationBaseRef.current = getBaseTextRef.current?.() ?? "";
    setStatus("checking");

    speechLog("useSpeechToText.ts:start", { message: "recording_starting" });

    stopActiveProbeStream();
    const list = await loadDevices(false);
    const deviceId = pickBestDeviceId(list, selectedDeviceId || undefined);
    if (deviceId && deviceId !== selectedDeviceId) {
      setSelectedDeviceId(deviceId);
      saveMicDeviceId(deviceId);
    }

    const diag = await runMicDiagnostics(deviceId || selectedDeviceId || undefined);
    if (!diag.ok || !diag.stream) {
      setError(diag.issues.join(" ") || "Microphone check failed.");
      setStatus("error");
      return;
    }

    const stream = diag.stream;
    streamRef.current = stream;
    recordingRef.current = true;
    stoppingRef.current = false;

    setMicDeviceLabel(diag.label || getStreamMicLabel(stream));
    peakLevelRef.current = diag.peakLevel ?? 0;

    stopMonitorRef.current = createAudioLevelMonitor(stream, scheduleLevelUpdate);

    const recorder = new MediaRecorderSession(stream);
    recorderRef.current = recorder;
    recorder.start();

    setEngine(diag.browserSttAvailable ? "hybrid" : "server");
    setStatus("listening");
    setSignalMessage("🔴 Listening…");

    if (diag.browserSttAvailable) {
      const session = new BrowserCaptionSession(language, {
        onStart: () => {
          speechLog("useSpeechToText.ts:browser", { message: "recording_started" });
        },
        onTranscript: handleTranscript,
        onDisabled: (reason) => {
          setEngine("server");
          setSignalMessage(reason);
          patchDebug({ browserDisabled: true });
        },
      });
      browserRef.current = session;
      session.start();
    }

    speechLog("useSpeechToText.ts:start", { message: "recording_started" });
  }, [
    disabled,
    isBusy,
    selectedDeviceId,
    loadDevices,
    language,
    handleTranscript,
    scheduleLevelUpdate,
    patchDebug,
  ]);

  const stop = useCallback(async () => {
    if (!recordingRef.current || stoppingRef.current) return;

    stoppingRef.current = true;
    recordingRef.current = false;
    setStatus("stopping");
    setSignalMessage("⏹ Finalizing transcript…");

    speechLog("useSpeechToText.ts:stop", { message: "recording_stopping" });

    const browser = browserRef.current;
    browserRef.current = null;

    let browserText = "";
    if (browser) {
      try {
        await browser.stop();
        browserText = browser.fullText;
      } catch {
        browserText = `${sessionFinalRef.current} ${sessionInterimRef.current}`.trim();
      }
    } else {
      browserText = `${sessionFinalRef.current} ${sessionInterimRef.current}`.trim();
    }

    flushTextboxRef.current();

    const recorder = recorderRef.current;
    recorderRef.current = null;

    stopMonitorRef.current?.();
    stopMonitorRef.current = null;

    const stream = streamRef.current;
    streamRef.current = null;

    let blob: Blob | null = null;
    try {
      if (recorder) {
        blob = await recorder.stop(5000);
      }
    } catch {
      blob = null;
    }

    stream?.getTracks().forEach((t) => t.stop());

    const text = browserText.trim();
    const blobOk = blob && blob.size >= 200;
    const heard = peakLevelRef.current > HEARING_THRESHOLD;

    stoppingRef.current = false;

    if (text) {
      await finalize(text);
      return;
    }
    if (blobOk && blob) {
      await transcribeServer(blob);
      return;
    }

    setError(
      heard
        ? "Audio captured but no words recognized. Try again or speak longer."
        : "No speech captured. Check mic input volume or device selection."
    );
    setStatus("error");
    releaseStreamInternal();
  }, [finalize, transcribeServer, releaseStreamInternal]);

  const selectDevice = useCallback(
    async (deviceId: string) => {
      if (recordingRef.current) return;
      setSelectedDeviceId(deviceId);
      saveMicDeviceId(deviceId);
      setSignalHealth("testing");
      setSignalMessage("Testing microphone…");
      try {
        const testId = deviceId || pickBestDeviceId(devices, deviceId);
        if (!testId && !deviceId) return;
        const result = await testMicDeviceHealth(testId || deviceId, 1400);
        setSignalHealth(result.health);
        setSignalMessage(result.message);
        setMicDeviceLabel(result.label);
        peakLevelRef.current = result.peakLevel;
      } finally {
        stopActiveProbeStream();
      }
    },
    [devices]
  );

  const toggle = useCallback(() => {
    if (recordingRef.current && !stoppingRef.current) void stop();
    else void start();
  }, [start, stop]);

  return {
    status,
    speechPhase,
    phase:
      status === "transcribing"
        ? "transcribing"
        : status === "polishing"
          ? "polishing"
          : mapStatusToPhase(status) === "idle"
            ? "idle"
            : "listening",
    isListening,
    isBusy,
    isStopping,
    error,
    statusHint: signalMessage,
    statusLabel: error || signalMessage,
    micDeviceLabel,
    audioLevel,
    engine,
    signalHealth,
    signalMessage,
    bluetoothWarning,
    refreshingDevices,
    availableMics: devices.map((d) => d.displayLabel),
    devices,
    selectedDeviceId,
    selectDevice,
    refreshDevices,
    interimText: sessionInterimRef.current,
    finalText: sessionFinalRef.current,
    showDebug,
    debugInfo,
    start,
    stop,
    toggle,
    setError,
  };
}
