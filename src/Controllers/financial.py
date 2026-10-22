import hashlib
import copy
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pycountry
from fastapi import HTTPException
from groq import APIConnectionError, APIError, APIStatusError, AuthenticationError, Groq, RateLimitError
from typing import Annotated
from pydantic import TypeAdapter, ValidationError

from Models.constants import (
    CURRENCY_MARKERS, DATE_FORMATS, DATE_PATTERN, DUE_DATE_PATTERN, FINANCIAL_EXTRACTION_PROMPT,
    FINANCIAL_VALIDATION_WARNING, GROQ_API_KEY, GROQ_AUTH_WARNING, GROQ_INPUT_WARNING,
    GROQ_KEY_WARNING, GROQ_MAX_OUTPUT_TOKENS, GROQ_MAX_RETRY_OUTPUT_TOKENS, GROQ_MODEL, GROQ_RATE_WARNING,
    GROQ_RESPONSE_WARNING, GROQ_TIMEOUT_SECONDS, GROQ_UNAVAILABLE_WARNING,
    INVOICE_NUMBER_LABEL_PATTERN, MAX_LLM_INPUT_CHARACTERS, MONEY_TOLERANCE, NUMBER_PATTERN,
    SUBTOTAL_LABEL_PATTERN, TAX_VALUE_PATTERN, TOTAL_LABEL_PATTERN,
    MISSING_COMPONENT_WARNING, TAX_AMOUNT_LABEL_PATTERN, TOTAL_MISMATCH_WARNING,
    VAT_MISMATCH_WARNING, VAT_RATE_PATTERN, VAT_UNVERIFIABLE_WARNING,
    ESSENTIAL_FIELDS, MONEY_FIELDS, ADJUSTMENT_LABEL_PATTERN,
)
from Models.financial_schema import (
    BatchExtractionResult, ExtractedInvoice, ExtractedInvoiceBatch, InvoiceWarning, UploadErrorDetail, ValidatedInvoice, NormalizedInvoice,
)
from Models.ocr_schema import ExtractedPage


def upload_error(status_code: int, code: str, message: str, flags=None, existing_id=None, warnings=None) -> HTTPException:
    detail = UploadErrorDetail(
        code=code, message=message, validation_flags=flags or [],
        existing_document_id=str(existing_id) if existing_id else None,
        warnings=warnings or [],
    )
    return HTTPException(status_code=status_code, detail=detail.model_dump(exclude_none=True))


def groq_response_schema() -> dict:
    """Inline enum references and use nullable type arrays accepted by Groq strict mode."""
    schema = ExtractedInvoiceBatch.model_json_schema()
    definitions = schema.get("$defs", {})

    def convert(node):
        if isinstance(node, list):
            return [convert(value) for value in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return convert(copy.deepcopy(definitions[node["$ref"].split("/")[-1]]))
        result = {key: convert(value) for key, value in node.items() if key != "$defs"}
        result.pop("default", None)
        if result.get("type") == "object" and "properties" in result:
            result["required"] = list(result["properties"])
        branches = result.get("anyOf")
        if branches and all(branch.get("type") in ("string", "null", "integer", "number", "boolean") for branch in branches):
            result.pop("anyOf")
            result["type"] = list(dict.fromkeys(branch["type"] for branch in branches))
            if any("enum" in branch for branch in branches):
                result["enum"] = [value for branch in branches for value in branch.get("enum", [None] if branch["type"] == "null" else [])]
        return result

    return convert(schema)


def extract_financial_data(pages: list[ExtractedPage] | str, is_last_chunk: bool = True) -> ExtractedInvoiceBatch:
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("your_"):
        raise upload_error(503, "groq_key_missing", GROQ_KEY_WARNING)
    if isinstance(pages, str):
        pages = [ExtractedPage(page_number=1, text=pages, method="text")]
    if sum(len(page.text) for page in pages) > MAX_LLM_INPUT_CHARACTERS:
        raise upload_error(422, "document_too_long", GROQ_INPUT_WARNING)
    try:
        with Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT_SECONDS, max_retries=1) as client:
            request = dict(
                model=GROQ_MODEL,
                temperature=0,
                reasoning_effort="low",
                messages=[
                    {"role": "system", "content": FINANCIAL_EXTRACTION_PROMPT},
                    {"role": "user", "content": json.dumps({"pages": [page.model_dump() for page in pages], "is_last_chunk": is_last_chunk}, ensure_ascii=False)},
                ],
                response_format={"type": "json_schema", "json_schema": {
                    "name": "financial_documents", "strict": True,
                    "schema": groq_response_schema(),
                }},
            )
            completion = client.chat.completions.create(**request, max_completion_tokens=GROQ_MAX_OUTPUT_TOKENS)
            if completion.choices and completion.choices[0].finish_reason == "length":
                completion = client.chat.completions.create(**request, max_completion_tokens=GROQ_MAX_RETRY_OUTPUT_TOKENS)
        if completion.choices and completion.choices[0].finish_reason == "length":
            raise upload_error(502, "groq_output_truncated", "Groq could not return all invoices in this batch. Reduce GROQ_BATCH_CHARACTERS or split this dense page; no incomplete model response was saved.", ["finish_reason_length"])
        if not completion.choices or completion.choices[0].finish_reason != "stop":
            raise upload_error(502, "groq_invalid_response", GROQ_RESPONSE_WARNING)
        return ExtractedInvoiceBatch.model_validate_json(completion.choices[0].message.content or "")
    except AuthenticationError as exc:
        raise upload_error(503, "groq_authentication_failed", GROQ_AUTH_WARNING) from exc
    except RateLimitError as exc:
        raise upload_error(429, "groq_rate_limited", GROQ_RATE_WARNING) from exc
    except APIConnectionError as exc:
        raise upload_error(503, "groq_unavailable", GROQ_UNAVAILABLE_WARNING) from exc
    except APIStatusError as exc:
        code = "groq_request_rejected" if exc.status_code == 400 else "groq_invalid_response"
        raise upload_error(502, code, GROQ_RESPONSE_WARNING, [f"upstream_http_{exc.status_code}"]) from exc
    except ValidationError as exc:
        flags = ["invalid_model_field_" + "_".join(map(str, error["loc"])) for error in exc.errors()]
        raise upload_error(502, "groq_invalid_response", GROQ_RESPONSE_WARNING, flags) from exc
    except (APIError, TypeError) as exc:
        raise upload_error(502, "groq_invalid_response", GROQ_RESPONSE_WARNING) from exc


def extract_invoice_batches(pages: list[ExtractedPage]) -> BatchExtractionResult:
    """Process every page without a fixed invoice count, carrying unfinished invoice pages."""
    def split_pages(items, limit):
        return [page.model_copy(update={"text": page.text[start:start + limit]})
                for page in items for start in range(0, len(page.text), limit)
                if page.text[start:start + limit].strip()]

    budget = MAX_LLM_INPUT_CHARACTERS
    units = split_pages(pages, budget)
    result = BatchExtractionResult()
    carry = []
    offset = 0
    first_error = None
    while offset < len(units):
        chunk = list(carry)
        size = sum(len(page.text) for page in chunk)
        start = offset
        if carry and offset < len(units) and 0 < budget - size < len(units[offset].text):
            # Use the remaining context for the next page instead of discarding a continuation.
            following = units[offset]
            available = budget - size
            units[offset:offset + 1] = [following.model_copy(update={"text": following.text[:available]}),
                                       following.model_copy(update={"text": following.text[available:]})]
        while offset < len(units) and size + len(units[offset].text) <= budget:
            chunk.append(units[offset])
            size += len(units[offset].text)
            offset += 1
        if offset == start:
            result.warnings.append(InvoiceWarning(code="invoice_exceeds_batch", source_pages=sorted({p.page_number for p in carry}), message="An unfinished invoice exceeds the batch text limit. Increase GROQ_BATCH_CHARACTERS or upload that invoice separately."))
            carry = []
            continue
        last = offset == len(units)
        numbers = {page.page_number for page in chunk}
        try:
            batch = extract_financial_data(chunk, is_last_chunk=last)
        except HTTPException as exc:
            if exc.detail.get("code") in ("groq_key_missing", "groq_authentication_failed"):
                raise
            if exc.detail.get("code") == "groq_output_truncated" and budget > 512:
                # Discard truncated output and retry its source with smaller batches.
                budget = max(512, budget // 2)
                units = split_pages(chunk + units[offset:], budget)
                offset = 0
                carry = []
                continue
            first_error = first_error or exc
            result.warnings.append(InvoiceWarning(code=exc.detail["code"], message=exc.detail["message"], source_pages=sorted(numbers), validation_flags=exc.detail.get("validation_flags", [])))
            carry = []
            if exc.status_code in (429, 503):
                remaining = sorted({page.page_number for page in units[offset:]})
                if remaining:
                    result.warnings.append(InvoiceWarning(code="pages_not_processed", source_pages=remaining,
                        message="Remaining pages were not sent because Groq was unavailable or rate limited. Retry these pages later."))
                break
            continue
        for invoice in batch.invoices:
            if not invoice.source_pages or not set(invoice.source_pages) <= numbers:
                result.warnings.append(InvoiceWarning(code="invalid_source_pages", source_pages=invoice.source_pages, message="The model returned invoice pages outside its input batch."))
            else:
                result.invoices.append(invoice)
        invalid_continuation = any(
            page.page_number not in numbers or not page.text.strip() or not any(
                normalize_text(page.text) in normalize_text(source.text)
                for source in chunk if source.page_number == page.page_number
            ) for page in batch.continuation_pages
        )
        if invalid_continuation or (last and batch.continuation_pages):
            result.warnings.append(InvoiceWarning(code="invalid_continuation", source_pages=sorted(numbers), message="The model returned an invalid continuation. Review these pages."))
            carry = []
        else:
            carry = [ExtractedPage(page_number=page.page_number, text=page.text,
                                   method=next(source.method for source in chunk if source.page_number == page.page_number))
                     for page in batch.continuation_pages]
        if not batch.invoices and not carry:
            result.warnings.append(InvoiceWarning(code="no_invoices_detected", source_pages=sorted(numbers), message="No invoice or receipt was identified on these pages."))
    if not result.invoices and first_error:
        first_error.detail["warnings"] = [warning.model_dump() for warning in result.warnings]
        raise first_error
    return result


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


def numbers_in_quote(quote: str) -> set[Decimal]:
    normalized = "".join(str(unicodedata.digit(char)) if char.isdecimal() else char for char in quote)
    normalized = normalized.replace("٫", ".").replace("٬", ",").replace("\u00a0", " ").replace("٪", "%")
    numbers = set()
    for match in re.finditer(NUMBER_PATTERN, normalized):
        if normalized[match.end():].lstrip().startswith("%"):
            continue
        token = match.group().replace(" ", "")
        # The last separator is decimal only when followed by one or two digits.
        separator = max(token.rfind("."), token.rfind(","))
        if separator >= 0 and len(token) - separator - 1 in (1, 2):
            token = token[:separator].replace(".", "").replace(",", "") + "." + token[separator + 1:]
        else:
            token = token.replace(".", "").replace(",", "")
        try:
            numbers.add(Decimal(token))
        except InvalidOperation:
            continue
    return numbers


def dates_in_quote(quote: str) -> set:
    dates = set()
    for token in re.findall(DATE_PATTERN, quote):
        for date_format in DATE_FORMATS:
            try:
                dates.add(datetime.strptime(token, date_format).date())
            except ValueError:
                pass
    return dates


def has_single_invoice_scope(invoice: ValidatedInvoice, text: str) -> bool:
    """Only use page-wide labels when every numbered invoice matches this invoice."""
    if not invoice.invoice_number:
        return False
    labels = list(re.finditer(INVOICE_NUMBER_LABEL_PATTERN, text, re.IGNORECASE))
    expected = re.sub(r"\W", "", normalize_text(invoice.invoice_number))
    identifiers = [re.search(r"([A-Za-z0-9][A-Za-z0-9/-]*)$", label.group()).group(1) for label in labels]
    return bool(identifiers) and all(re.sub(r"\W", "", normalize_text(value)) == expected for value in identifiers)


def source_has_component_amount(text: str, label_pattern: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.search(label_pattern, line, re.IGNORECASE):
            if numbers_in_quote(line):
                return True
            if index + 1 < len(lines) and numbers_in_quote(lines[index + 1]):
                return True
    return False


def assess_financial_data(extracted: ExtractedInvoice, text: str):
    """Normalize fields independently and collect issues without discarding the invoice."""
    flags, explanations = [], []
    if not extracted.is_financial_document:
        flags.append("not_a_single_invoice_or_receipt")
    raw = extracted.model_dump(exclude={"is_financial_document", "evidence", "source_pages"})
    for field in ("vendor", "invoice_number", "description", "project", "currency"):
        if raw[field] is not None:
            raw[field] = raw[field].strip() or None
    if raw["currency"]:
        raw["currency"] = raw["currency"].upper()
    if raw["invoice_number"]:
        raw["invoice_number"] = re.sub(r"^(?:invoice|receipt)\s*(?:number|no\.?|#)\s*[:#]?\s*", "", raw["invoice_number"], flags=re.IGNORECASE).strip() or None
    values = {}
    for field, definition in ValidatedInvoice.model_fields.items():
        value = raw.get(field)
        try:
            if field == "invoice_date" and value is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Expected ISO date")
            annotation = Annotated[tuple([definition.annotation] + definition.metadata)] if definition.metadata else definition.annotation
            values[field] = TypeAdapter(annotation).validate_python(value) if value is not None else None
        except (ValidationError, ValueError, TypeError):
            values[field] = None
            flags.append("invalid_or_missing_" + field)
        if values[field] is None and field in ESSENTIAL_FIELDS:
            flags.append("invalid_or_missing_" + field)
    # Review records use null, never invented placeholders, for unusable fields.
    invoice = NormalizedInvoice(**values)
    source = normalize_text(text)
    evidence = extracted.evidence.model_dump()
    for field, quote in evidence.items():
        value = getattr(invoice, field)
        if value is None:
            if quote is not None:
                flags.append(f"unexpected_evidence_{field}")
            continue
        if not quote or not normalize_text(quote) or normalize_text(quote) not in source:
            flags.append(f"unverified_evidence_{field}")
            continue
        if field in MONEY_FIELDS:
            if value not in numbers_in_quote(quote):
                flags.append(f"source_mismatch_{field}")
        elif field == "invoice_date":
            dates = dates_in_quote(quote)
            if value not in dates:
                flags.append("source_mismatch_invoice_date")
            elif len(dates) > 1:
                flags.append("ambiguous_invoice_date")
            if re.search(DUE_DATE_PATTERN, quote, re.IGNORECASE):
                flags.append("invoice_date_is_due_date")
            source_lines = [line for line in text.splitlines() if value in dates_in_quote(line)]
            if source_lines and all(re.search(DUE_DATE_PATTERN, line, re.IGNORECASE) for line in source_lines):
                flags.append("invoice_date_is_due_date")
        elif field == "currency":
            markers = (value, *CURRENCY_MARKERS.get(value, ()))
            if not any(re.search(r"(?<![A-Z])" + re.escape(marker) + r"(?![A-Z])", quote.upper()) for marker in markers):
                flags.append("source_mismatch_currency")
        elif normalize_text(str(value)) not in normalize_text(quote):
            flags.append(f"source_mismatch_{field}")

    if invoice.currency and pycountry.currencies.get(alpha_3=invoice.currency) is None:
        flags.append("invalid_currency")
    if invoice.amount is not None and not re.search(TOTAL_LABEL_PATTERN, evidence["amount"] or "", re.IGNORECASE):
        flags.append("total_label_not_verified")
    if invoice.tax_amount is not None and invoice.amount is not None and invoice.tax_amount > invoice.amount:
        flags.append("tax_exceeds_total")
    if has_single_invoice_scope(invoice, text):
        for field, label, title in (("subtotal", SUBTOTAL_LABEL_PATTERN, "a subtotal"),
                                    ("tax_amount", TAX_AMOUNT_LABEL_PATTERN, "a tax/VAT amount")):
            if getattr(invoice, field) is None and source_has_component_amount(text, label):
                flags.append(f"{field}_present_but_not_extracted")
                explanations.append(MISSING_COMPONENT_WARNING.format(field=title))
    verified_money = not any(
        flag in flags for field in MONEY_FIELDS
        for flag in (f"source_mismatch_{field}", f"unverified_evidence_{field}", f"{field}_present_but_not_extracted")
    )
    if invoice.subtotal is not None and invoice.tax_amount is not None and invoice.amount is not None and verified_money:
        expected_total = invoice.subtotal + invoice.tax_amount - (invoice.discount_amount or Decimal("0")) + (invoice.other_charges or Decimal("0"))
        if abs(expected_total - invoice.amount) > Decimal(MONEY_TOLERANCE):
            flags.append("subtotal_plus_tax_does_not_match_total")
            explanations.append(
                f"Subtotal {invoice.subtotal:.2f} + tax {invoice.tax_amount:.2f}"
                f" - discount {invoice.discount_amount or Decimal('0'):.2f} + other charges {invoice.other_charges or Decimal('0'):.2f}"
                f" = {invoice.currency or 'unknown currency'} {expected_total:.2f}, but the invoice total is {invoice.currency or 'unknown currency'} {invoice.amount:.2f}"
                f" (difference {invoice.currency or 'unknown currency'} {abs(expected_total - invoice.amount):.2f}). Requires review.")
        if not invoice.discount_amount and not invoice.other_charges and evidence["tax_amount"]:
            rate_text = evidence["tax_amount"]
            if not re.search(VAT_RATE_PATTERN, rate_text) and has_single_invoice_scope(invoice, text):
                rate_text += "\n" + "\n".join(line for line in text.splitlines() if re.search(TAX_AMOUNT_LABEL_PATTERN, line, re.IGNORECASE))
            rates = {Decimal(value.replace(",", ".").replace("٫", ".")) for value in re.findall(VAT_RATE_PATTERN, rate_text)}
            if len(rates) == 1:
                rate = rates.pop()
                try:
                    expected_tax = (invoice.subtotal * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                except InvalidOperation:
                    flags.append("vat_rate_cannot_be_verified")
                    explanations.append(VAT_UNVERIFIABLE_WARNING)
                    expected_tax = None
                if expected_tax is not None and abs(expected_tax - invoice.tax_amount) > Decimal(MONEY_TOLERANCE):
                    flags.append("vat_rate_does_not_match_tax_amount")
                    explanations.append(VAT_MISMATCH_WARNING.format(
                        rate=str(rate), currency=invoice.currency, subtotal=f"{invoice.subtotal:.2f}",
                        expected=f"{expected_tax:.2f}", actual=f"{invoice.tax_amount:.2f}"))
    for field in ("discount_amount", "other_charges"):
        if evidence[field] and getattr(invoice, field) is None:
            flags.append("ambiguous_" + field)
    if has_single_invoice_scope(invoice, text) and re.search(ADJUSTMENT_LABEL_PATTERN, text, re.IGNORECASE) and not (evidence["discount_amount"] or evidence["other_charges"]):
        flags.append("adjustment_treatment_requires_review")
    # Reject unsupported evidence; retain raw model output separately for auditing.
    verified_evidence = {}
    for field, quote in evidence.items():
        verified_evidence[field] = quote if quote and normalize_text(quote) in source else None
        if f"unverified_evidence_{field}" in flags or f"source_mismatch_{field}" in flags or (field == "currency" and "invalid_currency" in flags):
            setattr(invoice, field, None)
    flags = sorted(set(flags))
    if flags and not explanations:
        explanations = ["Requires review: " + ", ".join(flags) + "."]
    return invoice, flags, explanations, verified_evidence


def validate_financial_data(extracted: ExtractedInvoice, text: str) -> NormalizedInvoice:
    """Strict helper for callers that require a fully validated expense."""
    invoice, flags, explanations, _ = assess_financial_data(extracted, text)
    if flags:
        raise upload_error(422, "validation_failed", " ".join(explanations), flags)
    return invoice


def invoice_duplicate_key(invoice: NormalizedInvoice, use_invoice_number: bool = True) -> str | None:
    def identity(value):
        return "".join(char for char in normalize_text(value) if char.isalnum())

    if not invoice.vendor:
        return None
    if invoice.invoice_number and use_invoice_number:
        parts = ["invoice_number", identity(invoice.vendor), identity(invoice.invoice_number)]
    else:
        if invoice.invoice_date is None or invoice.amount is None or invoice.currency is None:
            return None
        parts = ["potential_duplicate", identity(invoice.vendor), invoice.invoice_date.isoformat(),
                 str(invoice.amount.quantize(Decimal("0.01"))), invoice.currency]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
