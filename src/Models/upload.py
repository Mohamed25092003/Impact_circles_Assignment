import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Models.base import Base


class DocumentUpload(Base):
    __tablename__ = "document_uploads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processing_status: Mapped[str] = mapped_column(String(30))
    extracted_text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(20))
    page_count: Mapped[int] = mapped_column(Integer)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    detected_count: Mapped[int] = mapped_column(Integer, default=0)
    invoices: Mapped[list["FinancialDocument"]] = relationship(
        "FinancialDocument", back_populates="upload", order_by="FinancialDocument.invoice_index",
        cascade="all, delete-orphan", foreign_keys="FinancialDocument.upload_id",
    )

    @property
    def saved_count(self) -> int:
        return len(self.invoices)
