"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/components/providers/AuthProvider";
import * as api from "@/lib/api";

export default function FirmChatUserSearch({
  onOpenRoom,
  onStatusMessage,
}: {
  onOpenRoom: (roomId: string) => void;
  onStatusMessage?: (msg: string) => void;
}) {
  const { user } = useAuth();
  const myUsername = String(user?.username || "");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<api.CollabUserSearchHit[]>([]);
  const [suggested, setSuggested] = useState<Array<{ user_id: string; username: string }>>([]);
  const [incoming, setIncoming] = useState<api.CollabChatRequest[]>([]);
  const [outgoing, setOutgoing] = useState<api.CollabChatRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState("");

  const loadRequests = useCallback(async () => {
    try {
      const r = await api.fetchCollabChatRequests();
      setIncoming(r.incoming || []);
      setOutgoing(r.outgoing || []);
    } catch {
      setIncoming([]);
      setOutgoing([]);
    }
  }, []);

  const loadSuggested = useCallback(async () => {
    try {
      const r = await api.fetchCollabMembers();
      setSuggested((r.members || []).slice(0, 20));
    } catch {
      setSuggested([]);
    }
  }, []);

  useEffect(() => {
    void loadRequests();
    void loadSuggested();
  }, [loadRequests, loadSuggested]);

  const runSearch = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim().replace(/^@+/, "");
    if (q.length < 2) {
      setHits([]);
      setSearched(false);
      setSearchError("Type at least 2 characters of their sign-in username or email.");
      return;
    }
    setBusy(true);
    setSearchError("");
    setSearched(true);
    try {
      const r = await api.searchCollabUsers(q);
      setHits(r.users || []);
      if (r.hint) {
        setSearchError(r.hint);
      } else if (!(r.users || []).length) {
        setSearchError(
          `No users found for "${q}". They must register in LegalEase first. Use their login username exactly.`
        );
      }
    } catch (e) {
      setHits([]);
      const msg = e instanceof Error ? e.message : "Search failed";
      setSearchError(
        msg.includes("404")
          ? "Search API unavailable — try again in a moment."
          : msg
      );
    } finally {
      setBusy(false);
    }
  };

  const sendRequest = async (userId: string, username: string) => {
    const intro =
      window.prompt(
        `Optional note for @${username} (they must accept before you can chat):`,
        "Would like to chat with you on Firm Chat."
      ) ?? "";
    if (intro === null) return;
    setBusy(true);
    try {
      const r = await api.sendCollabChatRequest(userId, intro);
      if (r.status === "connected" && r.room?.room_id) {
        onOpenRoom(r.room.room_id);
        onStatusMessage?.("You're connected — chat is open.");
      } else {
        onStatusMessage?.(r.message || "Chat request sent.");
      }
      await runSearch(query);
      await loadRequests();
    } catch (e) {
      onStatusMessage?.(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const accept = async (requestId: string) => {
    setBusy(true);
    try {
      const r = await api.acceptCollabChatRequest(requestId);
      if (r.room?.room_id) onOpenRoom(r.room.room_id);
      onStatusMessage?.("Request accepted — you can chat now.");
      await loadRequests();
      await runSearch(query);
    } catch (e) {
      onStatusMessage?.(e instanceof Error ? e.message : "Accept failed");
    } finally {
      setBusy(false);
    }
  };

  const reject = async (requestId: string) => {
    setBusy(true);
    try {
      await api.rejectCollabChatRequest(requestId);
      await loadRequests();
    } catch (e) {
      onStatusMessage?.(e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  };

  const openDm = async (userId: string) => {
    setBusy(true);
    try {
      const r = await api.createCollabDm(userId);
      if (r.room?.room_id) onOpenRoom(r.room.room_id);
    } catch (e) {
      onStatusMessage?.(e instanceof Error ? e.message : "Could not open chat");
    } finally {
      setBusy(false);
    }
  };

  const actionFor = (u: api.CollabUserSearchHit) => {
    if (u.is_self || u.connection_status === "self") {
      return <span className="text-xs text-slate-500 font-medium">This is you</span>;
    }
    switch (u.connection_status) {
      case "connected":
        return (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => openDm(u.user_id)}>
            Open chat
          </Button>
        );
      case "pending_sent":
        return (
          <span className="text-xs text-amber-700 font-medium">Request sent — waiting</span>
        );
      case "pending_received":
        return (
          <span className="text-xs text-blue-700 font-medium">They requested you — see below</span>
        );
      default:
        return (
          <Button size="sm" disabled={busy} onClick={() => sendRequest(u.user_id, u.username)}>
            Send chat request
          </Button>
        );
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <p className="font-semibold text-slate-800 m-0 mb-1 text-sm">Find someone by username</p>
        {myUsername && (
          <p className="text-xs text-blue-800 m-0 mb-2 bg-blue-50 border border-blue-100 rounded-lg px-2 py-1.5">
            You are signed in as <strong>@{myUsername}</strong> — search for a <em>different</em> account&apos;s
            login name (e.g. another user like <code className="bg-white px-1 rounded">saimon</code>).
          </p>
        )}
        <p className="text-xs text-slate-500 m-0 mb-2">
          Matches sign-in username, email, or display name. Both accounts must be registered in LegalEase.
        </p>
        <div className="flex gap-1">
          <input
            className="le-input flex-1 !min-h-[36px] !py-1.5 text-xs"
            placeholder="e.g. saimon or colleague@email.com"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearchError("");
            }}
            onKeyDown={(e) => e.key === "Enter" && void runSearch()}
          />
          <Button size="sm" variant="secondary" onClick={() => void runSearch()} disabled={busy}>
            {busy ? "…" : "Search"}
          </Button>
        </div>
        {searchError && (
          <p className="text-xs text-amber-800 m-0 mt-2" role="alert">
            {searchError}
          </p>
        )}
      </div>

      {suggested.length > 0 && !searched && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
          <p className="text-xs font-bold text-slate-600 m-0 mb-2">Registered users (quick pick)</p>
          <div className="flex flex-wrap gap-1.5">
            {suggested.map((m) => (
              <button
                key={m.user_id}
                type="button"
                className="px-2.5 py-1 rounded-lg border bg-white text-xs font-medium hover:border-blue-300 hover:bg-blue-50"
                onClick={() => {
                  setQuery(m.username);
                  void runSearch(m.username);
                }}
              >
                @{m.username}
              </button>
            ))}
          </div>
        </div>
      )}

      {incoming.length > 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-2 space-y-2">
          <p className="text-xs font-bold text-slate-700 m-0">Incoming requests</p>
          {incoming.map((req) => (
            <div key={req.request_id} className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-medium text-slate-800">
                @{req.from_username || req.from_user_id?.slice(0, 8)}
              </span>
              {req.intro_message && (
                <span className="text-slate-600 truncate max-w-[200px]">{req.intro_message}</span>
              )}
              <Button size="sm" disabled={busy} onClick={() => accept(req.request_id)}>
                Accept
              </Button>
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => reject(req.request_id)}>
                Decline
              </Button>
            </div>
          ))}
        </div>
      )}

      {outgoing.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
          <p className="text-xs font-bold text-slate-600 m-0 mb-1">Waiting for acceptance</p>
          <ul className="m-0 pl-4 text-xs text-slate-600 space-y-0.5">
            {outgoing.map((req) => (
              <li key={req.request_id}>
                @{req.to_username || req.to_user_id?.slice(0, 8)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {hits.length > 0 && (
        <ul className="m-0 p-0 list-none space-y-2">
          {hits.map((u) => (
            <li
              key={u.user_id}
              className="flex flex-wrap items-center justify-between gap-2 px-2 py-2 rounded-lg border border-slate-200 bg-white"
            >
              <span className="text-sm font-medium text-slate-800">
                @{u.username}
                {u.display_name ? ` (${u.display_name})` : ""}
              </span>
              {actionFor(u)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
