/** Reliable audio capture via MediaRecorder (server STT on stop). */

export class MediaRecorderSession {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private mimeType = "audio/webm";

  constructor(private stream: MediaStream) {}

  start(): void {
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
    this.mimeType = mime ? mime.split(";")[0] : "audio/webm";
    const options: MediaRecorderOptions = mime ? { mimeType: mime } : {};
    this.recorder = new MediaRecorder(this.stream, options);
    this.chunks = [];
    this.recorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) this.chunks.push(ev.data);
    };
    this.recorder.start(250);
  }

  stop(timeoutMs = 4000): Promise<Blob> {
    const rec = this.recorder;
    if (!rec || rec.state === "inactive") {
      return Promise.resolve(new Blob(this.chunks, { type: this.mimeType }));
    }

    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (blob: Blob) => {
        if (settled) return;
        settled = true;
        resolve(blob);
      };

      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        try {
          if (rec.state !== "inactive") rec.stop();
        } catch {
          /* ignore */
        }
        resolve(new Blob(this.chunks, { type: this.mimeType }));
      }, timeoutMs);

      rec.onstop = () => {
        clearTimeout(timer);
        finish(new Blob(this.chunks, { type: this.mimeType }));
      };
      rec.onerror = () => {
        clearTimeout(timer);
        if (!settled) {
          settled = true;
          reject(new Error("Recording failed"));
        }
      };

      try {
        if (rec.state === "recording") rec.requestData();
        rec.stop();
      } catch (e) {
        clearTimeout(timer);
        if (!settled) {
          settled = true;
          reject(e instanceof Error ? e : new Error("Stop recording failed"));
        }
      }
    });
  }

  get state() {
    return this.recorder?.state ?? "inactive";
  }
}
