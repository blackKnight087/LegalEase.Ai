"""Collaboration Hub API — firm-internal messaging."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.auth_sse import _user_from_token, get_current_user_sse
from ....core.collab_realtime import get_hub
from ....core.collab_rbac import collab_permissions, require_collab_perm
from ....core.collab_schema import ensure_collab_schema
from ....core.collab_service import (
    accept_chat_request,
    add_reaction,
    create_channel,
    create_deadline_from_message,
    create_task_from_message,
    get_attachment_path,
    get_or_create_dm,
    get_room,
    ensure_matter_room,
    list_chat_requests,
    list_messages,
    list_notifications,
    list_rooms,
    mark_notification_read,
    mark_room_read,
    reject_chat_request,
    save_attachment,
    search_collab,
    search_users_by_username,
    send_chat_request,
    send_message,
    room_activity_stats,
    room_context_panel,
    summarize_room,
)
from ....core.collab_service import list_collab_members
from ....core.org_service import get_primary_org_id

router = APIRouter(tags=["collaboration"])


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=20000)
    parent_id: str = ""
    message_type: str = "text"


class DmCreate(BaseModel):
    peer_user_id: str = Field(..., min_length=1)


class ChatRequestCreate(BaseModel):
    to_user_id: str = Field(..., min_length=1)
    intro_message: str = Field(default="", max_length=500)


class ChannelCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=60)
    name: str = Field(..., min_length=2, max_length=120)
    description: str = ""


class ReactionCreate(BaseModel):
    emoji: str = Field(default="👍", max_length=16)


class TaskFromMessage(BaseModel):
    title: str = ""
    assignee: str = ""
    due_date: str = ""
    priority: str = "Medium"


class DeadlineFromMessage(BaseModel):
    title: str = ""
    due_date: str = Field(..., min_length=4)
    deadline_type: str = "filing"
    notes: str = ""


class PresenceHeartbeat(BaseModel):
    room_id: str = ""
    display_name: str = ""


class TypingUpdate(BaseModel):
    room_id: str = Field(..., min_length=1)
    typing: bool = True
    display_name: str = ""


@router.post("/presence")
def collab_presence_heartbeat(
    body: PresenceHeartbeat,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    from ....core.collab_presence import heartbeat

    org_id = get_primary_org_id(str(user["id"])) or ""
    return heartbeat(
        str(user["id"]),
        org_id,
        room_id=body.room_id,
        display_name=body.display_name or str(user.get("username") or ""),
    )


@router.get("/presence")
def collab_presence_list(
    room_id: str = Query(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    from ....core.collab_presence import list_online

    org_id = get_primary_org_id(str(user["id"])) or ""
    return {"online": list_online(org_id, room_id=room_id)}


@router.post("/typing")
def collab_typing_update(
    body: TypingUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    from ....core.collab_presence import list_typing, set_typing
    from ....core.collab_realtime import publish_typing

    org_id = get_primary_org_id(str(user["id"])) or ""
    if not get_room(str(user["id"]), body.room_id):
        raise HTTPException(404, "Room not found")
    out = set_typing(
        str(user["id"]),
        org_id,
        room_id=body.room_id,
        display_name=body.display_name or str(user.get("username") or ""),
        typing=body.typing,
    )
    typing_list = list_typing(org_id, body.room_id, exclude_user_id=str(user["id"]))
    publish_typing(body.room_id, typing_list)
    return out


@router.get("/rooms/{room_id}/typing")
def collab_typing_list(
    room_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    from ....core.collab_presence import list_typing

    org_id = get_primary_org_id(str(user["id"])) or ""
    if not get_room(str(user["id"]), room_id):
        raise HTTPException(404, "Room not found")
    return {
        "typing": list_typing(org_id, room_id, exclude_user_id=str(user["id"])),
    }


@router.get("/rooms/{room_id}/context")
def collab_room_context(room_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    try:
        return room_context_panel(str(user["id"]), room_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@router.get("/permissions")
def collab_permissions_route(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_collab_schema()
    return {"permissions": collab_permissions(user)}


@router.get("/members")
def collab_members(user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    return {"members": list_collab_members(str(user["id"]))}


@router.get("/rooms")
def collab_list_rooms(user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    ensure_collab_schema()
    return {"rooms": list_rooms(str(user["id"]))}


@router.get("/users/search")
def collab_search_users(
    q: str = Query("", min_length=0),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    ensure_collab_schema()
    return search_users_by_username(
        str(user["id"]),
        q,
        your_username=str(user.get("username") or ""),
    )


@router.get("/requests")
def collab_list_requests(user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    ensure_collab_schema()
    return list_chat_requests(str(user["id"]))


@router.post("/requests")
def collab_send_request(
    body: ChatRequestCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "dm")
    try:
        result = send_chat_request(
            str(user["id"]),
            body.to_user_id,
            intro_message=body.intro_message,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return result


@router.post("/requests/{request_id}/accept")
def collab_accept_request(
    request_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "dm")
    try:
        return accept_chat_request(str(user["id"]), request_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/requests/{request_id}/reject")
def collab_reject_request(
    request_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "dm")
    try:
        return reject_chat_request(str(user["id"]), request_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@router.post("/rooms/dm")
def collab_dm(body: DmCreate, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "dm")
    try:
        room = get_or_create_dm(str(user["id"]), body.peer_user_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"room": room}


@router.post("/rooms/channel")
def collab_channel(body: ChannelCreate, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "create_channel")
    try:
        room = create_channel(
            str(user["id"]),
            slug=body.slug,
            name=body.name,
            description=body.description,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"room": room}


@router.get("/rooms/matter/{matter_id}")
def collab_matter_room(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    try:
        room = ensure_matter_room(str(user["id"]), matter_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return {"room": room}


@router.get("/rooms/{room_id}")
def collab_get_room(room_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    room = get_room(str(user["id"]), room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return {"room": room}


@router.get("/rooms/{room_id}/stats")
def collab_room_stats(room_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    try:
        return room_activity_stats(str(user["id"]), room_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@router.get("/rooms/{room_id}/messages")
def collab_messages(
    room_id: str,
    before: str = "",
    since: str = "",
    limit: int = Query(50, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    try:
        msgs = list_messages(
            str(user["id"]), room_id, before=before, since=since, limit=limit
        )
        mark_room_read(str(user["id"]), room_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return {"messages": msgs}


async def collab_room_event_stream(
    user_id: str,
    room_id: str,
    since: str = "",
    *,
    poll_interval: float = 2.0,
):
    """Async generator of SSE frames for room messages."""
    cursor = since
    yield f"event: connected\ndata: {json.dumps({'room_id': room_id})}\n\n"
    while True:
        try:
            msgs = list_messages(user_id, room_id, since=cursor, limit=50)
        except PermissionError:
            yield f"event: error\ndata: {json.dumps({'detail': 'Forbidden'})}\n\n"
            break
        for m in msgs:
            yield f"event: message\ndata: {json.dumps(m)}\n\n"
            if m.get("created_at"):
                cursor = m["created_at"]
        await asyncio.sleep(poll_interval)


@router.get("/rooms/{room_id}/stream")
async def collab_room_stream(
    room_id: str,
    since: str = "",
    user: Dict[str, Any] = Depends(get_current_user_sse),
):
    """SSE stream of new room messages (polls every 2s). Auth via Bearer or access_token query."""
    require_collab_perm(user, "view")
    return StreamingResponse(
        collab_room_event_stream(str(user["id"]), room_id, since),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/rooms/{room_id}/messages")
def collab_post_message(
    room_id: str,
    body: MessageCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "post")
    try:
        msg = send_message(
            str(user["id"]),
            room_id,
            body=body.body,
            message_type=body.message_type,
            parent_id=body.parent_id,
        )
    except ValueError as e:
        raise HTTPException(429, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    from ....core.collab_realtime import publish_message

    publish_message(room_id, msg)
    return {"message": msg}


@router.post("/rooms/{room_id}/read")
def collab_mark_read(room_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    from ....core.collab_realtime import publish_read

    try:
        mark_room_read(str(user["id"]), room_id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    publish_read(room_id, str(user["id"]))
    return {"ok": True}


@router.post("/rooms/{room_id}/messages/{message_id}/reactions")
def collab_reaction(
    room_id: str,
    message_id: str,
    body: ReactionCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "post")
    try:
        return add_reaction(str(user["id"]), message_id, body.emoji)
    except (PermissionError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/rooms/{room_id}/messages/{message_id}/attachments")
async def collab_upload(
    room_id: str,
    message_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "upload")
    content = await file.read()
    max_mb = int(os.getenv("COLLAB_ATTACHMENT_MAX_MB", "50"))
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {max_mb}MB)")
    try:
        att = save_attachment(
            str(user["id"]),
            room_id,
            message_id,
            filename=file.filename or "upload",
            content=content,
            mime_type=file.content_type or "",
        )
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    from ....core.collab_realtime import publish_message
    from ....core.collab_service import list_messages

    msgs = list_messages(str(user["id"]), room_id, limit=5)
    for m in msgs:
        if m.get("message_id") == message_id:
            publish_message(room_id, m)
            break
    return {"attachment": att, "upload_complete": True}


@router.get("/attachments/{attachment_id}/download")
def collab_download(attachment_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    require_collab_perm(user, "view")
    path_info = get_attachment_path(str(user["id"]), attachment_id)
    if not path_info:
        raise HTTPException(404, "Attachment not found")
    filename, path = path_info
    return FileResponse(path, filename=filename)


@router.post("/messages/{message_id}/create-task")
def collab_create_task(
    message_id: str,
    body: TaskFromMessage,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "create_task")
    try:
        return create_task_from_message(
            str(user["id"]),
            message_id,
            title=body.title,
            assignee=body.assignee,
            due_date=body.due_date,
            priority=body.priority,
        )
    except (PermissionError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/messages/{message_id}/create-deadline")
def collab_create_deadline(
    message_id: str,
    body: DeadlineFromMessage,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "create_deadline")
    try:
        return create_deadline_from_message(
            str(user["id"]),
            message_id,
            title=body.title,
            due_date=body.due_date,
            deadline_type=body.deadline_type,
            notes=body.notes,
        )
    except (PermissionError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/search")
def collab_search(
    q: str = Query(..., min_length=2),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    return search_collab(str(user["id"]), q)


@router.get("/notifications")
def collab_notifications(
    unread_only: bool = False,
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "view")
    return {"notifications": list_notifications(str(user["id"]), unread_only=unread_only)}


@router.post("/notifications/{notification_id}/read")
def collab_notif_read(notification_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    mark_notification_read(str(user["id"]), notification_id)
    return {"ok": True}


@router.post("/rooms/{room_id}/summarize")
def collab_summarize(
    room_id: str,
    limit: int = Query(100, ge=10, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
):
    require_collab_perm(user, "summarize")
    try:
        return summarize_room(str(user["id"]), room_id, limit=limit)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@router.websocket("/ws")
async def collab_websocket(
    websocket: WebSocket,
    access_token: str = Query(""),
):
    """Realtime Firm Chat — messages, typing, presence, notifications."""
    if not access_token.strip():
        await websocket.close(code=4401)
        return
    try:
        user = _user_from_token(access_token.strip())
    except HTTPException:
        await websocket.close(code=4401)
        return
    require_collab_perm(user, "view")
    from ....core.collab_presence import heartbeat, list_online, list_typing, set_typing

    uid = str(user["id"])
    org_id = get_primary_org_id(uid) or ""
    hub = get_hub()
    await hub.connect(websocket, uid, org_id)
    await websocket.send_json(
        {"type": "connected", "user_id": uid}
    )
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg_type = str(data.get("type", ""))
            room_id = str(data.get("room_id", ""))
            if msg_type == "subscribe" and room_id:
                if get_room(uid, room_id):
                    await hub.subscribe_room(websocket, room_id)
                    await websocket.send_json({"type": "subscribed", "room_id": room_id})
            elif msg_type == "presence":
                heartbeat(
                    uid,
                    org_id,
                    room_id=room_id,
                    display_name=str(data.get("display_name") or user.get("username") or ""),
                )
                if room_id:
                    online = list_online(org_id, room_id=room_id)
                    await websocket.send_json(
                        {"type": "presence", "room_id": room_id, "online": online}
                    )
            elif msg_type == "typing" and room_id:
                set_typing(
                    uid,
                    org_id,
                    room_id=room_id,
                    display_name=str(data.get("display_name") or user.get("username") or ""),
                    typing=bool(data.get("typing", True)),
                )
                typing_list = list_typing(org_id, room_id, exclude_user_id=uid)
                from ....core.collab_realtime import publish_typing

                publish_typing(room_id, typing_list)
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)


@router.get("/debug/realtime")
def collab_debug_realtime(user: Dict[str, Any] = Depends(get_current_user)):
    """Developer diagnostics — websocket hub + rate limit rules."""
    require_collab_perm(user, "view")
    from ....middleware.rate_limit import rate_limit_audit_report

    return {
        "hub": get_hub().stats(),
        "rate_limits": rate_limit_audit_report(),
    }
