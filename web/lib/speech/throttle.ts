/** Throttle callbacks to limit React updates (rAF for UI, ms for levels). */

export function throttleRaf(fn: () => void): () => void {
  let scheduled = false;
  return () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      fn();
    });
  };
}

export function throttleMs<T extends unknown[]>(
  fn: (...args: T) => void,
  ms: number
): (...args: T) => void {
  let last = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: T | null = null;

  return (...args: T) => {
    pending = args;
    const now = Date.now();
    const elapsed = now - last;

    const run = () => {
      last = Date.now();
      timer = null;
      if (pending) {
        fn(...pending);
        pending = null;
      }
    };

    if (elapsed >= ms) {
      if (timer) clearTimeout(timer);
      run();
    } else if (!timer) {
      timer = setTimeout(run, ms - elapsed);
    }
  };
}
