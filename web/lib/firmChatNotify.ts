/** Browser notifications for Firm Chat (no LLM). */

const PERM_KEY = "legalease_firm_chat_notify_asked";

export function requestFirmChatNotifyPermission(): void {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  try {
    if (localStorage.getItem(PERM_KEY)) return;
    if (Notification.permission === "default") {
      void Notification.requestPermission().finally(() => {
        localStorage.setItem(PERM_KEY, "1");
      });
    }
  } catch {
    /* ignore */
  }
}

export function showFirmChatNotification(
  title: string,
  body: string,
  roomId: string
): void {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  if (document.visibilityState === "visible") {
    const params = new URLSearchParams(window.location.search);
    if (params.get("room") === roomId && window.location.pathname.includes("collaboration")) {
      return;
    }
  }
  try {
    const n = new Notification(title, {
      body: body.slice(0, 200),
      tag: `firm-chat-${roomId}`,
      icon: "/favicon.ico",
    });
    n.onclick = () => {
      window.focus();
      window.location.href = `/collaboration?room=${encodeURIComponent(roomId)}`;
      n.close();
    };
  } catch {
    /* ignore */
  }
}

export const FIRM_CHAT_NOTIFY_EVENT = "legalease:firm-chat-notify";

export function dispatchFirmChatNotifyRefresh(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(FIRM_CHAT_NOTIFY_EVENT));
  }
}
