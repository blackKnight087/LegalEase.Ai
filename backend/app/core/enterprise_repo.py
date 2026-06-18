"""Repository layer — DB-backed deal rooms, witness sessions, judgments."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func

from .db import init_db, session_scope
from .orm_models import DealRoom, DealRoomDocument, Judgment, WitnessMessage, WitnessSession


def ensure_enterprise_db() -> None:
    init_db()
    try:
        from .judgment_seed import seed_judgments_if_empty

        seed_judgments_if_empty()
    except Exception:
        pass


# ---------- Deal rooms ----------


def create_deal_room(user_id: str, name: str, description: str = "") -> Dict[str, Any]:
    ensure_enterprise_db()
    with session_scope() as db:
        room = DealRoom(user_id=str(user_id), name=name or "Deal Room", description=description or "")
        db.add(room)
        db.flush()
        return {"room_id": room.id, "name": room.name}


def list_deal_rooms(user_id: str) -> List[Dict[str, Any]]:
    ensure_enterprise_db()
    with session_scope() as db:
        rooms = db.query(DealRoom).filter(DealRoom.user_id == str(user_id)).all()
        out = []
        for r in rooms:
            cnt = db.query(DealRoomDocument).filter(DealRoomDocument.room_id == r.id).count()
            out.append({"room_id": r.id, "name": r.name, "document_count": cnt})
        return out


def get_deal_room(room_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ensure_enterprise_db()
    with session_scope() as db:
        q = db.query(DealRoom).filter(DealRoom.id == room_id)
        if user_id:
            q = q.filter(DealRoom.user_id == str(user_id))
        room = q.first()
        if not room:
            return None
        return {"id": room.id, "name": room.name, "user_id": room.user_id}


def add_documents_to_room(
    room_id: str,
    documents: List[Dict[str, str]],
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_enterprise_db()
    with session_scope() as db:
        q = db.query(DealRoom).filter(DealRoom.id == room_id)
        if user_id:
            q = q.filter(DealRoom.user_id == str(user_id))
        room = q.first()
        if not room:
            return {"error": "Deal room not found"}
        for doc in documents:
            db.add(
                DealRoomDocument(
                    room_id=room_id,
                    filename=doc.get("filename", "document"),
                    text_content=(doc.get("text") or "")[:100000],
                    file_path=doc.get("file_path", ""),
                    faiss_pointer=doc.get("faiss_pointer", ""),
                    meta_tags=doc.get("meta_tags", ""),
                )
            )
        cnt = db.query(DealRoomDocument).filter(DealRoomDocument.room_id == room_id).count()
        return {"room_id": room_id, "document_count": cnt}


def load_room_documents(room_id: str) -> List[Dict[str, str]]:
    ensure_enterprise_db()
    with session_scope() as db:
        docs = db.query(DealRoomDocument).filter(DealRoomDocument.room_id == room_id).all()
        return [
            {
                "id": d.id,
                "filename": d.filename,
                "text": d.text_content,
                "file_path": d.file_path,
            }
            for d in docs
        ]


# ---------- Witness ----------


def create_witness_session(
    user_id: str,
    witness_name: str,
    background_text: str,
    disposition: str = "evasive",
    cross_examination_notes: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_db()
    disp = disposition if disposition in ("cooperative", "evasive", "defensive", "hostile") else "evasive"
    with session_scope() as db:
        sess = WitnessSession(
            user_id=str(user_id),
            witness_name=witness_name or "Witness",
            disposition=disp,
            background_text=(background_text or "")[:20000],
            cross_notes=(cross_examination_notes or "")[:8000],
        )
        db.add(sess)
        db.flush()
        return {
            "session_id": sess.id,
            "witness_name": sess.witness_name,
            "disposition": disp,
            "message": (
                f"Witness simulation ready. You are cross-examining {sess.witness_name}. "
                f"Disposition: {disp}. Ask your first question."
            ),
        }


def get_witness_session(session_id: str) -> Optional[Dict[str, Any]]:
    ensure_enterprise_db()
    with session_scope() as db:
        sess = db.query(WitnessSession).filter(WitnessSession.id == session_id).first()
        if not sess:
            return None
        msgs = (
            db.query(WitnessMessage)
            .filter(WitnessMessage.session_id == session_id)
            .order_by(WitnessMessage.created_at)
            .all()
        )
        return {
            "id": sess.id,
            "witness_name": sess.witness_name,
            "background": sess.background_text,
            "disposition": sess.disposition,
            "cross_notes": sess.cross_notes,
            "history": [{"role": m.role, "content": m.content} for m in msgs],
        }


def append_witness_message(session_id: str, role: str, content: str) -> None:
    ensure_enterprise_db()
    with session_scope() as db:
        db.add(WitnessMessage(session_id=session_id, role=role, content=content))


def list_witness_sessions(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_enterprise_db()
    with session_scope() as db:
        rows = (
            db.query(WitnessSession)
            .filter(WitnessSession.user_id == str(user_id))
            .order_by(WitnessSession.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "session_id": r.id,
                "witness_name": r.witness_name,
                "disposition": r.disposition,
            }
            for r in rows
        ]


# ---------- Judgments analytics ----------


def judge_disposition_stats(
    judge_name: str = "",
    section: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_db()
    with session_scope() as db:
        q = db.query(
            Judgment.disposition_outcome,
            func.count(Judgment.id),
        )
        if judge_name:
            q = q.filter(Judgment.judge_name.ilike(f"%{judge_name}%"))
        if section:
            q = q.filter(Judgment.statute_section.ilike(f"%{section}%"))
        rows = q.group_by(Judgment.disposition_outcome).all()
        total = sum(r[1] for r in rows) or 1
        breakdown = [{"outcome": r[0], "count": r[1], "pct": round(100 * r[1] / total, 1)} for r in rows]
        bail = sum(r[1] for r in rows if "bail" in (r[0] or "").lower() and "denied" not in (r[0] or "").lower())
        bail_denied = sum(r[1] for r in rows if "bail denied" in (r[0] or "").lower())
        bail_total = bail + bail_denied or 1
        return {
            "judge": judge_name or "All judges",
            "section": section or "All sections",
            "sample_size": total,
            "bail_grant_rate_pct": round(100 * bail / bail_total, 1),
            "disposition_breakdown": breakdown,
            "data_source": "judgments_database",
        }


def precedent_relations_for_landmark(landmark: str, limit: int = 30) -> List[Dict[str, Any]]:
    ensure_enterprise_db()
    with session_scope() as db:
        rows = (
            db.query(Judgment)
            .filter(Judgment.landmark_citation.ilike(f"%{landmark[:40]}%"))
            .limit(limit)
            .all()
        )
        if not rows:
            rows = db.query(Judgment).limit(limit).all()
        return [
            {
                "citation": r.citation,
                "relation": r.relation_to_landmark,
                "outcome": r.disposition_outcome,
                "judge": r.judge_name,
                "year": r.year,
            }
            for r in rows
        ]
