"use client";

import { getApiBase } from "@/lib/api";
import * as api from "@/lib/api";
import { getFirmChatDiagnostics, patchFirmChatDiagnostics } from "@/lib/firmChatDiagnostics";

export type CollabRealtimeEvent =
  | { type: "message"; room_id: string; payload: api.CollabMessage }
  | { type: "typing"; room_id: string; typing: Array<{ user_id?: string; display_name?: string }> }
  | { type: "presence"; room_id: string; online: Array<{ user_id?: string; display_name?: string }> }
  | { type: "read"; room_id: string; user_id: string; seen_by?: string[] }
  | { type: "notification"; payload: Record<string, unknown> }
  | { type: "connected" | "subscribed" | "pong" };

export function collabWebSocketUrl(): string {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("legalease_token") : null;
  const path = `/api/v1/collaboration/ws${token ? `?access_token=${encodeURIComponent(token)}` : ""}`;
  if (typeof window === "undefined") return path;
  const base = getApiBase();
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = base ? new URL(base).host : window.location.host;
  return `${proto}//${host}${path}`;
}

type Handlers = {
  onMessage?: (roomId: string, msg: api.CollabMessage) => void;
  onTyping?: (roomId: string, typing: Array<{ user_id?: string; display_name?: string }>) => void;
  onPresence?: (roomId: string, online: Array<{ user_id?: string; display_name?: string }>) => void;
  onNotification?: (payload: Record<string, unknown>) => void;
  onRead?: (roomId: string, userId: string) => void;
  onStateChange?: (state: "connecting" | "connected" | "disconnected" | "error") => void;
};

export class FirmChatRealtimeClient {
  private ws: WebSocket | null = null;
  private roomId = "";
  private handlers: Handlers = {};
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private closed = false;
  private lastPing = 0;

  constructor(handlers: Handlers) {
    this.handlers = handlers;
  }

  connect() {
    this.closed = false;
    patchFirmChatDiagnostics({ wsState: "connecting" });
    this.handlers.onStateChange?.("connecting");
    try {
      this.ws = new WebSocket(collabWebSocketUrl());
    } catch {
      patchFirmChatDiagnostics({ wsState: "error" });
      this.handlers.onStateChange?.("error");
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      patchFirmChatDiagnostics({ wsState: "connected" });
      this.handlers.onStateChange?.("connected");
      if (this.roomId) this.subscribe(this.roomId);
      this.pingTimer = setInterval(() => this.ping(), 25000);
    };
    this.ws.onmessage = (ev) => this.handleRaw(ev.data);
    this.ws.onerror = () => {
      patchFirmChatDiagnostics({ wsState: "error" });
      this.handlers.onStateChange?.("error");
    };
    this.ws.onclose = () => {
      if (this.pingTimer) clearInterval(this.pingTimer);
      patchFirmChatDiagnostics({ wsState: "disconnected" });
      this.handlers.onStateChange?.("disconnected");
      if (!this.closed) {
        const prev = getFirmChatDiagnostics();
        patchFirmChatDiagnostics({ reconnects: prev.reconnects + 1 });
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), 3000);
  }

  disconnect() {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.ws?.close();
    this.ws = null;
  }

  subscribe(roomId: string) {
    this.roomId = roomId;
    this.send({ type: "subscribe", room_id: roomId });
  }

  sendPresence(roomId: string, displayName: string) {
    this.send({ type: "presence", room_id: roomId, display_name: displayName });
  }

  sendTyping(roomId: string, typing: boolean, displayName: string) {
    this.send({ type: "typing", room_id: roomId, typing, display_name: displayName });
  }

  private ping() {
    this.lastPing = Date.now();
    this.send({ type: "ping" });
  }

  private send(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private handleRaw(raw: string) {
    let data: CollabRealtimeEvent & Record<string, unknown>;
    try {
      data = JSON.parse(raw) as CollabRealtimeEvent & Record<string, unknown>;
    } catch {
      return;
    }
    patchFirmChatDiagnostics({ lastEventType: String(data.type || "") });
    if (data.type === "pong" && this.lastPing) {
      patchFirmChatDiagnostics({ wsLatencyMs: Date.now() - this.lastPing });
    }
    if (data.type === "message" && data.room_id && data.payload) {
      const prev = getFirmChatDiagnostics();
      patchFirmChatDiagnostics({ messagesReceived: prev.messagesReceived + 1 });
      this.handlers.onMessage?.(data.room_id, data.payload as api.CollabMessage);
    } else if (data.type === "typing" && data.room_id) {
      this.handlers.onTyping?.(
        data.room_id,
        (data as { typing?: Array<{ user_id?: string; display_name?: string }> }).typing || []
      );
    } else if (data.type === "presence" && data.room_id) {
      this.handlers.onPresence?.(
        data.room_id,
        (data as { online?: Array<{ user_id?: string; display_name?: string }> }).online || []
      );
    } else if (data.type === "notification" && data.payload) {
      this.handlers.onNotification?.(data.payload as Record<string, unknown>);
    } else if (data.type === "read" && data.room_id) {
      this.handlers.onRead?.(data.room_id, String(data.user_id || ""));
    }
  }
}
