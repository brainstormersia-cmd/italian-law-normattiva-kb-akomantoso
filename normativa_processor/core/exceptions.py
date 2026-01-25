class NormativaProcessorError(Exception):
    """Errore base per il processor."""


class PDFExtractionError(NormativaProcessorError):
    """Errore durante estrazione PDF."""


class OCRError(NormativaProcessorError):
    """Errore durante OCR."""


class ParsingError(NormativaProcessorError):
    """Errore durante parsing gerarchia."""


class ValidationError(NormativaProcessorError):
    """Errore validazione chunks."""
