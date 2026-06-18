import type { CollabMessage } from "@/lib/api";

/** Match current user to message sender (id or login username). */
export function isMessageMine(
  message: CollabMessage,
  myId: string,
  myUsername: string
): boolean {
  if (!myId && !myUsername) return false;
  const sid = String(message.sender_id || "").trim();
  if (myId && sid && sid === myId) return true;
  const sname = String(message.sender_name || "")
    .trim()
    .toLowerCase();
  const uname = myUsername.trim().toLowerCase();
  if (uname && sname && sname === uname) return true;
  return false;
}
