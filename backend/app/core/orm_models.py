"""Enterprise ORM models — immutable persistence for analytics and enterprise features."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DealRoom(Base):
    __tablename__ = "deal_rooms"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    documents = relationship("DealRoomDocument", back_populates="room", cascade="all, delete-orphan")


class DealRoomDocument(Base):
    __tablename__ = "deal_room_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    room_id = Column(String(36), ForeignKey("deal_rooms.id"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    text_content = Column(Text, default="")
    file_path = Column(String(1024), default="")
    faiss_pointer = Column(String(255), default="")
    meta_tags = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)

    room = relationship("DealRoom", back_populates="documents")


class WitnessSession(Base):
    __tablename__ = "witness_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(64), nullable=False, index=True)
    witness_name = Column(String(255), nullable=False)
    disposition = Column(String(32), default="evasive")
    background_text = Column(Text, default="")
    cross_notes = Column(Text, default="")
    active = Column(Integer, default=1)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    messages = relationship("WitnessMessage", back_populates="session", cascade="all, delete-orphan")


class WitnessMessage(Base):
    __tablename__ = "witness_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("witness_sessions.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("WitnessSession", back_populates="messages")


class Judgment(Base):
    __tablename__ = "judgments"

    id = Column(String(36), primary_key=True, default=_uuid)
    citation = Column(String(512), nullable=False, index=True)
    case_name = Column(String(512), default="")
    judge_name = Column(String(255), index=True)
    court = Column(String(128), default="")
    year = Column(Integer, default=0)
    statute_section = Column(String(64), index=True)
    disposition_outcome = Column(String(64), index=True)
    relation_to_landmark = Column(String(32), default="referred")
    landmark_citation = Column(String(512), default="")
    created_at = Column(DateTime, default=_utcnow)


class TuningExportJob(Base):
    __tablename__ = "tuning_export_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(64), default="")
    status = Column(String(32), default="pending")
    record_count = Column(Integer, default=0)
    export_path = Column(String(1024), default="")
    created_at = Column(DateTime, default=_utcnow)
