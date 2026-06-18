const API_BASE = import.meta.env.VITE_API_URL || "";

export async function sendChat({
  userId,
  message,
  mode,
  lang,
  history,
  attachment,
}) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      mode,
      lang,
      history,
      attachment,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText || "Chat request failed");
  }
  return res.json();
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.ok;
}
