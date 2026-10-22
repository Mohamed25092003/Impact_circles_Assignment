import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from Models.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class ContentRecord(Base):
    __tablename__ = 'content_requests'

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    generated: Mapped[dict | None] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    approved_digest: Mapped[str | None] = mapped_column(String(64))
    channels: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default='created')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PublicationLog(Base):
    __tablename__ = 'content_publication_logs'
    __table_args__ = (UniqueConstraint('content_id', 'revision', 'channel'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    content_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('content_requests.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='publishing')
    published_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    active_attempt: Mapped[str | None] = mapped_column(String(36))
    # The local HTTP mock persists its received post here, avoiding a third table.
    mock_post: Mapped[dict | None] = mapped_column(JSON)
    mock_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
