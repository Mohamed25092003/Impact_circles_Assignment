import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from Controllers.financial import assess_financial_data, extract_invoice_batches, invoice_duplicate_key, upload_error
from Controllers.ocr import extract_image_text, extract_pdf_text
from Models.constants import (
    DOCUMENT_NOT_FOUND_WARNING, DUPLICATE_FILE_WARNING, DUPLICATE_INVOICE_WARNING,
    GROQ_MODEL, MAX_FILENAME_LENGTH, MAX_PDF_BYTES, PDF_CONTENT_TYPE, PDF_CONTENT_WARNING,
    PDF_EXTENSION, PDF_EXTENSION_WARNING, PDF_HEADER, PDF_SIZE_WARNING, UPLOAD_CHUNK_BYTES,
    UPLOAD_DIR, VALIDATED_STATUS, SUPPORTED_IMAGES, SUPPORTED_FILE_WARNING,
)
from Models.document import FinancialDocument
from Models.financial_schema import InvoiceWarning
from Models.ocr_schema import DocumentExtractionError
from Models.upload import DocumentUpload


def get_document(document_id: uuid.UUID, db: Session) -> DocumentUpload:
    document = db.scalar(select(DocumentUpload).where(DocumentUpload.id == document_id).options(selectinload(DocumentUpload.invoices)))
    if document is None:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND_WARNING)
    return document


def duplicate_warning(existing: FinancialDocument, index: int, pages: list[int]) -> InvoiceWarning:
    return InvoiceWarning(invoice_index=index, source_pages=pages, code="duplicate_invoice",
                         message=DUPLICATE_INVOICE_WARNING, validation_flags=["potential_duplicate"], existing_invoice_id=str(existing.id),
                         existing_document_id=str(existing.upload_id) if existing.upload_id else None)


def upload_pdf(file: UploadFile, db: Session) -> DocumentUpload:
    """Persist only validated, nonduplicate expenses; return warnings for rejected items."""
    destination = None
    try:
        name = Path((file.filename or "").replace("\\", "/")).name
        extension = Path(name).suffix.lower()
        if extension != PDF_EXTENSION and extension not in SUPPORTED_IMAGES:
            raise HTTPException(status_code=400, detail=SUPPORTED_FILE_WARNING)
        header = file.file.read(len(PDF_HEADER))
        if extension == PDF_EXTENSION and header != PDF_HEADER:
            raise HTTPException(status_code=400, detail=PDF_CONTENT_WARNING)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".pending-", dir=UPLOAD_DIR) as temporary:
            staged = Path(temporary) / f"document{extension}"
            digest, size = hashlib.sha256(header), len(header)
            with staged.open("xb") as output:
                output.write(header)
                while chunk := file.file.read(UPLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise HTTPException(status_code=413, detail="Document exceeds the upload size limit.")
                    digest.update(chunk)
                    output.write(chunk)
            checksum = digest.hexdigest()
            existing_upload = db.scalar(select(DocumentUpload).where(DocumentUpload.sha256 == checksum))
            if existing_upload:
                error = upload_error(409, "duplicate_document", "Potential duplicate: this exact document is already stored.", existing_id=existing_upload.id, flags=["potential_duplicate"])
                error.detail["duplicate_status"] = "checked_match"
                raise error
            try:
                text_result = extract_pdf_text(staged) if extension == PDF_EXTENSION else extract_image_text(staged)
            except DocumentExtractionError as exc:
                raise upload_error(422, "document_unreadable", str(exc)) from exc
            extraction = extract_invoice_batches(text_result.pages)
            warnings = list(extraction.warnings)
            pages = {page.page_number: page.text for page in text_result.pages}
            processed = []
            for index, candidate in enumerate(extraction.invoices, start=1):
                if not candidate.source_pages or not set(candidate.source_pages) <= pages.keys():
                    warnings.append(InvoiceWarning(invoice_index=index, source_pages=candidate.source_pages,
                        code="invalid_source_pages", message="Invoice source pages could not be verified."))
                    continue
                source = "\n\n".join(pages[number] for number in sorted(set(candidate.source_pages)))
                invoice, flags, messages, evidence = assess_financial_data(candidate, source)
                key = invoice_duplicate_key(invoice)
                if not key:
                    flags.append("duplicate_check_not_possible")
                    messages.append("Duplicate check was not possible because identifying fields are missing or unverified.")
                if flags:
                    warnings.append(InvoiceWarning(invoice_index=index, source_pages=candidate.source_pages,
                        code="validation_failed", message=" ".join(messages) + " This invoice was not saved.",
                        validation_flags=sorted(set(flags))))
                    continue
                processed.append((key, index, invoice, candidate, source, flags, messages, evidence))
            if not processed:
                raise upload_error(422, "no_valid_invoices", "No invoice passed validation. Nothing was saved.", warnings=warnings)
            stored_name, now = f"{uuid.uuid4()}{extension}", datetime.now(timezone.utc)
            upload = DocumentUpload(id=uuid.uuid4(), original_filename=name[:MAX_FILENAME_LENGTH],
                stored_filename=stored_name, size_bytes=size, sha256=checksum,
                processing_status=VALIDATED_STATUS, extracted_text=text_result.text,
                extraction_method=text_result.method, page_count=text_result.page_count,
                extracted_at=now, detected_count=len(extraction.invoices), warnings=[])
            db.add(upload)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                existing_upload = db.scalar(select(DocumentUpload).where(DocumentUpload.sha256 == checksum))
                if existing_upload:
                    error = upload_error(409, "duplicate_document", "Potential duplicate: this exact document is already stored.", existing_id=existing_upload.id, flags=["potential_duplicate"])
                    error.detail["duplicate_status"] = "checked_match"
                    raise error
                raise
            saved = []
            if db.bind.dialect.name == "postgresql":
                # Serialize vendor checks across different invoice/fallback keys, including legacy rows.
                from Controllers.financial import normalize_text
                vendor_locks = sorted({"".join(c for c in normalize_text(item[2].vendor) if c.isalnum()) for item in processed if item[2].vendor})
                for vendor in vendor_locks:
                    lock_id = int.from_bytes(hashlib.sha256(vendor.encode()).digest()[:8], "big", signed=True)
                    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            # Serialize overlapping canonical keys in a stable order; uniqueness handles races.
            for key, index, invoice, candidate, source, flags, messages, evidence in sorted(processed, key=lambda item: (item[0] or "", item[1])):
                existing = find_duplicate(invoice, key, db) if key else None
                basis = "vendor_invoice_number" if invoice.vendor and invoice.invoice_number else "vendor_date_amount_currency" if key else None
                if existing:
                    warnings.append(duplicate_warning(existing, index, candidate.source_pages))
                    continue
                values = invoice.model_dump()
                values.update(category=invoice.category.value if invoice.category else None,
                              document_type=invoice.document_type.value if invoice.document_type else None)
                document = FinancialDocument(**values, original_filename=upload.original_filename,
                    stored_filename=stored_name, content_type=PDF_CONTENT_TYPE if extension == PDF_EXTENSION else SUPPORTED_IMAGES[extension][1], size_bytes=size,
                    sha256=checksum, duplicate_key=key,
                    processing_status=VALIDATED_STATUS,
                    extracted_text=source, extraction_method=text_result.method,
                    page_count=len(set(candidate.source_pages)), extracted_at=now,
                    financial_evidence=evidence, raw_extraction=candidate.model_dump(mode="json"), extraction_model=GROQ_MODEL,
                    upload_id=upload.id, invoice_index=index, source_pages=sorted(set(candidate.source_pages)),
                    validation_flags=sorted(set(flags)), validation_messages=messages,
                    duplicate_status="checked_no_match", duplicate_basis=basis, duplicate_of_id=None)
                try:
                    with db.begin_nested():
                        db.add(document)
                        db.flush()
                except IntegrityError:
                    existing = db.scalar(select(FinancialDocument).where(FinancialDocument.duplicate_key == key))
                    if not existing:
                        raise
                    warnings.append(duplicate_warning(existing, index, candidate.source_pages))
                    continue
                saved.append(document)
            if not saved:
                duplicate_only = warnings and all(warning.code.startswith("duplicate") for warning in warnings)
                raise upload_error(409 if duplicate_only else 422, "no_new_valid_invoices",
                    "No new validated invoice was saved.", warnings=warnings)
            upload.warnings = [warning.model_dump() for warning in warnings]
            upload.processing_status = "partial" if warnings else VALIDATED_STATUS
            upload.invoices = sorted(saved, key=lambda item: item.invoice_index)
            destination = UPLOAD_DIR / stored_name
            staged.replace(destination)
            db.commit()
            return upload
    except Exception:
        db.rollback()
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


def find_duplicate(invoice, key: str, db: Session):
    """Check canonical rows and legacy rows using the same Python normalization."""
    existing = db.scalar(select(FinancialDocument).where(FinancialDocument.duplicate_key == key))
    if existing:
        return existing
    # Older tracker rows may predate duplicate keys. Never treat them as no-match by omission.
    fallback = invoice_duplicate_key(invoice, use_invoice_number=False)
    for record in db.scalars(select(FinancialDocument).where(FinancialDocument.duplicate_of_id.is_(None))):
        if invoice_duplicate_key(record) == key:
            return record
        if fallback and (not invoice.invoice_number or not record.invoice_number) and invoice_duplicate_key(record, use_invoice_number=False) == fallback:
            return record
    return None
