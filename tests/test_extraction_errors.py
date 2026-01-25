import pytest
from pathlib import Path

from normativa_processor.extraction.pdf_extractor import extract_text_pdf
from normativa_processor.core.exceptions import PDFExtractionError


def test_extract_text_pdf_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.pdf"
    with pytest.raises(PDFExtractionError):
        extract_text_pdf(missing, use_ocr=False)
