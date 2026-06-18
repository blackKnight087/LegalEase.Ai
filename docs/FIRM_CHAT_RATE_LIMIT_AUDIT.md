# Firm Chat — Rate Limit Audit

Last updated: 2026-06-02

## Summary

Firm Chat and voice APIs are **fully exempt** from the global HTTP rate limiter when `RATE_LIMIT_COLLAB_EXEMPT=1` (default). Auth-sensitive endpoints remain protected. Real-time updates use **WebSocket** (`/api/v1/collaboration/ws`) with SSE/polling as fallback.

## Active limiters

| Rule ID | Limit (per minute) | Applies to | Exempt when |
|---------|-------------------|------------|-------------|
| `global` | `RATE_LIMIT_PER_MINUTE` (default 180) | All other API routes | — |
| `auth_sensitive` | `RATE_LIMIT_AUTH_PER_MINUTE` (default 20) | Login, register, forgot/reset password, org invite | Never |
| `ai_chat` | `RATE_LIMIT_CHAT_PER_MINUTE` (default 80) | `/api/v1/chat/*` | `RATE_LIMIT_CHAT_EXEMPT=1` |
| `scope_promotion` | `RATE_LIMIT_SCOPE_PROMOTION_PER_MINUTE` (12) | Learning scope promote | Never |
| `collab_message_post` | `RATE_LIMIT_COLLAB_MESSAGE_PER_MINUTE` (100) | POST `.../collaboration/rooms/.../messages` | `RATE_LIMIT_COLLAB_EXEMPT=1` |

## Fully exempt paths (no 429 from middleware)

All routes under:

- `/api/v1/collaboration/*` — rooms, messages, read, typing, presence, notifications, stream, WebSocket, attachments, search, context
- `/api/v1/speech/*` — voice transcription (when enabled)

Health, document job status, and KB health paths are also exempt (see `rate_limit.py`).

## Not rate-limited by design (chat operations)

- Opening conversations / listing rooms
- Reading messages / history
- Switching rooms
- Notifications list
- Typing indicators
- Presence heartbeats
- Read receipts
- WebSocket events
- Message sync (SSE fallback, 30s poll only when WS down)

## Spam protection (not HTTP 429)

- Duplicate identical message within **2 seconds** per user+room → HTTP 400 with friendly message
- No hard cap on normal send volume when collab exempt is on

## 429 logging

When a 429 is returned, the backend logs (throttled to once per 5s per client+path):

- `path`, `method`, `client` (hashed user or IP), `count`, `limit`, `rule`

Response headers: `X-RateLimit-Rule`, `X-RateLimit-Limit`

## Frontend

- Rate-limit banner: only on genuine 429, auto-hides after **5 seconds**, clears on next successful request, session diagnostics in **Firm Chat diagnostics** panel (dev / `NEXT_PUBLIC_FIRM_CHAT_DEBUG=1`)
- Polling reduced: notifications 45s; typing/presence HTTP fallback only when WebSocket disconnected

## Environment

```env
RATE_LIMIT_ENABLED=1
RATE_LIMIT_PER_MINUTE=180
RATE_LIMIT_COLLAB_EXEMPT=1
RATE_LIMIT_CHAT_EXEMPT=1
RATE_LIMIT_COLLAB_MESSAGE_PER_MINUTE=100
RATE_LIMIT_AUTH_PER_MINUTE=20
RATE_LIMIT_LOG_429=1
COLLAB_ATTACHMENT_MAX_MB=50
```

Restart backend after changing `.env`.

## Diagnostics API

`GET /api/v1/collaboration/debug/realtime` — WebSocket hub stats + active rate-limit rules (authenticated).
