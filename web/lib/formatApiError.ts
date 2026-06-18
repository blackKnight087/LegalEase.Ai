/** Map API / network errors to user-friendly messages. */
export function formatApiError(e: unknown): string {
  if (e instanceof Error) {
    const m = e.message;
    if (e.name === "AbortError" || /timeout/i.test(m)) {
      return "Request timed out. The server may be busy — try again.";
    }
    if (/401|not authenticated|invalid.*token/i.test(m)) {
      return "Session expired. Please sign in again.";
    }
    if (/403|forbidden|suspended/i.test(m)) {
      return m;
    }
    if (/429|rate limit/i.test(m)) {
      return "Too many requests. Wait a minute and try again.";
    }
    if (/failed to fetch|network|connection/i.test(m)) {
      return "Cannot reach the server. Check that the backend is running.";
    }
    return m;
  }
  return "Something went wrong. Please try again.";
}
