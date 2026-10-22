import shutil
import warnings
from pathlib import Path

import pytesseract
from PIL import Image, UnidentifiedImageError
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError, PDFPopplerTimeoutError, PDFSyntaxError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from Models.constants import (
    FILE_ACCESS_WARNING,
    MAX_DOCUMENT_PAGES,
    MAX_EXTRACTED_CHARACTERS,
    MIXED_EXTRACTION_METHOD,
    OCR_DEPENDENCY_WARNING,
    OCR_DPI,
    OCR_EXTRACTION_METHOD,
    OCR_LANGUAGE_WARNING,
    OCR_LANGUAGES,
    OCR_PAGE_TIMEOUT_SECONDS,
    OCR_TIMEOUT_WARNING,
    PDF_EMPTY_WARNING,
    PDF_PAGE_LIMIT_WARNING,
    PDF_PASSWORD_WARNING,
    PDF_READ_WARNING,
    TEXT_EMPTY_WARNING,
    TEXT_EXTRACTION_METHOD,
    TEXT_LENGTH_WARNING,
    SUPPORTED_IMAGES, MAX_IMAGE_PIXELS,
)
from Models.ocr_schema import DocumentExtractionError, ExtractedPage, TextExtractionResult


def extract_image_text(path: Path) -> TextExtractionResult:
    """Verify the decoded format, then OCR every frame (including multipage TIFF)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != SUPPORTED_IMAGES[path.suffix.lower()][0]:
                    raise DocumentExtractionError("Image contents do not match the filename extension.")
                count = getattr(image, "n_frames", 1)
                if count > MAX_DOCUMENT_PAGES:
                    raise DocumentExtractionError(PDF_PAGE_LIMIT_WARNING.format(limit=MAX_DOCUMENT_PAGES))
                check_ocr_dependencies()
                pages = []
                length = 0
                for index in range(count):
                    image.seek(index)
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise DocumentExtractionError("Image exceeds the supported pixel limit.")
                    with image.convert("RGB") as frame:
                        text = pytesseract.image_to_string(frame, lang=OCR_LANGUAGES, timeout=OCR_PAGE_TIMEOUT_SECONDS).strip()
                    length += len(text)
                    if length > MAX_EXTRACTED_CHARACTERS:
                        raise DocumentExtractionError(TEXT_LENGTH_WARNING)
                    pages.append(ExtractedPage(page_number=index + 1, text=text, method="ocr"))
        text = "\n\n".join(page.text for page in pages).strip()
        if not text:
            raise DocumentExtractionError(TEXT_EMPTY_WARNING)
        return TextExtractionResult(text=text, method="ocr", page_count=len(pages), pages=pages)
    except DocumentExtractionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise DocumentExtractionError("Image is damaged, unsupported, or too large to decode.") from exc
    except RuntimeError as exc:
        raise DocumentExtractionError(OCR_TIMEOUT_WARNING) from exc


def check_ocr_dependencies() -> None:
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        raise DocumentExtractionError(OCR_DEPENDENCY_WARNING)
    available = set(pytesseract.get_languages(config=""))
    missing = set(OCR_LANGUAGES.split("+")) - available
    if missing:
        raise DocumentExtractionError(OCR_LANGUAGE_WARNING.format(languages=", ".join(sorted(missing))))


def read_scanned_page(path: Path, page_number: int) -> str:
    images = convert_from_path(
        str(path), dpi=OCR_DPI, first_page=page_number, last_page=page_number,
        grayscale=True, thread_count=1, timeout=OCR_PAGE_TIMEOUT_SECONDS,
    )
    try:
        return pytesseract.image_to_string(
            images[0], lang=OCR_LANGUAGES, timeout=OCR_PAGE_TIMEOUT_SECONDS,
        ).strip()
    finally:
        for image in images:
            image.close()


def extract_pdf_text(path: Path) -> TextExtractionResult:
    """Read embedded text per page, falling back to local OCR for image pages."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentExtractionError(PDF_PASSWORD_WARNING)
        page_count = len(reader.pages)
        if not page_count:
            raise DocumentExtractionError(PDF_EMPTY_WARNING)
        if page_count > MAX_DOCUMENT_PAGES:
            raise DocumentExtractionError(PDF_PAGE_LIMIT_WARNING.format(limit=MAX_DOCUMENT_PAGES))

        texts = []
        pages = []
        methods = set()
        character_count = 0
        ocr_checked = False
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                methods.add(TEXT_EXTRACTION_METHOD)
                method = TEXT_EXTRACTION_METHOD
            else:
                if not ocr_checked:
                    check_ocr_dependencies()
                    ocr_checked = True
                text = read_scanned_page(path, number)
                methods.add(OCR_EXTRACTION_METHOD)
                method = OCR_EXTRACTION_METHOD
            character_count += len(text)
            if character_count > MAX_EXTRACTED_CHARACTERS:
                raise DocumentExtractionError(TEXT_LENGTH_WARNING)
            texts.append(text)
            pages.append(ExtractedPage(page_number=number, text=text, method=method))

        text = "\n\n".join(texts).strip()
        if not text:
            raise DocumentExtractionError(TEXT_EMPTY_WARNING)
        return TextExtractionResult(
            text=text, method=MIXED_EXTRACTION_METHOD if len(methods) > 1 else methods.pop(), page_count=page_count, pages=pages,
        )
    except DocumentExtractionError:
        raise
    except (PyPdfError, PDFPageCountError, PDFSyntaxError, ValueError, IndexError) as exc:
        raise DocumentExtractionError(PDF_READ_WARNING) from exc
    except (PDFPopplerTimeoutError, RuntimeError) as exc:
        raise DocumentExtractionError(OCR_TIMEOUT_WARNING) from exc
    except OSError as exc:
        raise DocumentExtractionError(FILE_ACCESS_WARNING) from exc
