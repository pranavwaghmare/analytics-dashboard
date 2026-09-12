"""Ingestion package for document loading, PDF, DOCX, and spreadsheet parsing."""
from ingestion.table_normalizer import deduplicate_headers, TableNormalizer
from ingestion.pdf_extractor import PDFExtractor, RawTable, RawParagraph, DocumentPage
from ingestion.docx_extractor import DOCXExtractor
from ingestion.document_parser import DocumentParser

__all__ = [
    "deduplicate_headers",
    "TableNormalizer",
    "PDFExtractor",
    "RawTable",
    "RawParagraph",
    "DocumentPage",
    "DOCXExtractor",
    "DocumentParser"
]
