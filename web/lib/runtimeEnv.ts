/** True when the app is opened on a developer machine (not production DuckDNS/IP). */
export function isLocalDevHost(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1";
}

export function backendStartHint(): string {
  return isLocalDevHost()
    ? "Run .\\run_backend.ps1 in a terminal and keep it open."
    : "The server may be restarting — wait a moment and try again.";
}

export function backendUnreachableMessage(): string {
  return isLocalDevHost()
    ? "Cannot reach the API. Run .\\run_backend.ps1 in a separate terminal."
    : "Cannot reach the server. Check your connection and try again.";
}
