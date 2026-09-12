"""PDF Extraction engine using pdfplumber and PyMuPDF (fitz).
Extracts:
- Text paragraphs with font hierarchy detection (headings vs body)
- Tables with header row detection and cell cleaning
- Page-by-page mapping and coordinate preservation
"""

import os
import re
from typing import List, Dict, Any, Optional
import pdfplumber
import pymupdf


def clean_cell_text(text: Optional[str]) -> str:
    """Cleans raw PDF/table cell text, fixing line breaks, artifacts, and multi-spaces."""
    if not text:
        return ""
    # Normalize unicode spaces and clean newlines
    cleaned = text.replace("\n", " ").replace("\r", " ")
    # Replace common font encoding quirks for currency symbols
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


class RawTable:
    def __init__(self, headers: List[str], rows: List[List[str]], page_number: int, section_title: str = "", table_index: int = 0):
        from ingestion.table_normalizer import deduplicate_headers
        clean_hdrs = [clean_cell_text(h) if clean_cell_text(h) else f"Col_{i}" for i, h in enumerate(headers)]
        self.headers = deduplicate_headers(clean_hdrs)
        self.rows = [[clean_cell_text(c) for c in row] for row in rows]
        self.page_number = page_number
        self.section_title = section_title
        self.table_index = table_index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "section_title": self.section_title,
            "table_index": self.table_index,
            "headers": self.headers,
            "rows": self.rows
        }

    def to_markdown(self) -> str:
        if not self.headers:
            return ""
        hdr_line = "| " + " | ".join(self.headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(self.headers)) + " |"
        row_lines = ["| " + " | ".join(row) + " |" for row in self.rows]
        return "\n".join([hdr_line, sep_line] + row_lines)


class RawParagraph:
    def __init__(self, text: str, page_number: int, section_title: str = "", is_heading: bool = False, heading_level: int = 0):
        self.text = text.strip()
        self.page_number = page_number
        self.section_title = section_title
        self.is_heading = is_heading
        self.heading_level = heading_level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "is_heading": self.is_heading,
            "heading_level": self.heading_level
        }


class DocumentPage:
    def __init__(self, page_number: int, text: str, paragraphs: List[RawParagraph], tables: List[RawTable]):
        self.page_number = page_number
        self.text = text
        self.paragraphs = paragraphs
        self.tables = tables


class PDFExtractor:
    @staticmethod
    def extract(file_path: str) -> Dict[str, Any]:
        """Extracts text, headings, and tables from PDF."""
        pages: List[DocumentPage] = []
        all_tables: List[RawTable] = []
        full_text_list = []
        doc_title = os.path.basename(file_path).replace(".pdf", "").replace("_", " ").title()
        
        # 1. Use PyMuPDF for font-based heading detection
        doc_fitz = pymupdf.open(file_path)
        page_headings: Dict[int, List[Dict[str, Any]]] = {}
        
        for p_no in range(len(doc_fitz)):
            fitz_page = doc_fitz[p_no]
            blocks = fitz_page.get_text("dict")["blocks"]
            headings = []
            
            for b in blocks:
                if b.get("type") == 0:  # text block
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            txt = span.get("text", "").strip()
                            sz = span.get("size", 10.0)
                            flags = span.get("flags", 0)  # 2 is italic, 16 is bold
                            if len(txt) > 3 and (sz >= 12.0 or flags & 16):
                                headings.append({
                                    "text": txt,
                                    "size": sz,
                                    "is_bold": bool(flags & 16),
                                    "bbox": span.get("bbox")
                                })
            page_headings[p_no + 1] = headings
        doc_fitz.close()

        # 2. Use pdfplumber for table extraction and structured page text
        with pdfplumber.open(file_path) as pdf:
            current_section = ""
            table_global_idx = 0
            
            for p_idx, page in enumerate(pdf.pages):
                p_num = p_idx + 1
                page_text = page.extract_text() or ""
                full_text_list.append(page_text)
                
                # Extract tables on this page
                raw_extracted_tables = page.extract_tables()
                page_tables: List[RawTable] = []
                
                for t in raw_extracted_tables:
                    if not t or len(t) < 2:
                        continue
                    # Clean empty rows
                    cleaned_t = [[cell if cell is not None else "" for cell in row] for row in t]
                    header = cleaned_t[0]
                    data_rows = cleaned_t[1:]
                    table_obj = RawTable(
                        headers=header,
                        rows=data_rows,
                        page_number=p_num,
                        section_title=current_section,
                        table_index=table_global_idx
                    )
                    page_tables.append(table_obj)
                    all_tables.append(table_obj)
                    table_global_idx += 1
                
                # Deconstruct paragraphs
                lines = [line.strip() for line in page_text.split("\n") if line.strip()]
                paragraphs: List[RawParagraph] = []
                p_headings = page_headings.get(p_num, [])
                
                current_p_buffer = []
                for line in lines:
                    # Check if this line is a heading
                    is_h = any(h["text"] in line or line in h["text"] for h in p_headings)
                    if is_h:
                        if current_p_buffer:
                            paragraphs.append(RawParagraph(
                                text=" ".join(current_p_buffer),
                                page_number=p_num,
                                section_title=current_section,
                                is_heading=False
                            ))
                            current_p_buffer = []
                        current_section = line
                        if p_num == 1 and not doc_title or doc_title in ["Financial Report", "Sales Operations Report"]:
                            # Infer better title if first heading is prominent
                            doc_title = line
                        paragraphs.append(RawParagraph(
                            text=line,
                            page_number=p_num,
                            section_title=current_section,
                            is_heading=True,
                            heading_level=1
                        ))
                    else:
                        current_p_buffer.append(line)
                
                if current_p_buffer:
                    paragraphs.append(RawParagraph(
                        text=" ".join(current_p_buffer),
                        page_number=p_num,
                        section_title=current_section,
                        is_heading=False
                    ))
                
                pages.append(DocumentPage(
                    page_number=p_num,
                    text=page_text,
                    paragraphs=paragraphs,
                    tables=page_tables
                ))

        return {
            "title": doc_title,
            "file_path": file_path,
            "file_type": "pdf",
            "page_count": len(pages),
            "pages": pages,
            "all_tables": all_tables,
            "full_text": "\n\n".join(full_text_list)
        }
