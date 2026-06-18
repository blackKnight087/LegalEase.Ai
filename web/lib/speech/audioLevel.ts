/** Real-time mic level — RMS from time + frequency domains. */

function computeRmsLevel(analyser: AnalyserNode): number {
  const timeData = new Uint8Array(analyser.fftSize);
  const freqData = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteTimeDomainData(timeData);
  analyser.getByteFrequencyData(freqData);

  let sumSq = 0;
  for (let i = 0; i < timeData.length; i++) {
    const v = (timeData[i] - 128) / 128;
    sumSq += v * v;
  }
  const timeRms = Math.sqrt(sumSq / timeData.length);

  let freqSum = 0;
  for (let i = 0; i < freqData.length; i++) freqSum += freqData[i];
  const freqRms = freqSum / freqData.length / 255;

  const combined = timeRms * 0.65 + freqRms * 0.35;
  return Math.min(1, combined * 2.8);
}

export function createAudioLevelMonitor(
  stream: MediaStream,
  onLevel: (level: number) => void
): () => void {
  let closed = false;
  let raf = 0;
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.35;
  source.connect(analyser);

  const tick = () => {
    if (closed) return;
    onLevel(computeRmsLevel(analyser));
    raf = requestAnimationFrame(tick);
  };

  void ctx.resume().then(() => {
    if (!closed) tick();
  });

  return () => {
    closed = true;
    cancelAnimationFrame(raf);
    source.disconnect();
    void ctx.close();
    onLevel(0);
  };
}

export async function sampleMicLevelRms(
  stream: MediaStream,
  ms = 1500
): Promise<number> {
  return new Promise((resolve) => {
    let peak = 0;
    const stop = createAudioLevelMonitor(stream, (l) => {
      if (l > peak) peak = l;
    });
    setTimeout(() => {
      stop();
      resolve(peak);
    }, ms);
  });
}

/** @deprecated use sampleMicLevelRms */
export async function sampleMicLevel(stream: MediaStream, ms = 1200): Promise<number> {
  return sampleMicLevelRms(stream, ms);
}
