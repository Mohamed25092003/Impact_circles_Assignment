import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

from Models.financial_schema import InvoiceWarning


class FinancialDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_pages: list[int] | None
    document_type: str | None
    invoice_date: date | None
    vendor: str | None
    invoice_number: str | None
    description: str | None
    amount: Decimal | None
    currency: str | None
    tax_amount: Decimal | None
    category: str | None
    subtotal: Decimal | None
    discount_amount: Decimal | None
    other_charges: Decimal | None
    project: str | None
    financial_evidence: dict | None
    processing_status: str
    validation_flags: list[str]
    validation_messages: list[str]
    duplicate_status: str
    duplicate_basis: str | None
    duplicate_of_id: uuid.UUID | None


    @field_serializer("financial_evidence")
    def distinct_evidence(self, evidence: dict | None):
        if evidence is None:
            return None
        return {
            field: quote for field, quote in evidence.items()
            if quote != getattr(self, field, None) and quote != str(getattr(self, field, None))
        }


class UploadInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_date: date | None
    vendor: str | None
    invoice_number: str | None
    description: str | None
    amount: Decimal | None
    currency: str | None
    category: str | None
    project: str | None
    processing_status: str


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    processing_status: str
    saved_count: int
    invoices: list[UploadInvoiceResponse]
    warnings: list[InvoiceWarning]


class ExpenseSummaryGroup(BaseModel):
    project: str | None
    category: str
    currency: str
    expense_count: int
    total: Decimal


class ExpenseSummaryResponse(BaseModel):
    groups: list[ExpenseSummaryGroup]
    included_count: int
    excluded_count: int
    review_count: int
    potential_duplicate_count: int
    policy: str = "Only validated expenses checked for duplicates with no match are included. No currency conversion."
