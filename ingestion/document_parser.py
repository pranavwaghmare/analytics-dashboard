"""Unified Document Ingestion Router.
Detects document format and delegates to specialized extractors:
- PDF -> PDFExtractor
- DOCX -> DOCXExtractor
- XLSX / CSV -> SpreadsheetExtractor
"""

import os
from typing import Dict, Any, Optional
import re
import pandas as pd
from ingestion.pdf_extractor import PDFExtractor, RawTable, RawParagraph, DocumentPage
from ingestion.docx_extractor import DOCXExtractor


class DocumentParser:
    @classmethod
    def parse(cls, file_path: str, original_title: Optional[str] = None) -> Dict[str, Any]:
        """Parses any supported document format and returns a canonical DocumentTree dictionary."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document not found: {file_path}")
            
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == ".pdf":
            res = PDFExtractor.extract(file_path)
        elif ext in [".docx", ".doc"]:
            res = DOCXExtractor.extract(file_path)
        elif ext in [".xlsx", ".xls", ".csv"]:
            res = cls._parse_spreadsheet(file_path, ext)
        else:
            raise ValueError(f"Unsupported file format '{ext}'. Supported formats: PDF, DOCX, XLSX, CSV.")
            
        if original_title:
            res["title"] = original_title
        elif re.search(r'^(?:tmp[a-z0-9_]+|temp[a-z0-9_]+)$', res.get("title", ""), re.IGNORECASE):
            # Attempt to find prominent heading from first page
            found_title = None
            if res.get("pages"):
                first_page = res["pages"][0]
                for p in getattr(first_page, "paragraphs", []):
                    if getattr(p, "is_heading", False) and len(p.text) > 3:
                        found_title = p.text.strip()
                        break
            res["title"] = found_title or "Executive Formal Report"
            
        return res

    @classmethod
    def _parse_spreadsheet(cls, file_path: str, ext: str) -> Dict[str, Any]:
        """Parses tabular spreadsheets as a single-page document with tables."""
        doc_title = os.path.basename(file_path).rsplit(".", 1)[0].replace("_", " ").title()
        if ext == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        headers = [str(c) for c in df.columns]
        rows = [[str(val) if pd.notna(val) else "" for val in row] for row in df.values]
        
        table = RawTable(
            headers=headers,
            rows=rows,
            page_number=1,
            section_title="Data Sheet",
            table_index=0
        )
        
        para = RawParagraph(
            text=f"Spreadsheet dataset containing {len(df)} records across columns: {', '.join(headers)}.",
            page_number=1,
            section_title="Data Sheet",
            is_heading=False
        )
        
        page = DocumentPage(
            page_number=1,
            text=table.to_markdown(),
            paragraphs=[para],
            tables=[table]
        )
        
        return {
            "title": doc_title,
            "file_path": file_path,
            "file_type": ext.lstrip("."),
            "page_count": 1,
            "pages": [page],
            "all_tables": [table],
            "full_text": table.to_markdown()
        }
