"""Table Normalization and Structure Parsing Engine.
Responsibilities:
- Cleans and repairs table headers (detecting wrapped header lines, multi-index fragments)
- Classifies table semantic topology generically:
    1. PERFORMANCE_COMPARISON (periods/deltas in columns, diverse metrics in rows)
    2. CATEGORICAL_BREAKDOWN (homogeneous entities in rows, measures/periods in columns)
    3. NON_ANALYTICAL_SCHEDULE (calendar dates, option exercise disclosures, etc.)
- Cleans and parses numeric strings (e.g., "164,600", "96.2%", "₹545 Cr", "+21.1%")
- Eliminates generic labels ("Financial Line Item", "Col_1") in favor of contextual dimensions
"""

from enum import Enum
import re
from typing import List, Dict, Any, Tuple, Optional


class TableTopology(str, Enum):
    PERFORMANCE_COMPARISON = "performance_comparison"
    CATEGORICAL_BREAKDOWN = "categorical_breakdown"
    NON_ANALYTICAL_SCHEDULE = "non_analytical_schedule"


def parse_numeric_cell(cell_str: str) -> Tuple[Optional[float], str, Optional[float]]:
    """
    Extracts numeric value, unit, and optional sign/percentage from a table cell.
    Returns: (numeric_value, unit, percentage_change_if_signed)
    """
    if not cell_str:
        return None, "", None
        
    s = cell_str.strip()
    
    # Check for growth/change signed pattern e.g. "+21.1%", "-5.6%", "15%"
    signed_pct_match = re.search(r'^([+-]?\d+(?:\.\d+)?)\s*%$', s)
    if signed_pct_match:
        val = float(signed_pct_match.group(1))
        return val, "%", val
        
    # Check standard percentage e.g. "96.2%"
    pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', s)
    if pct_match:
        val = float(pct_match.group(1))
        return val, "%", None
        
    # Check standard comma-separated or integer/float e.g. "164,600", "281,724", "13.64"
    # Handle currency symbols and parentheses for negative values: (1,234) -> -1234
    is_negative = False
    if re.search(r'^\s*\(([\d,.]+)\)\s*$', s):
        is_negative = True
        s = re.sub(r'^\s*\(([\d,.]+)\)\s*$', r'\1', s)
        
    clean_num_str = s.replace(",", "").replace("$", "").replace("₹", "").replace("€", "").strip()
    num_match = re.search(r'[-+]?\d+(?:\.\d+)?', clean_num_str)
    if num_match:
        try:
            val = float(num_match.group(0))
            if is_negative:
                val = -val
            # Detect unit suffix if any
            unit = ""
            if "cr" in s.lower():
                unit = "Crore"
            elif "lakh" in s.lower() or "lpa" in s.lower():
                unit = "Lakh"
            elif "%" in s:
                unit = "%"
            return val, unit, None
        except ValueError:
            pass
            
    return None, "", None


def clean_header_name(header: str) -> str:
    """Repairs fragmented header names caused by table wrapping."""
    if not header:
        return ""
    h = header.replace("\n", " ").strip()
    h = re.sub(r'\s+', ' ', h)
    # Fix broken currency / parenthesis artifacts
    h = re.sub(r'\(INR\s*C\s*r\)', '(INR Cr)', h)
    h = re.sub(r'\(n\s*Cr\)', '(INR Cr)', h)
    h = re.sub(r'\(n\s*CQr\)', '(INR Cr)', h)
    h = re.sub(r'^\)\s*', '', h)
    h = re.sub(r'\s*\(?Q$', '', h)
    return h.strip()


def deduplicate_headers(headers: List[str]) -> List[str]:
    """Ensures all column headers are unique, non-empty strings suitable for Pandas and PyArrow."""
    seen: Dict[str, int] = {}
    deduped: List[str] = []
    for i, h in enumerate(headers):
        clean_name = str(h).strip() if h is not None and str(h).strip() else f"Col_{i+1}"
        if clean_name in seen:
            seen[clean_name] += 1
            deduped.append(f"{clean_name}_{seen[clean_name]}")
        else:
            seen[clean_name] = 1
            deduped.append(clean_name)
    return deduped


def classify_table_topology(headers: List[str], rows: List[List[str]], section_title: str = "") -> TableTopology:
    """
    Generically classifies table topology from structural and semantic signals:
    - NON_ANALYTICAL_SCHEDULE: Calendar dates, option exercise tables, disclosures, roster tables
    - PERFORMANCE_COMPARISON: Multi-period comparison table with distinct performance metrics in rows
    - CATEGORICAL_BREAKDOWN: Homogeneous entities in rows (segments, departments, regions)
    """
    if not rows or len(rows) < 1 or len(headers) < 2:
        return TableTopology.NON_ANALYTICAL_SCHEDULE
        
    combined_headers = " ".join(h.lower() for h in headers)
    sec_lower = section_title.lower() if section_title else ""
    
    # 0. Governance / Roster tables
    if any(gov in sec_lower for gov in ["director", "executive officer", "governance", "committee members"]):
        return TableTopology.NON_ANALYTICAL_SCHEDULE

    # 1. Non-analytical schedule markers (calendar dates, option exercise schedules)
    schedule_keywords = [
        "declaration date", "record date", "payment date", "payable date",
        "grant date", "exercise date", "expiration date", "vesting date",
        "weighted average exercise price", "stock option activity", "contractual obligations"
    ]
    if any(kw in combined_headers for kw in schedule_keywords):
        return TableTopology.NON_ANALYTICAL_SCHEDULE
        
    # Check if > 35% of data cells are calendar dates (e.g. "September 19, 2024")
    date_pattern = re.compile(
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}|\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        re.IGNORECASE
    )
    date_cells = 0
    total_cells = 0
    for r in rows:
        for c in r[1:]:
            total_cells += 1
            if date_pattern.search(c):
                date_cells += 1
    if total_cells > 0 and (date_cells / total_cells) > 0.35:
        return TableTopology.NON_ANALYTICAL_SCHEDULE
        
    # Check if headers are repetitive non-distinguished words (e.g. repeated "Shares", "Amount" across 10 cols)
    non_first = [h.lower() for h in headers[1:]]
    if len(non_first) >= 4:
        share_amount_count = sum(1 for h in non_first if "shares" in h or "amount" in h)
        if (share_amount_count / len(non_first)) >= 0.7:
            return TableTopology.NON_ANALYTICAL_SCHEDULE

    # 2. Section context & Footnote / Disclosure schedule detection
    is_footnote_section = bool(re.search(
        r'\b(?:notes?\s+(?:to|\d+)|disclosures?|accounting\s+policies|commitments|statutory|schedules?|footnotes?|appendix|supplementary)\b',
        sec_lower
    ))
    
    # Check for heterogeneous semantic column types in disclosure tables (e.g. mix of amounts, duration, rates, or rollforwards)
    has_duration_col = any(re.search(r'\b(?:years?|months?|days?|life|term|tenure|maturit(?:y|ies))\b', h) for h in non_first)
    has_rate_col = any(re.search(r'\b(?:interest\s+rate|discount\s+rate|yield|effective\s+rate)\b', h) for h in non_first)
    has_rollforward_col = any(re.search(r'\b(?:acquisitions?|additions?|deductions?|retirements?|impairments?)\b', h) for h in non_first)
    
    if is_footnote_section and (has_duration_col or has_rate_col or has_rollforward_col):
        return TableTopology.NON_ANALYTICAL_SCHEDULE

    # 3. Performance Comparison Table vs Categorical Breakdown
    temporal_pattern = re.compile(
        r'(?:\b20\d\d\b|FY\s*\d\d|Q[1-4]|percentage\s+change|%\s*change|\bchange\b|growth|increase\s*/\s*\(decrease\))',
        re.IGNORECASE
    )
    temporal_matches = sum(1 for h in non_first if temporal_pattern.search(h))
    is_temporal_columns = len(non_first) > 0 and (temporal_matches / len(non_first)) >= 0.5
    has_explicit_change_col = any("change" in h or "%" in h for h in non_first)
    
    # Check row labels in Column 0
    row_labels = [r[0].strip() for r in rows if r and r[0].strip()]
    metric_word_pattern = re.compile(
        r'\b(?:revenue|income|margin|expense|earnings|cost|sales|profit|ebitda|tax|cash|assets|liabilities|equity|headcount|attrition|deliveries|volume|enrollment|placement|sla|debt|capex|per\s+share|percentage|rate)\b',
        re.IGNORECASE
    )
    metric_labeled_rows = sum(1 for lbl in row_labels if metric_word_pattern.search(lbl))
    
    # Check magnitude variance across rows in column 1 (e.g. 281,724 vs 13.64)
    c1_vals = []
    for r in rows:
        if len(r) > 1:
            v, _, _ = parse_numeric_cell(r[1])
            if v is not None and v > 0:
                c1_vals.append(v)
    huge_magnitude_spread = False
    if len(c1_vals) >= 3:
        if max(c1_vals) / max(min(c1_vals), 0.001) > 1000:
            huge_magnitude_spread = True

    if is_temporal_columns and (has_explicit_change_col or metric_labeled_rows >= 1 or huge_magnitude_spread):
        return TableTopology.PERFORMANCE_COMPARISON

    # Disclose tables in footnote sections without clear operational dimensions are schedules
    if is_footnote_section and not any(w in sec_lower for w in ["segment", "department", "operations", "results", "geographic"]):
        return TableTopology.NON_ANALYTICAL_SCHEDULE

    return TableTopology.CATEGORICAL_BREAKDOWN


def infer_dimension_name(dim_raw: str, section_title: str, headers: List[str], rows: List[List[str]]) -> str:
    """
    Infers a human-readable dimension name without relying on hardcoded generic placeholders like 'Financial Line Item'.
    """
    clean_raw = clean_header_name(dim_raw)
    is_scale_or_currency = bool(re.search(
        r'(?:in\s+)?(?:millions?|billions?|thousands?|crores?|lakhs?|usd|inr|\$)',
        clean_raw, re.IGNORECASE
    ))
    
    if clean_raw and not is_scale_or_currency and not clean_raw.lower().startswith("col_"):
        return clean_raw
        
    sec_lower = section_title.lower() if section_title else ""
    if "segment" in sec_lower:
        return "Segment"
    elif "department" in sec_lower or "staff" in sec_lower or "workforce" in sec_lower or "intangible" in sec_lower:
        return "Department" if "department" in sec_lower or "workforce" in sec_lower else "Asset Class"
    elif "region" in sec_lower or "zone" in sec_lower or "geography" in sec_lower:
        return "Region"
    elif "school" in sec_lower or "program" in sec_lower or "academic" in sec_lower:
        return "Program"
    elif "product" in sec_lower:
        return "Product Line"
    elif "channel" in sec_lower:
        return "Channel"
    elif "division" in sec_lower:
        return "Division"
        
    # Check sample row labels
    row_text = " ".join(r[0] for r in rows[:4] if r).lower()
    if any(w in row_text for w in ["cloud", "computing", "processes", "hardware", "software"]):
        return "Business Segment"
    if any(w in row_text for w in ["north", "south", "east", "west", "central"]):
        return "Region"
    if any(w in row_text for w in ["engineering", "sales", "marketing", "operations", "hr"]):
        return "Department"
    if any(w in row_text for w in ["common stock", "preferred stock"]):
        return "Stock Class"
        
    return "Category"


class TableNormalizer:
    @staticmethod
    def normalize_table(headers: List[str], rows: List[List[str]], section_title: str = "") -> Dict[str, Any]:
        """
        Analyzes table structure:
        - Repaired column names
        - Topology classification (Performance Comparison vs Categorical Breakdown vs Schedule)
        - Contextual dimension name inference
        - Parsed metric columns and clean rows
        """
        cleaned_headers = deduplicate_headers([clean_header_name(h) for h in headers])
        
        # Check if row 0 was a continuation of headers
        if rows and len(rows) > 1:
            first_row_numeric_count = sum(1 for cell in rows[0] if parse_numeric_cell(cell)[0] is not None)
            if first_row_numeric_count == 0 and len(rows[0]) == len(cleaned_headers):
                combined = []
                for h, sub in zip(cleaned_headers, rows[0]):
                    combined.append(f"{h} {sub}".strip())
                cleaned_headers = deduplicate_headers([clean_header_name(c) for c in combined])
                rows = rows[1:]

        topology = classify_table_topology(cleaned_headers, rows, section_title)
        
        dim_raw = cleaned_headers[0] if cleaned_headers else "Category"
        dim_name = infer_dimension_name(dim_raw, section_title, cleaned_headers, rows)

        # Detect default table unit from scale markers in headers
        default_unit = ""
        all_header_text = " ".join(headers).lower()
        if "billion" in all_header_text:
            default_unit = "Billion"
        elif "million" in all_header_text:
            default_unit = "Million"
        elif "thousand" in all_header_text:
            default_unit = "Thousand"
        elif "crore" in all_header_text:
            default_unit = "Crore"
        elif "lakh" in all_header_text:
            default_unit = "Lakh"
            
        metric_columns = []
        for col_idx in range(1, len(cleaned_headers)):
            col_name = cleaned_headers[col_idx]
            display_name = re.sub(r'_\d+$', '', col_name).strip()
            
            # Check how many rows have numeric values in this column
            numeric_cells = []
            for row in rows:
                if col_idx < len(row):
                    val, unit, _ = parse_numeric_cell(row[col_idx])
                    if val is not None:
                        numeric_cells.append((val, unit))
                        
            if len(numeric_cells) >= max(1, len(rows) * 0.4):
                unit = ""
                is_share_pct = ("market share" in col_name.lower() or "revenue share" in col_name.lower() or "share of" in col_name.lower()) and not any(s in col_name.lower() for s in ["shares", "per share"])
                if "%" in col_name or "rate" in col_name.lower() or is_share_pct or "change" in col_name.lower():
                    unit = "%"
                elif re.search(r'\b(?:per\s+share|eps)\b', col_name.lower()):
                    unit = "$ / share" if "$" in col_name or default_unit == "Million" or default_unit == "Billion" else "/ share"
                elif re.search(r'\b(?:years?|months?|days?|life|term|tenure)\b', col_name.lower()):
                    if "month" in col_name.lower():
                        unit = "Months"
                    elif "day" in col_name.lower():
                        unit = "Days"
                    else:
                        unit = "Years"
                elif "shares" in col_name.lower():
                    unit = f"{default_unit} Shares".strip() if default_unit else "Shares"
                elif "cr" in col_name.lower() or "crore" in col_name.lower():
                    unit = "Crore"
                elif "lpa" in col_name.lower() or "lakh" in col_name.lower():
                    unit = "Lakh"
                elif "employee" in col_name.lower() or "headcount" in col_name.lower():
                    unit = "Employees"
                elif "student" in col_name.lower():
                    unit = "Students"
                elif "deliver" in col_name.lower():
                    unit = "Deliveries"
                elif "count" in col_name.lower():
                    unit = "Units"
                else:
                    if numeric_cells and numeric_cells[0][1]:
                        unit = numeric_cells[0][1]
                    elif default_unit:
                        unit = default_unit
                        
                metric_columns.append({
                    "col_idx": col_idx,
                    "metric_name": display_name,
                    "unit": unit
                })

        return {
            "topology": topology,
            "dimension_name": dim_name,
            "headers": cleaned_headers,
            "metric_columns": metric_columns,
            "rows": rows,
            "default_unit": default_unit
        }
