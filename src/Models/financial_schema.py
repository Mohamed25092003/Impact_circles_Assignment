from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"


class ExpenseCategory(str, Enum):
    PERSONNEL = "personnel"
    TRAVEL = "travel"
    EQUIPMENT = "equipment"
    SOFTWARE = "software"
    EVENTS = "events"
    OPERATIONS = "operational_expenses"


class InvoiceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_date: str | None
    vendor: str | None
    invoice_number: str | None
    description: str | None
    amount: str | None
    currency: str | None
    tax_amount: str | None
    subtotal: str | None
    discount_amount: str | None = None
    other_charges: str | None = None
    project: str | None = None


class ExtractedInvoice(BaseModel):
    """Groq wire schema: all keys are required; unknown values must be null."""
    model_config = ConfigDict(extra="forbid")

    is_financial_document: bool
    document_type: DocumentType | None
    invoice_date: str | None
    vendor: str | None
    invoice_number: str | None
    description: str | None
    amount: str | None
    currency: str | None
    tax_amount: str | None
    subtotal: str | None
    category: ExpenseCategory | None
    evidence: InvoiceEvidence
    discount_amount: str | None = None
    other_charges: str | None = None
    project: str | None = None


class ValidatedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    invoice_date: date
    vendor: str = Field(min_length=1, max_length=255)
    invoice_number: str | None = Field(max_length=100)
    description: str = Field(min_length=1)
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_amount: Decimal | None = Field(ge=0, max_digits=14, decimal_places=2)
    subtotal: Decimal | None = Field(ge=0, max_digits=14, decimal_places=2)
    category: ExpenseCategory
    discount_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    other_charges: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    project: str | None = Field(default=None, max_length=255)


class NormalizedInvoice(BaseModel):
    """Storage values for both validated expenses and incomplete review records."""
    document_type: DocumentType | None
    invoice_date: date | None
    vendor: str | None
    invoice_number: str | None
    description: str | None
    amount: Decimal | None
    currency: str | None
    tax_amount: Decimal | None
    subtotal: Decimal | None
    category: ExpenseCategory | None
    discount_amount: Decimal | None
    other_charges: Decimal | None
    project: str | None


class InvoiceCandidate(ExtractedInvoice):
    source_pages: list[int]


class ContinuationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    text: str


class ExtractedInvoiceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoices: list[InvoiceCandidate]
    continuation_pages: list[ContinuationPage]


class InvoiceWarning(BaseModel):
    invoice_index: int | None = None
    source_pages: list[int] = Field(default_factory=list)
    code: str
    message: str
    validation_flags: list[str] = Field(default_factory=list)
    existing_invoice_id: str | None = None
    existing_document_id: str | None = None


class BatchExtractionResult(BaseModel):
    invoices: list[InvoiceCandidate] = Field(default_factory=list)
    warnings: list[InvoiceWarning] = Field(default_factory=list)


class UploadErrorDetail(BaseModel):
    code: str
    message: str
    saved: bool = False
    validation_flags: list[str] = Field(default_factory=list)
    existing_document_id: str | None = None
    warnings: list[InvoiceWarning] = Field(default_factory=list)
