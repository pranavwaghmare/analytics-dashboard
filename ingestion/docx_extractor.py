"""DOCX Extraction engine using python-docx.
Extracts:
- Document hierarchy (Title, Heading 1, Heading 2, Body) in natural flow order
- Tables interleaved with paragraphs, inheriting the correct immediate parent section
- Clean table structures with empty spacer columns pruned
- Virtual page estimation for granular page provenance
"""

import os
from typing import List, Dict, Any
import docx
from docx.text.paragraph import Paragraph
from docx.table import Table
from ingestion.pdf_extractor import RawTable, RawParagraph, DocumentPage


class DOCXExtractor:
    @staticmethod
    def extract(file_path: str) -> Dict[str, Any]:
        """Extracts text, headings, and tables from DOCX document in flow order."""
        doc = docx.Document(file_path)
        doc_title = os.path.basename(file_path).replace(".docx", "").replace("_", " ").title()
        
        pages: List[DocumentPage] = []
        all_tables: List[RawTable] = []
        all_paragraphs: List[RawParagraph] = []
        
        current_section = ""
        current_page_no = 1
        current_page_chars = 0
        PAGE_CHAR_THRESHOLD = 2800  # Standard virtual page (~400-500 words)
        
        current_page_paras: List[RawParagraph] = []
        current_page_tables: List[RawTable] = []
        current_page_text: List[str] = []
        
        table_idx = 0
        
        def commit_page():
            nonlocal current_page_no, current_page_chars, current_page_paras, current_page_tables, current_page_text
            if current_page_paras or current_page_tables or current_page_text:
                page_obj = DocumentPage(
                    page_number=current_page_no,
                    text="\n\n".join(current_page_text),
                    paragraphs=list(current_page_paras),
                    tables=list(current_page_tables)
                )
                pages.append(page_obj)
                current_page_paras = []
                current_page_tables = []
                current_page_text = []
                current_page_chars = 0
                current_page_no += 1

        # Traverse body elements in natural document flow order
        for child in doc.element.body:
            if child.tag.endswith('p'):
                p = Paragraph(child, doc)
                text = p.text.replace('\xa0', ' ').replace('\u202f', ' ').strip()
                if not text:
                    continue
                
                # Check for page break elements in runs
                has_page_break = False
                for r in p.runs:
                    xml = r._r.xml
                    if 'w:br w:type="page"' in xml or 'w:lastRenderedPageBreak' in xml:
                        has_page_break = True
                        break
                        
                style_name = p.style.name.lower() if p.style else ""
                
                # Determine heading status
                is_heading = "heading" in style_name or "title" in style_name
                heading_lvl = 1 if "1" in style_name else (2 if "2" in style_name else 0)
                
                # Heading fallback: short bold runs or uppercase
                if not is_heading and len(text) < 80:
                    runs = [r for r in p.runs if r.text.strip()]
                    if runs and all(r.bold for r in runs):
                        is_heading = True
                        heading_lvl = 2
                    elif text.isupper() and len(text.split()) <= 6:
                        is_heading = True
                        heading_lvl = 2
                
                if "title" in style_name:
                    doc_title = text
                    is_heading = True
                    heading_lvl = 1
                elif is_heading:
                    current_section = text
                
                para_obj = RawParagraph(
                    text=text,
                    page_number=current_page_no,
                    section_title=current_section,
                    is_heading=is_heading,
                    heading_level=heading_lvl
                )
                current_page_paras.append(para_obj)
                all_paragraphs.append(para_obj)
                current_page_text.append(text)
                current_page_chars += len(text)
                
                if has_page_break or current_page_chars >= PAGE_CHAR_THRESHOLD:
                    commit_page()

            elif child.tag.endswith('tbl'):
                t = Table(child, doc)
                if not t.rows or len(t.rows) < 2:
                    continue
                
                # Extract all row cell texts
                raw_grid: List[List[str]] = []
                for r in t.rows:
                    raw_grid.append([c.text.strip() for c in r.cells])
                
                if not raw_grid or not raw_grid[0]:
                    continue
                
                num_cols = len(raw_grid[0])
                # Prune columns that are completely empty across all rows (spacer columns)
                active_col_indices = [
                    col_idx for col_idx in range(num_cols)
                    if any(row[col_idx].strip() for row in raw_grid if col_idx < len(row))
                ]
                
                if not active_col_indices:
                    continue
                
                cleaned_headers = [raw_grid[0][col_idx] for col_idx in active_col_indices]
                cleaned_rows = [
                    [row[col_idx] if col_idx < len(row) else "" for col_idx in active_col_indices]
                    for row in raw_grid[1:]
                ]
                
                table_obj = RawTable(
                    headers=cleaned_headers,
                    rows=cleaned_rows,
                    page_number=current_page_no,
                    section_title=current_section,
                    table_index=table_idx
                )
                current_page_tables.append(table_obj)
                all_tables.append(table_obj)
                table_idx += 1
                md_repr = table_obj.to_markdown()
                current_page_text.append(md_repr)
                current_page_chars += len(md_repr)
                
                if current_page_chars >= PAGE_CHAR_THRESHOLD:
                    commit_page()
                    
        # Commit final page
        commit_page()
        
        if not pages:
            pages = [DocumentPage(page_number=1, text="", paragraphs=[], tables=[])]
            
        full_doc_text = "\n\n".join(p.text for p in pages)
        
        return {
            "title": doc_title,
            "file_path": file_path,
            "file_type": "docx",
            "page_count": len(pages),
            "pages": pages,
            "all_tables": all_tables,
            "full_text": full_doc_text
        }
