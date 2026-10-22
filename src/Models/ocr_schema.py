from typing import Literal

from pydantic import BaseModel, Field


class ExtractedPage(BaseModel):
    page_number: int
    text: str
    method: Literal["text", "ocr"]


class TextExtractionResult(BaseModel):
    text: str
    method: Literal["text", "ocr", "mixed"]
    page_count: int
    pages: list[ExtractedPage] = Field(default_factory=list)


class DocumentExtractionError(Exception):
    """A document could not be read, or a required OCR dependency is missing."""
