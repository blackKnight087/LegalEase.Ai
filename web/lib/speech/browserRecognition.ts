import { browserSpeechLang, uiLangToCode } from "@/lib/speechLang";
import { speechLog } from "./logger";

export type RecState = "idle" | "starting" | "listening" | "stopping";

const MAX_NO_SPEECH = 3;
const RESTART_DELAY_MS = 120;

type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((ev: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: { isFinal: boolean; [index: number]: { transcript: string } };
  };
}

export function getBrowserSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export type LiveCaptionCallbacks = {
  onStart?: () => void;
  onTranscript?: (final: string, interim: string) => void;
  onError?: (error: string) => void;
  onDisabled?: (reason: string) => void;
  onEnd?: () => void;
};

/**
 * Single persistent browser recognition session with state machine.
 * Rebuilds full final+interim from results each onresult (ChatGPT-style).
 */
export class BrowserCaptionSession {
  private rec: SpeechRecognitionInstance | null = null;
  private state: RecState = "idle";
  private manualStop = false;
  private noSpeechCount = 0;
  private disabled = false;
  private finalTranscript = "";
  private lastInterim = "";
  private restartTimer: ReturnType<typeof setTimeout> | null = null;
  private endResolve: (() => void) | null = null;

  constructor(
    private language: string,
    private callbacks: LiveCaptionCallbacks
  ) {}

  get stateSnapshot() {
    return this.state;
  }

  get finalText() {
    return this.finalTranscript;
  }

  get fullText() {
    const f = this.finalTranscript.trim();
    const i = this.lastInterim.trim();
    if (!i) return f;
    if (!f) return i;
    return `${f} ${i}`.trim();
  }

  get isDisabled() {
    return this.disabled;
  }

  /** Rebuild full transcript each event (final segments + live interim). */
  private handleResult(ev: SpeechRecognitionEvent) {
    let interim = "";
    let allFinal = "";

    for (let i = 0; i < ev.results.length; i++) {
      const piece = ev.results[i][0]?.transcript || "";
      if (!piece) continue;
      if (ev.results[i].isFinal) {
        allFinal += piece;
      }
    }
    for (let i = 0; i < ev.results.length; i++) {
      if (!ev.results[i].isFinal) {
        interim += ev.results[i][0]?.transcript || "";
      }
    }

    this.finalTranscript = allFinal.trim();
    this.lastInterim = interim.trim();

    speechLog("browserRecognition.ts:onresult", {
      message: "speech_detected",
      data: {
        finalLen: this.finalTranscript.length,
        interimLen: interim.length,
        preview: (interim || this.finalTranscript).slice(0, 60),
      },
    });

    this.callbacks.onTranscript?.(this.finalTranscript, this.lastInterim);
  }

  start(): boolean {
    if (this.disabled || this.state === "listening" || this.state === "starting") {
      return false;
    }
    const Ctor = getBrowserSpeechRecognitionCtor();
    if (!Ctor) {
      this.disabled = true;
      this.callbacks.onDisabled?.("Browser speech recognition not supported.");
      return false;
    }

    this.manualStop = false;
    this.noSpeechCount = 0;
    this.finalTranscript = "";
    this.state = "starting";

    const code = uiLangToCode(this.language);
    const rec = new Ctor();
    this.rec = rec;

    rec.lang = browserSpeechLang(code);
    rec.continuous = true;
    rec.interimResults = true;

    rec.onstart = () => {
      this.state = "listening";
      speechLog("browserRecognition.ts:onstart", { message: "recording_started" });
      this.callbacks.onStart?.();
    };

    rec.onresult = (ev) => this.handleResult(ev);

    rec.onerror = (ev) => {
      const err = ev.error || "unknown";
      if (err === "aborted" || (this.manualStop && err === "no-speech")) return;

      if (err === "no-speech") {
        this.noSpeechCount += 1;
        if (this.noSpeechCount >= MAX_NO_SPEECH && this.state === "listening") {
          this.disabled = true;
          this.callbacks.onDisabled?.(
            "Live captions unavailable — server transcription when you stop."
          );
        }
        return;
      }

      speechLog("browserRecognition.ts:onerror", {
        message: "recognition_error",
        data: { error: err },
      });
      this.callbacks.onError?.(err);
      if (err === "not-allowed" || err === "service-not-allowed") {
        this.disabled = true;
      }
    };

    rec.onend = () => {
      speechLog("browserRecognition.ts:onend", {
        message: "recognition_onend",
        data: { manualStop: this.manualStop, state: this.state },
      });

      if (this.manualStop || this.state === "stopping") {
        this.state = "idle";
        this.rec = null;
        this.endResolve?.();
        this.endResolve = null;
        this.callbacks.onEnd?.();
        return;
      }

      if (!this.disabled && this.state === "listening") {
        this.clearRestartTimer();
        this.restartTimer = setTimeout(() => {
          if (this.manualStop || this.disabled || !this.rec) return;
          try {
            this.rec.start();
          } catch {
            this.state = "idle";
          }
        }, RESTART_DELAY_MS);
      }
    };

    try {
      rec.start();
      return true;
    } catch (e) {
      this.state = "idle";
      this.disabled = true;
      this.callbacks.onDisabled?.("Could not start browser speech recognition.");
      return false;
    }
  }

  private clearRestartTimer() {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
  }

  /** Graceful stop — wait for onend, no restart. */
  stop(): Promise<void> {
    return new Promise((resolve) => {
      if (this.state === "idle" || !this.rec) {
        resolve();
        return;
      }

      this.manualStop = true;
      this.state = "stopping";
      this.clearRestartTimer();
      this.endResolve = resolve;

      const timeout = setTimeout(() => {
        speechLog("browserRecognition.ts:stop", { message: "stop_timeout_abort" });
        try {
          this.rec?.abort();
        } catch {
          /* ignore */
        }
        this.rec = null;
        this.state = "idle";
        this.endResolve = null;
        resolve();
      }, 2500);

      const prevResolve = this.endResolve;
      this.endResolve = () => {
        clearTimeout(timeout);
        prevResolve?.();
      };

      try {
        this.rec.stop();
      } catch {
        clearTimeout(timeout);
        this.rec = null;
        this.state = "idle";
        resolve();
      }
    });
  }

  abort() {
    this.manualStop = true;
    this.state = "idle";
    this.clearRestartTimer();
    try {
      this.rec?.abort();
    } catch {
      /* ignore */
    }
    this.rec = null;
  }
}
