/** Shared Firm Chat UI helpers (avatars, time, previews). */

export function firmChatAvatarColor(seed: string): string {
  const colors = [
    "#6366f1",
    "#059669",
    "#d97706",
    "#e11d48",
    "#0891b2",
    "#4f46e5",
    "#7c3aed",
    "#0d9488",
  ];
  let n = 0;
  for (let i = 0; i < seed.length; i++) n += seed.charCodeAt(i);
  return colors[n % colors.length];
}

export function firmChatInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (name.slice(0, 2) || "?").toUpperCase();
}

export function formatChatTime(iso?: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export function formatLastSeen(epoch?: number): string {
  if (!epoch) return "Offline";
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (sec < 60) return "Online now";
  if (sec < 3600) return `Active ${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `Active ${Math.floor(sec / 3600)}h ago`;
  return "Offline";
}

export function notificationIcon(type: string): string {
  const t = (type || "").toLowerCase();
  if (t.includes("mention")) return "@";
  if (t.includes("message")) return "💬";
  if (t.includes("document") || t.includes("file")) return "📄";
  if (t.includes("task")) return "✓";
  if (t.includes("deadline") || t.includes("hearing")) return "📅";
  if (t.includes("matter")) return "📁";
  return "🔔";
}
