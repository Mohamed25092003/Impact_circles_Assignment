import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Models.base import Base
from Models.constants import UPLOADED_STATUS
from Models.upload import DocumentUpload


class FinancialDocument(Base):
    __tablename__ = "financial_documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="positive_document_size"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="nonnegative_amount"),
        CheckConstraint("tax_amount IS NULL OR tax_amount >= 0", name="nonnegative_tax"),
        CheckConstraint(
            "category IS NULL OR category IN ('personnel', 'travel', 'equipment', 'software', 'events', 'operational_expenses')",
            name="valid_expense_category",
        ),
        CheckConstraint(
            "document_type IS NULL OR document_type IN ('invoice', 'receipt')",
            name="valid_document_type",
        ),
        Index("ix_financial_documents_vendor_invoice", "vendor", "invoice_number"),
        Index("uq_financial_documents_duplicate_key", "duplicate_key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(30), default=UPLOADED_STATUS, nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("financial_documents.id"), nullable=True)
    upload_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_uploads.id", ondelete="CASCADE"), index=True)
    invoice_index: Mapped[int | None] = mapped_column(Integer)
    source_pages: Mapped[list | None] = mapped_column(JSON)
    upload: Mapped[DocumentUpload | None] = relationship(back_populates="invoices", foreign_keys=[upload_id])

    # Normalized source values; review records may have missing fields.
    document_type: Mapped[str | None] = mapped_column(String(20))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    vendor: Mapped[str | None] = mapped_column(String(255))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    category: Mapped[str | None] = mapped_column(String(30))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    duplicate_key: Mapped[str | None] = mapped_column(String(64))
    financial_evidence: Mapped[dict | None] = mapped_column(JSON)
    extraction_model: Mapped[str | None] = mapped_column(String(100))
    validation_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(String(20))
    page_count: Mapped[int | None] = mapped_column(Integer)
    processing_error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    other_charges: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    project: Mapped[str | None] = mapped_column(String(255))
    raw_extraction: Mapped[dict | None] = mapped_column(JSON)
    validation_messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    duplicate_status: Mapped[str] = mapped_column(String(30), default="not_checked", nullable=False)
    duplicate_basis: Mapped[str | None] = mapped_column(String(40))
