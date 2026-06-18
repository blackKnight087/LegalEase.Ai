"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import Alert from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import FirmChatConnectGuide from "@/components/collaboration/FirmChatConnectGuide";
import FirmChatUserSearch from "@/components/collaboration/FirmChatUserSearch";
import FirmChatMessage, {
  FirmChatDayDivider,
  firmChatDayKey,
  formatDayLabel,
} from "@/components/collaboration/FirmChatMessage";
import FirmChatRoomSidebar from "@/components/collaboration/FirmChatRoomSidebar";
import FirmChatInboxHome from "@/components/collaboration/FirmChatInboxHome";
import FirmChatNotificationCenter from "@/components/collaboration/FirmChatNotificationCenter";
import FirmChatMatterPanel, { type FirmChatRoomContext } from "@/components/collaboration/FirmChatMatterPanel";
import FirmChatAvatar from "@/components/collaboration/FirmChatAvatar";
import { formatLastSeen } from "@/components/collaboration/firmChatUi";
import FirmChatCreateChannelModal from "@/components/collaboration/FirmChatCreateChannelModal";
import { isMessageMine } from "@/components/collaboration/firmChatUtils";
import { useAuth } from "@/components/providers/AuthProvider";
import * as api from "@/lib/api";
import { FIRM_CHAT_FREE_NOTE, FIRM_CHAT_NAME, FIRM_CHAT_TAGLINE } from "@/lib/firmChat";
import {
  dispatchFirmChatNotifyRefresh,
  requestFirmChatNotifyPermission,
  showFirmChatNotification,
} from "@/lib/firmChatNotify";
import VoiceMicIcon from "@/components/ui/VoiceMicIcon";
import { FirmChatRealtimeClient } from "@/lib/firmChatRealtime";
import { isRateLimitError, useFirmChatRateLimitBanner } from "@/lib/firmChatRateLimit";
import { getFirmChatDiagnostics, patchFirmChatDiagnostics } from "@/lib/firmChatDiagnostics";

const PRACTICE_SLUGS = new Set([
  "criminal-team",
  "civil-team",
  "corporate-team",
  "litigation",
  "associates",
]);

const GUIDE_KEY = "legalease_firm_chat_guide_dismissed";

function roomTypeLabel(room?: api.CollabRoom): string {
  if (!room) return "";
  if (room.room_type === "dm") return "Direct message";
  if (room.room_type === "matter") return "Case chat";
  if (room.room_type === "channel") return "Channel";
  return "Chat";
}

export default function CollaborationHub({
  initialRoomId = "",
  matterId = "",
  embedded = false,
}: {
  initialRoomId?: string;
  matterId?: string;
  embedded?: boolean;
}) {
  const { user } = useAuth();
  const myId = String(user?.id || "");
  const myUsername = String(user?.username || "");
  const router = useRouter();
  const searchParams = useSearchParams();
  const roomFromUrl = searchParams.get("room") || initialRoomId;

  const [rooms, setRooms] = useState<api.CollabRoom[]>([]);
  const [activeId, setActiveId] = useState(roomFromUrl);
  const [messages, setMessages] = useState<api.CollabMessage[]>([]);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<api.CollabRoom[]>([]);
  const [searchMessageHits, setSearchMessageHits] = useState<
    Array<{ message_id: string; room_id: string; body: string; room_name?: string }>
  >([]);
  const [roomContext, setRoomContext] = useState<FirmChatRoomContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [typingUsers, setTypingUsers] = useState<Array<{ display_name?: string }>>([]);
  const [orgOnlineIds, setOrgOnlineIds] = useState<Set<string>>(new Set());
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [showFindModal, setShowFindModal] = useState(false);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceUploadPct, setVoiceUploadPct] = useState<number | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [mobileShowChat, setMobileShowChat] = useState(false);
  const [onlineIds, setOnlineIds] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const lastMessageAtRef = useRef<string>("");
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const roomsRef = useRef(rooms);
  roomsRef.current = rooms;
  const realtimeRef = useRef<FirmChatRealtimeClient | null>(null);
  const roomsRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { banner: rateLimitBanner, showRateLimit, onRequestSuccess, clearBanner } =
    useFirmChatRateLimitBanner();

  const handleChatError = useCallback(
    (e: unknown, source: string) => {
      const msg = e instanceof Error ? e.message : String(e);
      if (isRateLimitError(msg)) {
        showRateLimit(source, msg);
        return;
      }
      setErr(msg);
    },
    [showRateLimit]
  );

  const dismissGuide = () => {
    setShowGuide(false);
    try {
      localStorage.setItem(GUIDE_KEY, "1");
    } catch {
      /* ignore */
    }
  };

  const loadRooms = useCallback(async () => {
    try {
      const r = await api.fetchCollabRooms();
      setRooms(r.rooms || []);
      setErr("");
      onRequestSuccess();
    } catch (e) {
      handleChatError(e, "loadRooms");
    }
  }, [handleChatError, onRequestSuccess]);

  const notifyIncomingMessages = useCallback(
    (incoming: api.CollabMessage[], roomId: string, room?: api.CollabRoom) => {
      for (const m of incoming) {
        if (isMessageMine(m, myId, myUsername)) continue;
        const preview =
          m.message_type === "voice" ? "Voice message" : (m.body || "New message").slice(0, 120);
        const title =
          room?.room_type === "dm"
            ? `Message from ${m.sender_name || "colleague"}`
            : `New message in ${room?.name || "chat"}`;
        showFirmChatNotification(title, preview, roomId);
      }
      if (incoming.some((m) => !isMessageMine(m, myId, myUsername))) {
        dispatchFirmChatNotifyRefresh();
      }
    },
    [myId, myUsername]
  );

  const loadMessages = useCallback(
    async (roomId: string, incremental = false) => {
      if (!roomId) return;
      try {
        const since = incremental ? lastMessageAtRef.current : "";
        const r = await api.fetchCollabMessages(roomId, {
          since: since || undefined,
          limit: since ? 100 : 50,
        });
        const incoming = r.messages || [];
        const roomMeta = rooms.find((ro) => ro.room_id === roomId);
        if (incremental && since && incoming.length) {
          const fresh = incoming.filter((m) => !isMessageMine(m, myId, myUsername));
          if (fresh.length) notifyIncomingMessages(fresh, roomId, roomMeta);
          setMessages((prev) => {
            const ids = new Set(prev.map((m) => m.message_id));
            const merged = [...prev];
            for (const m of incoming) {
              if (!ids.has(m.message_id)) merged.push(m);
            }
            return merged;
          });
        } else if (!incremental) {
          setMessages(incoming);
          if (incoming.length) {
            lastMessageAtRef.current = incoming[incoming.length - 1]?.created_at || "";
          }
        }
        const last = incoming[incoming.length - 1];
        if (last?.created_at) {
          lastMessageAtRef.current = last.created_at;
        } else if (!incremental && incoming.length) {
          lastMessageAtRef.current = incoming[incoming.length - 1]?.created_at || "";
        }
        await api.markCollabRoomRead(roomId);
        onRequestSuccess();
        if (roomsRefreshRef.current) clearTimeout(roomsRefreshRef.current);
        roomsRefreshRef.current = setTimeout(() => void loadRooms(), 8000);
      } catch (e) {
        handleChatError(e, "loadMessages");
      }
    },
    [loadRooms, rooms, myId, myUsername, notifyIncomingMessages, handleChatError, onRequestSuccess]
  );

  useEffect(() => {
    loadRooms();
    requestFirmChatNotifyPermission();
  }, [loadRooms]);

  useEffect(() => {
    if (matterId && !activeId) {
      api
        .fetchCollabMatterRoom(matterId)
        .then((r) => {
          setActiveId(r.room.room_id);
          setMobileShowChat(true);
          if (!embedded) router.replace(`/collaboration?room=${r.room.room_id}`);
        })
        .catch((e) => setErr(e instanceof Error ? e.message : "Matter room error"));
    }
  }, [matterId, activeId, embedded, router]);

  useEffect(() => {
    if (roomFromUrl && roomFromUrl !== activeId) {
      setActiveId(roomFromUrl);
      setMobileShowChat(true);
    }
  }, [roomFromUrl, activeId]);

  useEffect(() => {
    const client = new FirmChatRealtimeClient({
      onStateChange: (s) => setWsConnected(s === "connected"),
      onMessage: (roomId, msg) => {
        if (roomId !== activeIdRef.current) return;
        setMessages((prev) => {
          if (prev.some((m) => m.message_id === msg.message_id)) return prev;
          return [...prev, msg];
        });
        if (msg.created_at) lastMessageAtRef.current = msg.created_at;
        if (!isMessageMine(msg, myId, myUsername)) {
          const roomMeta = roomsRef.current.find((ro) => ro.room_id === roomId);
          notifyIncomingMessages([msg], roomId, roomMeta);
        }
        onRequestSuccess();
      },
      onTyping: (roomId, typing) => {
        if (roomId === activeIdRef.current) setTypingUsers(typing);
      },
      onPresence: (roomId, online) => {
        if (roomId === activeIdRef.current) {
          setOnlineIds(new Set((online || []).map((o) => String(o.user_id || ""))));
        }
      },
      onNotification: () => dispatchFirmChatNotifyRefresh(),
    });
    realtimeRef.current = client;
    client.connect();
    return () => {
      client.disconnect();
      realtimeRef.current = null;
      setWsConnected(false);
    };
  }, [myId, myUsername, notifyIncomingMessages, onRequestSuccess]);

  useEffect(() => {
    if (!activeId || !wsConnected) return;
    realtimeRef.current?.subscribe(activeId);
    realtimeRef.current?.sendPresence(activeId, myUsername);
    const id = window.setInterval(() => {
      realtimeRef.current?.sendPresence(activeId, myUsername);
    }, 30000);
    return () => window.clearInterval(id);
  }, [activeId, myUsername, wsConnected]);

  useEffect(() => {
    if (!activeId || wsConnected) return;
    const tick = () => {
      void api.postCollabPresence(activeId, myUsername).catch(() => undefined);
      void api
        .fetchCollabPresence(activeId)
        .then((r) => setOnlineIds(new Set((r.online || []).map((o) => o.user_id))))
        .catch(() => undefined);
    };
    tick();
    const id = window.setInterval(tick, 30000);
    return () => window.clearInterval(id);
  }, [activeId, myUsername, wsConnected]);

  useEffect(() => {
    if (!activeId) return;
    lastMessageAtRef.current = "";
    loadMessages(activeId, false);

    let pollId: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      if (pollId) return;
      pollId = setInterval(() => loadMessages(activeId, true), 30000);
    };

    const mergeIncoming = (incoming: api.CollabMessage[]) => {
      if (!incoming.length) return;
      const room = rooms.find((r) => r.room_id === activeId);
      setMessages((prev) => {
        const ids = new Set(prev.map((m) => m.message_id));
        const merged = [...prev];
        const added: api.CollabMessage[] = [];
        for (const m of incoming) {
          if (!ids.has(m.message_id)) {
            merged.push(m);
            added.push(m);
          }
        }
        if (added.length) notifyIncomingMessages(added, activeId, room);
        return merged;
      });
      const last = incoming[incoming.length - 1];
      if (last?.created_at) {
        lastMessageAtRef.current = last.created_at;
      }
    };

    let es: EventSource | null = null;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("legalease_token")
        : null;

    if (token) {
      try {
        es = new EventSource(api.collabStreamUrl(activeId));
        es.addEventListener("message", (ev) => {
          try {
            const m = JSON.parse(ev.data) as api.CollabMessage;
            mergeIncoming([m]);
          } catch {
            /* ignore malformed SSE payload */
          }
        });
        es.onerror = () => {
          es?.close();
          es = null;
          startPolling();
        };
      } catch {
        startPolling();
      }
    } else {
      startPolling();
    }

    return () => {
      es?.close();
      if (pollId) clearInterval(pollId);
    };
  }, [activeId, loadMessages, rooms, notifyIncomingMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!activeId) {
      setRoomContext(null);
      return;
    }
    setContextLoading(true);
    void api
      .fetchCollabRoomContext(activeId)
      .then((c) => setRoomContext(c as FirmChatRoomContext))
      .catch(() => setRoomContext(null))
      .finally(() => setContextLoading(false));
  }, [activeId, messages.length]);

  useEffect(() => {
    if (wsConnected) return;
    const tick = () => {
      void api
        .fetchCollabPresence()
        .then((r) => setOrgOnlineIds(new Set((r.online || []).map((o) => o.user_id))))
        .catch(() => undefined);
    };
    tick();
    const id = window.setInterval(tick, 45000);
    return () => window.clearInterval(id);
  }, [wsConnected]);

  useEffect(() => {
    if (!activeId) {
      setTypingUsers([]);
      return;
    }
    if (wsConnected) return;
    const poll = () => {
      void api
        .fetchCollabTyping(activeId)
        .then((r) => setTypingUsers(r.typing || []))
        .catch(() => setTypingUsers([]));
    };
    poll();
    const id = window.setInterval(poll, 8000);
    return () => window.clearInterval(id);
  }, [activeId, wsConnected]);

  const selectRoom = (id: string) => {
    setActiveId(id);
    setMobileShowChat(true);
    setShowFindModal(false);
    if (!embedded) router.replace(`/collaboration?room=${id}`);
  };

  const backToRooms = () => {
    setMobileShowChat(false);
    if (!embedded) router.replace("/collaboration");
  };

  const send = async () => {
    if (!activeId || !text.trim()) return;
    setBusy(true);
    try {
      await api.postCollabMessage(activeId, { body: text.trim() });
      if (wsConnected && realtimeRef.current) {
        realtimeRef.current.sendTyping(activeId, false, myUsername);
      } else {
        void api.postCollabTyping(activeId, false, myUsername).catch(() => undefined);
      }
      setText("");
      onRequestSuccess();
      await loadMessages(activeId);
      patchFirmChatDiagnostics({
        messagesSent: getFirmChatDiagnostics().messagesSent + 1,
      });
    } catch (e) {
      handleChatError(e, "send");
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (file: File) => {
    if (!activeId) return;
    setBusy(true);
    try {
      const placeholder = await api.postCollabMessage(activeId, { body: `📎 ${file.name}` });
      const mid = placeholder.message?.message_id;
      if (mid) await api.uploadCollabAttachment(activeId, mid, file);
      await loadMessages(activeId);
    } catch (e) {
      handleChatError(e, "upload");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (searchQ.trim().length < 2) return;
    try {
      const r = await api.searchCollab(searchQ.trim());
      setSearchHits(r.rooms || []);
      setSearchMessageHits(r.messages || []);
    } catch {
      setSearchHits([]);
      setSearchMessageHits([]);
    }
  };

  const sendVoiceNote = async () => {
    if (!activeId || recording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      mediaRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (!blob.size) return;
        const tempId = `pending-voice-${Date.now()}`;
        const optimistic: api.CollabMessage = {
          message_id: tempId,
          room_id: activeId,
          sender_id: myId,
          sender_name: myUsername || "You",
          body: "Voice note",
          message_type: "voice",
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, optimistic]);
        setVoiceUploadPct(0);
        setRecording(false);
        try {
          const placeholder = await api.postCollabMessage(activeId, {
            body: "Voice note",
            message_type: "voice",
          });
          const mid = placeholder.message?.message_id;
          if (mid) {
            await api.uploadCollabAttachmentWithProgress(
              activeId,
              mid,
              new File([blob], "voice-note.webm", { type: "audio/webm" }),
              (pct) => setVoiceUploadPct(pct)
            );
          }
          setMessages((prev) => prev.filter((m) => m.message_id !== tempId));
          await loadMessages(activeId);
          setStatusMsg("Voice note sent");
          onRequestSuccess();
        } catch (e) {
          setMessages((prev) => prev.filter((m) => m.message_id !== tempId));
          handleChatError(e, "voice");
        } finally {
          setVoiceUploadPct(null);
        }
      };
      setRecording(true);
      rec.start();
      window.setTimeout(() => {
        if (mediaRef.current?.state === "recording") mediaRef.current.stop();
      }, 60000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Microphone access denied");
      setRecording(false);
    }
  };

  const stopVoiceNote = () => {
    if (mediaRef.current?.state === "recording") mediaRef.current.stop();
  };

  const totalUnread = rooms.reduce((n, r) => n + (r.unread_count ?? 0), 0);
  const activeRoom = rooms.find((r) => r.room_id === activeId);
  const presenceOnline = new Set([...onlineIds, ...orgOnlineIds]);
  const displayRooms = searchHits.length ? searchHits : rooms;
  const isGroupRoom =
    activeRoom?.room_type === "channel" || activeRoom?.room_type === "matter";

  const practiceChannels = displayRooms.filter(
    (r) => r.room_type === "channel" && PRACTICE_SLUGS.has((r.slug || "").toLowerCase())
  );
  const firmChannels = displayRooms.filter(
    (r) => r.room_type === "channel" && !PRACTICE_SLUGS.has((r.slug || "").toLowerCase())
  );
  const roomSections = [
    { title: "Direct messages", rooms: displayRooms.filter((r) => r.room_type === "dm") },
    { title: "Matter channels", rooms: displayRooms.filter((r) => r.room_type === "matter") },
    { title: "Practice channels", rooms: practiceChannels },
    ...(firmChannels.length ? [{ title: "Firm channels", rooms: firmChannels }] : []),
  ];

  const messageGrouping = (index: number) => {
    const m = messages[index];
    const mine = isMessageMine(m, myId, myUsername);
    if (mine) return { showAvatar: false, showSenderLabel: false };
    const prev = messages[index - 1];
    const newBlock =
      !prev ||
      isMessageMine(prev, myId, myUsername) ||
      prev.sender_id !== m.sender_id ||
      firmChatDayKey(prev.created_at) !== firmChatDayKey(m.created_at);
    return { showAvatar: newBlock, showSenderLabel: newBlock && !isGroupRoom };
  };

  const mobileRoomOpen = Boolean(activeId) && mobileShowChat;

  return (
    <div className={`firm-chat-app ${embedded ? "firm-chat-app--embedded h-full" : ""}`}>
      {!embedded && (
        <header className="firm-chat-topbar shrink-0 flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-200/80 bg-white">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-slate-900 m-0 tracking-tight">{FIRM_CHAT_NAME}</h1>
            <p className="text-[11px] text-slate-500 m-0 truncate hidden sm:block">{FIRM_CHAT_TAGLINE}</p>
            <p className="text-[10px] text-emerald-700 font-medium m-0 mt-0.5 hidden md:block">
              {FIRM_CHAT_FREE_NOTE}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <FirmChatNotificationCenter onOpenRoom={(id) => selectRoom(id)} totalUnreadRooms={totalUnread} />
            <button
              type="button"
              className="text-xs font-medium px-3 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 hidden sm:inline-flex"
              onClick={() => setShowGuide((v) => !v)}
            >
              Help
            </button>
            <Button size="sm" onClick={() => setShowFindModal(true)} className="rounded-lg shadow-sm">
              <span className="hidden sm:inline">New message</span>
              <span className="sm:hidden">+</span>
            </Button>
          </div>
        </header>
      )}

      {embedded && (
        <div className="shrink-0 px-4 py-2 border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
          <strong className="text-slate-800">Case Chat</strong> — matter team only.{" "}
          <Link href="/collaboration" className="text-blue-600 font-medium hover:underline">
            Open Firm Chat
          </Link>
        </div>
      )}

      {showGuide && !embedded && (
        <FirmChatConnectGuide
          onFindSomeone={() => {
            dismissGuide();
            setShowFindModal(true);
          }}
          onDismiss={dismissGuide}
        />
      )}

      {rateLimitBanner && (
        <div className="px-4 py-2 shrink-0">
          <Alert variant="error">{rateLimitBanner}</Alert>
        </div>
      )}

      {err && !rateLimitBanner && (
        <div className="px-4 py-2 shrink-0">
          <Alert variant="error">{err}</Alert>
        </div>
      )}

      {statusMsg && (
        <div className="mx-4 mb-1 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200/80 text-xs text-emerald-900 shrink-0 flex items-center justify-between gap-2">
          <span>{statusMsg}</span>
          <button type="button" className="text-emerald-700 font-medium shrink-0" onClick={() => setStatusMsg("")}>
            OK
          </button>
        </div>
      )}

      <div className="firm-chat-body flex flex-1 min-h-0">
        <aside
          className={`firm-chat-sidebar shrink-0 flex-col border-r border-slate-200/80 bg-slate-50/90 ${
            embedded
              ? activeId
                ? "hidden"
                : "flex w-full"
              : `firm-chat-sidebar w-full md:w-[340px] ${mobileRoomOpen ? "hidden md:flex" : "flex"}`
          }`}
        >
          <div className="p-3 border-b border-slate-200/80 bg-white space-y-2">
            <div className="relative">
              <input
                className="w-full rounded-xl border border-slate-200 bg-slate-50/80 pl-3 pr-16 py-2.5 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
                placeholder="Search messages, matters, rooms…"
                value={searchQ}
                onChange={(e) => {
                  setSearchQ(e.target.value);
                  if (e.target.value.trim().length < 2) {
                    setSearchHits([]);
                    setSearchMessageHits([]);
                  }
                }}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
              />
              <button
                type="button"
                onClick={runSearch}
                className="absolute right-1 top-1 bottom-1 px-2.5 rounded-lg text-[11px] font-semibold text-blue-600 hover:bg-blue-50"
              >
                Go
              </button>
            </div>
            {!embedded && (
              <button
                type="button"
                onClick={() => setShowCreateChannel(true)}
                className="w-full text-xs font-semibold rounded-lg border border-dashed border-slate-300 text-slate-600 py-2 hover:bg-slate-50"
              >
                + Create practice channel
              </button>
            )}
            {searchMessageHits.length > 0 && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 max-h-32 overflow-y-auto le-scroll text-[11px]">
                {searchMessageHits.slice(0, 5).map((m) => (
                  <button
                    key={m.message_id}
                    type="button"
                    className="w-full text-left px-2 py-1.5 hover:bg-white border-b border-slate-100 last:border-0"
                    onClick={() => selectRoom(m.room_id)}
                  >
                    <span className="font-medium text-slate-700">{m.room_name}</span>
                    <span className="block text-slate-500 truncate">{m.body}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <FirmChatRoomSidebar
            sections={roomSections}
            activeId={activeId}
            onlineUserIds={presenceOnline}
            onSelect={selectRoom}
          />
        </aside>

        <main
          className={`firm-chat-main flex-1 flex-col min-w-0 min-h-0 bg-white ${
            embedded
              ? activeId
                ? "flex"
                : "hidden"
              : mobileRoomOpen
                ? "flex"
                : activeId
                  ? "hidden md:flex"
                  : "hidden md:flex"
          }`}
        >
          {!activeId ? (
            <FirmChatInboxHome rooms={displayRooms} onSelect={selectRoom} onNewMessage={() => setShowFindModal(true)} />
          ) : (
            <>
              <header className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-slate-200/80 bg-white">
                <button
                  type="button"
                  className="md:hidden shrink-0 h-9 w-9 flex items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
                  onClick={backToRooms}
                  aria-label="Back to conversations"
                >
                  ←
                </button>
                <FirmChatAvatar
                  name={activeRoom?.name || "Chat"}
                  seed={activeRoom?.peer_user_id || activeRoom?.room_id}
                  size="lg"
                  online={
                    activeRoom?.room_type === "dm" && activeRoom.peer_user_id
                      ? presenceOnline.has(activeRoom.peer_user_id)
                      : undefined
                  }
                />
                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-bold text-slate-900 m-0 truncate leading-tight">
                    {activeRoom?.name || "Conversation"}
                  </h2>
                  <p className="text-xs text-slate-500 m-0 flex items-center gap-2 flex-wrap">
                    {activeRoom?.room_type === "dm" && roomContext?.peer ? (
                      <span className="text-emerald-700 font-medium">
                        {roomContext.peer.online
                          ? "Online now"
                          : formatLastSeen(roomContext.peer.last_seen)}
                      </span>
                    ) : (
                      <>
                        {roomTypeLabel(activeRoom)}
                        {onlineIds.size > 0 && (
                          <span className="text-emerald-700">{onlineIds.size} in room</span>
                        )}
                      </>
                    )}
                  </p>
                  {typingUsers.length > 0 && (
                    <p className="text-xs text-blue-600 font-medium m-0 mt-0.5 animate-pulse">
                      {typingUsers.map((t) => t.display_name || "Someone").join(", ")} typing…
                    </p>
                  )}
                </div>
              </header>

              <div className="flex-1 overflow-y-auto le-scroll firm-chat-thread px-3 sm:px-6 py-4 group/firm-msg">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <p className="text-sm font-medium text-slate-700 m-0">Start the conversation</p>
                    <p className="text-xs text-slate-500 mt-1 m-0 max-w-xs">
                      Your messages appear on the right. Teammates appear on the left.
                    </p>
                  </div>
                )}
                {messages.map((m, i) => {
                  const dayKey = firmChatDayKey(m.created_at);
                  const prevDay = i > 0 ? firmChatDayKey(messages[i - 1].created_at) : "";
                  const mine = isMessageMine(m, myId, myUsername);
                  const { showAvatar, showSenderLabel } = messageGrouping(i);
                  return (
                    <div key={m.message_id} className={showAvatar ? "mt-3" : "mt-0.5"}>
                      {dayKey !== prevDay && <FirmChatDayDivider label={formatDayLabel(m.created_at)} />}
                      <FirmChatMessage
                        message={m}
                        isMine={mine}
                        showAvatar={showAvatar}
                        showSenderLabel={showSenderLabel}
                        isGroupRoom={isGroupRoom}
                        onReact={(emoji) =>
                          api
                            .addCollabReaction(activeId, m.message_id, emoji)
                            .then(() => loadMessages(activeId))
                        }
                        onCreateTask={
                          activeRoom?.matter_id
                            ? async () => {
                                try {
                                  await api.createTaskFromCollabMessage(m.message_id, {
                                    title: m.body.slice(0, 120),
                                  });
                                  setStatusMsg("Task added to this case");
                                } catch (e) {
                                  setErr(e instanceof Error ? e.message : "Task failed");
                                }
                              }
                            : undefined
                        }
                        onCreateDeadline={
                          activeRoom?.matter_id
                            ? async () => {
                                const due = window.prompt("Due date (YYYY-MM-DD):");
                                if (!due) return;
                                try {
                                  await api.createDeadlineFromCollabMessage(m.message_id, {
                                    due_date: due,
                                    title: m.body.slice(0, 120),
                                  });
                                  setStatusMsg("Deadline added");
                                } catch (e) {
                                  setErr(e instanceof Error ? e.message : "Deadline failed");
                                }
                              }
                            : undefined
                        }
                      />
                    </div>
                  );
                })}
                <div ref={bottomRef} className="h-2" />
              </div>

              <div className="shrink-0 border-t border-slate-200/80 bg-white px-3 sm:px-4 py-3 safe-area-pb">
                {voiceUploadPct != null && (
                  <div className="max-w-3xl mx-auto mb-2">
                    <div className="h-1.5 rounded-full bg-slate-200 overflow-hidden">
                      <div
                        className="h-full bg-slate-500 transition-all duration-200"
                        style={{ width: `${voiceUploadPct}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-slate-500 m-0 mt-1">Uploading voice note… {voiceUploadPct}%</p>
                  </div>
                )}
                <div className="firm-chat-composer flex items-end gap-2 max-w-3xl mx-auto">
                  <button
                    type="button"
                    className={`shrink-0 h-11 w-11 flex items-center justify-center rounded-xl border transition-colors ${
                      recording
                        ? "border-red-300 bg-red-50 text-red-600 animate-pulse"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                    onClick={() => (recording ? stopVoiceNote() : void sendVoiceNote())}
                    aria-label={recording ? "Stop recording" : "Record voice note"}
                    title={recording ? "Stop (max 60s)" : "Voice note"}
                  >
                    <VoiceMicIcon active={recording} size={20} />
                  </button>
                  <button
                    type="button"
                    className="shrink-0 h-11 w-11 flex items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-colors"
                    onClick={() => fileRef.current?.click()}
                    aria-label="Attach file"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                    </svg>
                  </button>
                  <input
                    ref={fileRef}
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void onFile(f);
                      e.target.value = "";
                    }}
                  />
                  <div className="flex-1 rounded-2xl border border-slate-200 bg-slate-50/50 focus-within:ring-2 focus-within:ring-blue-500/25 focus-within:border-blue-400">
                    <textarea
                      className="w-full bg-transparent border-0 resize-none text-sm text-slate-900 placeholder:text-slate-400 px-4 py-3 min-h-[44px] max-h-28 focus:outline-none focus:ring-0"
                      rows={1}
                      placeholder={
                        isGroupRoom ? "Message the team… use @username to mention" : "Write a message…"
                      }
                      value={text}
                      onChange={(e) => {
                        setText(e.target.value);
                        if (!activeId) return;
                        if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
                        if (wsConnected && realtimeRef.current) {
                          realtimeRef.current.sendTyping(activeId, true, myUsername);
                        } else {
                          void api.postCollabTyping(activeId, true, myUsername).catch(() => undefined);
                        }
                        typingTimerRef.current = setTimeout(() => {
                          if (wsConnected && realtimeRef.current) {
                            realtimeRef.current.sendTyping(activeId, false, myUsername);
                          } else {
                            void api.postCollabTyping(activeId, false, myUsername).catch(() => undefined);
                          }
                        }, 2500);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      disabled={busy}
                    />
                  </div>
                  <Button
                    onClick={send}
                    disabled={busy || !text.trim()}
                    className="shrink-0 h-11 px-5 rounded-xl shadow-sm"
                  >
                    Send
                  </Button>
                </div>
              </div>
            </>
          )}
        </main>

        {!embedded && (
          <FirmChatMatterPanel room={activeRoom} context={roomContext} loading={contextLoading} />
        )}
      </div>

      <FirmChatCreateChannelModal
        open={showCreateChannel}
        onClose={() => setShowCreateChannel(false)}
        onCreated={(id) => {
          void loadRooms();
          selectRoom(id);
          setStatusMsg("Practice channel created");
        }}
      />

      {showFindModal && (
        <div
          className="firm-chat-modal fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-900/40 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-label="Find someone to chat"
          onClick={() => setShowFindModal(false)}
        >
          <div
            className="w-full sm:max-w-lg max-h-[90dvh] overflow-y-auto le-scroll bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white rounded-t-2xl sm:rounded-t-2xl">
              <h3 className="text-sm font-semibold text-slate-900 m-0">New message</h3>
              <button
                type="button"
                className="h-8 w-8 rounded-lg hover:bg-slate-100 text-slate-500"
                onClick={() => setShowFindModal(false)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="p-4">
              <FirmChatUserSearch
                onOpenRoom={(id) => {
                  selectRoom(id);
                  setStatusMsg("Conversation opened");
                }}
                onStatusMessage={(msg) => {
                  setStatusMsg(msg);
                  setErr("");
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
