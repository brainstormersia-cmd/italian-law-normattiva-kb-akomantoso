from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path

from normativa_processor.core.exceptions import OCRError, PDFExtractionError
from normativa_processor.core.utils import retry_on_failure
from normativa_processor.extraction.table_extractor import table_to_markdown
from normativa_processor.extraction.text_cleaner import remove_repeated_headers

pdfplumber = importlib.import_module("pdfplumber") if importlib.util.find_spec("pdfplumber") else None
fitz = importlib.import_module("fitz") if importlib.util.find_spec("fitz") else None
pytesseract = (
    importlib.import_module("pytesseract") if importlib.util.find_spec("pytesseract") else None
)


@retry_on_failure(max_attempts=3, delay=0.5, exceptions=(PDFExtractionError,))
def extract_text_pdf(path: Path, use_ocr: bool) -> tuple[str, int, list[list[str]]]:
    if not path.exists():
        raise PDFExtractionError(f"PDF non trovato: {path}")
    if pdfplumber is None and fitz is None:
        raise PDFExtractionError("pdfplumber o PyMuPDF non disponibili.")

    if pdfplumber is not None:
        try:
            return _extract_with_pdfplumber(path, use_ocr)
        except Exception as exc:
            logging.warning("pdfplumber fallito per %s: %s", path.name, exc)
            if fitz is None:
                raise PDFExtractionError(str(exc)) from exc

    if fitz is not None:
        try:
            return _extract_with_pymupdf(path, use_ocr)
        except Exception as exc:
            raise PDFExtractionError(str(exc)) from exc

    raise PDFExtractionError("Impossibile estrarre testo dal PDF.")


def _extract_with_pdfplumber(path: Path, use_ocr: bool) -> tuple[str, int, list[list[str]]]:
    with pdfplumber.open(path) as pdf:
        pages_text = []
        headers = []
        footers = []
        tables: list[list[str]] = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                headers.append(lines[0])
                footers.append(lines[-1])
            pages_text.append(text)
            for table in page.extract_tables() or []:
                table_md = table_to_markdown(table)
                if table_md:
                    tables.append(table_md)
        cleaned = remove_repeated_headers(pages_text, headers, footers)
        if use_ocr and not cleaned.strip():
            cleaned = ocr_pdf(path)
        return cleaned, len(pdf.pages), tables


def _extract_with_pymupdf(path: Path, use_ocr: bool) -> tuple[str, int, list[list[str]]]:
    doc = fitz.open(path)  # type: ignore[call-arg]
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()
    extracted = "\n".join(pages_text)
    if use_ocr and not extracted.strip():
        extracted = ocr_pdf(path)
    return extracted, len(pages_text), []


def ocr_pdf(path: Path) -> str:
    if pytesseract is None or fitz is None:
        logging.info("OCR non disponibile, skip.")
        return ""
    logging.info("OCR attivato per %s", path.name)
    doc = fitz.open(path)  # type: ignore[call-arg]
    ocr_text = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            text = pytesseract.image_to_string(img_bytes, lang="ita")
            ocr_text.append(text)
    except Exception as exc:
        raise OCRError(str(exc)) from exc
    finally:
        doc.close()
    return "\n".join(ocr_text)
