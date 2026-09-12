"""Deterministic / Heuristic Semantic Extraction Engine.
Extracts analytical primitives (metrics, series, comparisons, relationships)
from both tabular structures and prose paragraphs with exact provenance.
Serves as the robust offline baseline and deterministic foundation.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from ingestion.table_normalizer import TableNormalizer, TableTopology, parse_numeric_cell
from schema.models import (
    DocumentAnalyticsModel,
    StandaloneMetric,
    ComparisonItem,
    CategoricalSeries,
    CategoricalDataPoint,
    TimeSeries,
    TimeDataPoint,
    Relationship,
    AnalyticalInsight,
    ProvenanceRecord,
    GroundingStatus
)


def clean_metric_name(raw_name: str) -> str:
    """
    Cleans metric names while rigorously preserving compound noun phrases
    (e.g., 'Cash, cash equivalents, and short-term investments', 'Property, plant, and equipment',
    'Total operating expenses', 'Diluted earnings per share').
    Disentangles temporal preambles, possessive entities, and parenthetical/relative clauses.
    """
    if not raw_name:
        return ""
        
    cleaned = raw_name.strip()
    
    # 1. Patterns to strip
    discourse_marker_pattern = re.compile(
        r'^(?:financially|operationally|furthermore|moreover|additionally|in\s+addition|across\s+the\s+(?:company|organization|firm|enterprise|business)),\s*',
        re.IGNORECASE
    )
    
    date_span = r'(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s*\d{4}|\d{4})'
    multi_year_span = r'\d{4}(?:,\s*\d{4})*(?:,?\s*and\s+\d{4})*'

    temporal_patterns = [
        re.compile(r'^(?:for|in|during)\s+(?:the\s+)?(?:fiscal\s+)?(?:years?|quarters?|periods?)\s+ended\s+' + date_span + r',?\s*', re.IGNORECASE),
        re.compile(r'^(?:for|in|during)\s+(?:the\s+)?(?:fiscal\s+)?(?:years?|quarters?|periods?)\s+' + multi_year_span + r',?\s*', re.IGNORECASE),
        re.compile(r'^as\s+of\s+(?:' + date_span + r'(?:\s*(?:and|,)\s*' + date_span + r')*|' + multi_year_span + r'),?\s*', re.IGNORECASE),
        re.compile(r'^(?:on\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s*\d{4},?\s*', re.IGNORECASE),
        re.compile(r'^at\s+(?:the\s+end\s+of\s+)[^,]+,?\s*', re.IGNORECASE),
        re.compile(r'^during\s+(?:the\s+)?(?:fiscal\s+)?(?:years?\s+)?\d{4}(?:,\s*\d{4})*(?:,?\s*and\s+\d{4})?,?\s*', re.IGNORECASE),
    ]

    entity_pattern = re.compile(
        r'^(?:our|their|its|the\s+company(?:\'s|\’s)|[A-Za-z0-9]+(?:\'s|\’s))\s+',
        re.IGNORECASE
    )

    trailing_temporal_patterns = [
        re.compile(r'\s+(?:for\s+(?:both\s+)?(?:fiscal\s+)?(?:years?|quarters?|periods?)\s+' + multi_year_span + r')$', re.IGNORECASE),
        re.compile(r'\s+(?:as\s+of\s+[A-Za-z0-9,\s]+?|for\s+the\s+year\s+ended\s+[A-Za-z0-9,\s]+?)$', re.IGNORECASE),
    ]

    noise_pattern = re.compile(
        r'^(?:and|or|of|in|on|at|to|for|with|by|from|the|a|an|overall|total|our|their|its|including|as\s+well\s+as|there\s+(?:was|were))\s+',
        re.IGNORECASE
    )

    while True:
        original = cleaned
        cleaned = discourse_marker_pattern.sub('', cleaned).strip()
        for tp in temporal_patterns:
            cleaned = tp.sub('', cleaned).strip()
        cleaned = entity_pattern.sub('', cleaned).strip()
        for ttp in trailing_temporal_patterns:
            cleaned = ttp.sub('', cleaned).strip()
        cleaned = re.sub(r',\s*(?:which\s+includes|including|net\s+of|related\s+to|as\s+reported|measured\s+using).*$', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^[\s\-_*#>`~:\.,]+', '', cleaned).strip()
        cleaned = re.sub(r'[\s\-_*#>`~:\.,]+$', '', cleaned).strip()
        cleaned = noise_pattern.sub('', cleaned).strip()
        if cleaned == original or not cleaned:
            break

    # Filter out non-metrics (pure pronouns or dates)
    if re.search(r'^(?:there|it|we|they|he|she|this|that|these|those)$', cleaned, re.IGNORECASE):
        return ""
    if re.search(r'^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\b20\d\d\b)$', cleaned, re.IGNORECASE):
        return ""

    # Collapse duplicate inner spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'[\s\-_*#>`~:\.]+$', '', cleaned).strip()
    
    # Capitalization normalization
    if cleaned.isupper() or cleaned.islower():
        cleaned = cleaned.title()
    elif len(cleaned) > 1 and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
        
    return cleaned


def resolve_unit_and_scale(
    val_raw: str,
    metric_name: str,
    sentence_span: str = "",
    default_table_unit: str = ""
) -> Tuple[Optional[float], str]:
    """
    Rigorously resolves numerical value and semantic unit:
    - Non-financial measures (headcounts, percentages, days, students) never inherit currency.
    - Currency only attaches if explicit currency symbols ($ ₹ € £) or word tokens (\\bUSD\\b, \\bINR\\b, \\bEUR\\b, \\bGBP\\b, \\bRs\\.?\\b)
      are in val_raw or immediately adjacent (never from remote sentence context).
    - Prevents word-substring bugs like 'years' or 'shareholders' triggering 'INR'.
    - Assigns appropriate scale (Million, Billion, Lakh, Crore) only to monetary/volume values, not to rates, percentages, or durations.
    """
    val, raw_unit, _ = parse_numeric_cell(val_raw)
    if val is None:
        return None, ""
        
    m_lower = metric_name.lower().strip()
    v_lower = val_raw.lower().strip()
    
    # 1. Check if metric is per-share amount
    if re.search(r'\b(?:per\s+share|eps)\b', m_lower):
        curr = "USD"
        if "₹" in val_raw or bool(re.search(r'\b(?:INR|Rs\.?)\b', val_raw, re.IGNORECASE)):
            curr = "INR"
        elif "€" in val_raw or bool(re.search(r'\bEUR\b', val_raw)):
            curr = "EUR"
        return val, f"{curr} / share"

    # 2. Check if metric is a percentage, rate, yield, or margin
    if "%" in val_raw or "percent" in v_lower or "%" in raw_unit or re.search(r'\b(?:rate|margin|percentage|percent|yield|attrition|turnover|churn|ratio|market\s+share|revenue\s+share)\b', m_lower):
        return val, "%"

    # 3. Check if metric is a duration / time period
    if re.search(r'\b(?:years?|months?|days?|hours?|weeks?|quarters?|tenure)\b', v_lower) or re.search(r'\b(?:years?|months?|days?|hours?|weeks?|tenure|time-to-hire|transit\s+time|lead\s+time)\b', m_lower):
        if "day" in v_lower or "day" in m_lower:
            return val, "Days"
        elif "month" in v_lower or "month" in m_lower:
            return val, "Months"
        elif "hour" in v_lower or "hour" in m_lower:
            return val, "Hours"
        elif "week" in v_lower or "week" in m_lower:
            return val, "Weeks"
        return val, "Years"

    # 4. Check if metric is a count of people, records, entities, or physical objects
    count_noun_matches = [
        (r'\b(?:headcount|employees?|staff|workforce|people)\b', "Employees"),
        (r'\b(?:students?|enrollments?|undergraduates?|graduates?)\b', "Students"),
        (r'\b(?:faculty|professors?|teachers?)\b', "Faculty"),
        (r'\b(?:deliveries|delivery|packages?|shipments?)\b', "Deliveries"),
        (r'\b(?:patents?|papers?|publications?|citations?)\b', "Publications" if "paper" in m_lower or "pub" in m_lower else "Patents"),
        (r'\b(?:stockholders?|shareholders?|holders?)\b', "Stockholders" if "stock" in m_lower or "share" in m_lower else "Holders"),
        (r'\b(?:shares?)\b', "Shares"),
        (r'\b(?:users?|subscribers?|clients?|customers?)\b', "Users" if "user" in m_lower or "sub" in m_lower else "Customers"),
        (r'\b(?:units?|vehicles?|items?|orders?)\b', "Units" if "unit" in m_lower or "item" in m_lower else "Orders"),
    ]
    for pattern, label in count_noun_matches:
        if re.search(pattern, m_lower) or re.search(pattern, v_lower):
            if "million" in v_lower or "m" == raw_unit.lower():
                return val, f"Million {label}"
            elif "billion" in v_lower or "b" == raw_unit.lower():
                return val, f"Billion {label}"
            return val, label

    # 5. Monetary Currency & Scale resolution
    has_inr = "₹" in val_raw or bool(re.search(r'\b(?:INR|Rs\.?)\b', val_raw, re.IGNORECASE))
    has_usd = "$" in val_raw or bool(re.search(r'\bUSD\b', val_raw, re.IGNORECASE))
    has_eur = "€" in val_raw or bool(re.search(r'\bEUR\b', val_raw, re.IGNORECASE))
    has_gbp = "£" in val_raw or bool(re.search(r'\bGBP\b', val_raw, re.IGNORECASE))

    if not (has_inr or has_usd or has_eur or has_gbp) and sentence_span:
        idx = sentence_span.find(val_raw)
        if idx != -1:
            nbr = sentence_span[max(0, idx - 8) : min(len(sentence_span), idx + len(val_raw) + 8)]
            has_inr = "₹" in nbr or bool(re.search(r'\b(?:INR|Rs\.?)\b', nbr, re.IGNORECASE))
            has_usd = "$" in nbr or bool(re.search(r'\bUSD\b', nbr, re.IGNORECASE))
            has_eur = "€" in nbr or bool(re.search(r'\bEUR\b', nbr, re.IGNORECASE))
            has_gbp = "£" in nbr or bool(re.search(r'\bGBP\b', nbr, re.IGNORECASE))

    curr = ""
    if has_inr:
        curr = "INR"
    elif has_usd:
        curr = "USD"
    elif has_eur:
        curr = "EUR"
    elif has_gbp:
        curr = "GBP"

    # Resolve scale (Billion, Million, Crore, Lakh, Thousand)
    scale = ""
    if "billion" in v_lower or "b" == raw_unit.lower() or "billion" in default_table_unit.lower():
        scale = "Billion"
    elif "million" in v_lower or "m" == raw_unit.lower() or "million" in default_table_unit.lower():
        scale = "Million"
    elif "crore" in v_lower or "cr" in v_lower or "crore" in default_table_unit.lower():
        scale = "Crore"
    elif "lakh" in v_lower or "lpa" in v_lower or "lakh" in default_table_unit.lower():
        scale = "Lakh"
    elif "thousand" in v_lower or "k" == raw_unit.lower() or "thousand" in default_table_unit.lower():
        scale = "Thousand"
    elif default_table_unit and default_table_unit not in ["%", "Ratio"]:
        scale = default_table_unit

    final_unit_parts = []
    if scale:
        final_unit_parts.append(scale)
    if curr:
        final_unit_parts.append(curr)

    final_unit = " ".join(final_unit_parts).strip()
    return val, final_unit


class HeuristicExtractor:
    @classmethod
    def extract(cls, doc_tree: Dict[str, Any], model_name: Optional[str] = None) -> DocumentAnalyticsModel:
        """Extracts complete analytical model deterministically from document tree."""
        doc_title = doc_tree.get("title", "Organizational Report")
        file_path = doc_tree.get("file_path", "")
        doc_name = file_path.split("/")[-1].split("\\")[-1] if file_path else "document"
        pages = doc_tree.get("pages", [])
        all_tables = doc_tree.get("all_tables", [])
        full_text = doc_tree.get("full_text", "")
        total_pages = max(len(pages), 1)
        
        # 1. Domain & Reporting Period Inference
        inferred_domain = cls._infer_domain(full_text)
        reporting_period = cls._infer_reporting_period(full_text)

        # Sanitize temp file names (e.g. Tmp8g0ltbby) to meaningful titles
        if re.search(r'^(?:tmp[a-z0-9_]+|temp[a-z0-9_]+)$', doc_title, re.IGNORECASE):
            found_title = None
            for p in pages[:2]:
                for para in getattr(p, "paragraphs", []):
                    if getattr(para, "is_heading", False) and len(para.text) > 3 and not re.search(r'^(?:table|page|\d+)', para.text, re.IGNORECASE):
                        found_title = para.text.strip().title()
                        break
                if found_title:
                    break
            doc_title = found_title or f"{inferred_domain} Performance Report"
        
        standalone_metrics: List[StandaloneMetric] = []
        comparisons: List[ComparisonItem] = []
        categorical_series: List[CategoricalSeries] = []
        relationships: List[Relationship] = []
        insights: List[AnalyticalInsight] = []

        # 2. Extract from Prose Paragraphs
        for page in pages:
            p_num = page.page_number
            rel_pos = p_num / total_pages
            for para in page.paragraphs:
                if para.is_heading or not para.text:
                    continue
                sentences = re.split(r'(?<=[.!?])\s+', para.text)
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean or len(s_clean) < 10:
                        continue
                    cls._extract_from_sentence(
                        s_clean, p_num, rel_pos, para.section_title, doc_name,
                        standalone_metrics, comparisons, categorical_series, relationships, insights
                    )

        # 3. Extract from Tables
        for t_idx, raw_tbl in enumerate(all_tables):
            cls._extract_from_table(
                raw_tbl, t_idx, doc_name,
                standalone_metrics, comparisons, categorical_series
            )

        # 4. Deduplicate Metrics and Comparisons
        deduped_metrics = cls._deduplicate_metrics(standalone_metrics)
        deduped_comparisons = cls._deduplicate_comparisons(comparisons)

        # 5. Generate Executive Summary if empty
        summary = cls._generate_summary(doc_title, inferred_domain, reporting_period, deduped_metrics, categorical_series)

        model = DocumentAnalyticsModel(
            document_title=doc_title,
            inferred_domain=inferred_domain,
            reporting_period=reporting_period,
            executive_summary=summary,
            standalone_metrics=deduped_metrics,
            comparisons=deduped_comparisons,
            categorical_series=categorical_series,
            time_series=[],
            relationships=relationships,
            insights=insights,
            extraction_metadata={"method": "deterministic_heuristic", "tables_processed": len(all_tables)}
        )
        return model

    @classmethod
    def _infer_domain(cls, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ["revenue", "ebitda", "profit", "debt", "financial", "capex", "balance sheet"]):
            return "Financial"
        elif any(w in t for w in ["headcount", "attrition", "time-to-hire", "diversity", "enps", "workforce"]):
            return "Human Resources"
        elif any(w in t for w in ["logistics", "sla", "deliveries", "return rate", "supply chain", "transit"]):
            return "Sales & Operations"
        elif any(w in t for w in ["enrollment", "placement", "academic", "faculty", "curriculum", "scopus", "gpa", "ctc"]):
            return "Academic"
        return "Organizational Management"

    @classmethod
    def _infer_reporting_period(cls, text: str) -> Optional[str]:
        match = re.search(r'(Q[1-4]\s*(?:FY)?\d{2,4}|FY\s*\d{2,4}|Academic Year\s*\d{4}-\d{2,4}|AY\s*\d{4}-\d{2,4}|\b20\d{2}\b)', text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
        return None

    @classmethod
    def _extract_from_sentence(
        cls, s: str, p_num: int, rel_pos: float, section: str, doc_name: str,
        metrics: List[StandaloneMetric], comparisons: List[ComparisonItem],
        series_list: List[CategoricalSeries], relationships: List[Relationship], insights: List[AnalyticalInsight]
    ):
        s_lower = s.lower()
        
        # Preprocess sentence: remove leading discourse transition clause and normalize spaces
        s = s.replace('\xa0', ' ').replace('\u202f', ' ')
        s_proc = re.sub(
            r'^(?:financially|operationally|furthermore|moreover|additionally|in\s+addition|during\s+the\s+(?:fiscal\s+)?(?:year|period|quarter)|in\s+(?:fiscal\s+)?(?:year\s+)?\d{4}|across\s+the\s+(?:company|organization|firm|enterprise|business)),\s*',
            '', s, flags=re.IGNORECASE
        ).strip()
        s_proc = s_proc.replace('\xa0', ' ').replace('\u202f', ' ')

        prov = ProvenanceRecord(
            source_document=doc_name,
            page_number=p_num,
            section_title=section,
            verbatim_source_span=s,
            source_type="prose"
        )

        # Helper to determine favorable direction
        def get_fav_direction(name: str) -> str:
            if any(neg in name.lower() for neg in ["attrition", "cost", "debt", "defect", "return rate", "time-to-hire", "expense"]):
                return "down"
            return "up"

        # Check if sentence has an explicit period preamble
        period_match = re.search(
            r'(?:for\s+(?:the\s+)?(?:fiscal\s+)?(?:year|quarter|period)\s+ended\s+([A-Za-z0-9,\s]+?)|as\s+of\s+([A-Za-z0-9,\s]+?)|in\s+(?:fiscal\s+)?(?:year\s+)?(\d{4})|during\s+(?:fiscal\s+)?(?:years?\s+)?(\d{4}))',
            s, re.IGNORECASE
        )
        period_context = None
        if period_match:
            for g in period_match.groups():
                if g:
                    period_context = g.strip()
                    break

        # Pattern 1: Level + Change Statement
        level_change_match = re.search(
            r'([A-Za-z0-9\s&/,\(\)\'\-]+?)\s+(?:was|were|totaled|reached|stood\s+at|surpassed)\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k))?)(?:,\s*|\s+(?:and\s+)?(?:which\s+)?)(?:up|down|increased\s+by|decreased\s+by|increased|decreased|growing\s+by|growing|grew|fell|dropped|declined)\s+([+-]?\d+(?:\.\d+)?)\s*(?:%|percent)',
            s_proc, re.IGNORECASE
        )
        if level_change_match:
            raw_metric = level_change_match.group(1).strip()
            metric_name = clean_metric_name(raw_metric)
            val_raw = level_change_match.group(2)
            pct_raw = level_change_match.group(3)
            
            val, unit = resolve_unit_and_scale(val_raw, metric_name, s)
            pct_val = float(pct_raw) if pct_raw else None
            
            is_decrease = any(w in s_proc[level_change_match.start():level_change_match.end()].lower() for w in ["down", "decreased", "fell", "dropped", "declined"])
            if is_decrease and pct_val and pct_val > 0:
                pct_val = -pct_val
                
            if val is not None and len(metric_name) > 1:
                fav = get_fav_direction(metric_name)
                prev_val = round(val / (1 + (pct_val / 100.0)), 2) if pct_val is not None and (1 + (pct_val / 100.0)) != 0 else None
                delta_abs = round(val - prev_val, 2) if prev_val is not None else None

                metrics.append(StandaloneMetric(
                    id=f"metric_{len(metrics)+1}",
                    name=metric_name,
                    current_value=val,
                    display_value=f"{val:g} {unit}".strip(),
                    unit=unit,
                    previous_value=prev_val,
                    change_abs=delta_abs,
                    change_pct=pct_val,
                    comparison_period=period_context or "YoY",
                    favorable_direction=fav,
                    provenance=prov
                ))

                if prev_val is not None:
                    comparisons.append(ComparisonItem(
                        id=f"comp_{len(comparisons)+1}",
                        metric_name=metric_name,
                        baseline_label="Previous",
                        baseline_value=prev_val,
                        current_label="Current",
                        current_value=val,
                        unit=unit,
                        delta_abs=delta_abs,
                        delta_pct=pct_val,
                        favorable_direction=fav,
                        provenance=prov
                    ))
                return

        # Pattern 2: Comparative Pair with "respectively"
        comp_pair_match = re.search(
            r'([A-Za-z0-9\s&/,\(\)\'\-]+?)\s+(?:totaled|were|was|stood\s+at)\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k))?)\s+and\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k))?)\s+as\s+of\s+([A-Za-z0-9,\s]+?)\s+and\s+([A-Za-z0-9,\s]+?)(?:,\s*respectively|\s+respectively)',
            s_proc, re.IGNORECASE
        )
        if comp_pair_match:
            raw_metric = comp_pair_match.group(1).strip()
            metric_name = clean_metric_name(raw_metric)
            val1_raw = comp_pair_match.group(2)
            val2_raw = comp_pair_match.group(3)
            p1 = comp_pair_match.group(4).strip()
            p2 = comp_pair_match.group(5).strip()

            v1, u1 = resolve_unit_and_scale(val1_raw, metric_name, s)
            v2, u2 = resolve_unit_and_scale(val2_raw, metric_name, s)

            if v1 is not None and v2 is not None and len(metric_name) > 1:
                unit = u1 or u2 or ""
                delta_abs = round(v1 - v2, 2)
                delta_pct = round((delta_abs / abs(v2)) * 100.0, 1) if v2 != 0 else None
                fav = get_fav_direction(metric_name)

                comparisons.append(ComparisonItem(
                    id=f"comp_{len(comparisons)+1}",
                    metric_name=metric_name,
                    baseline_label=p2,
                    baseline_value=v2,
                    current_label=p1,
                    current_value=v1,
                    unit=unit,
                    delta_abs=delta_abs,
                    delta_pct=delta_pct,
                    favorable_direction=fav,
                    provenance=prov
                ))

                metrics.append(StandaloneMetric(
                    id=f"metric_{len(metrics)+1}",
                    name=metric_name,
                    current_value=v1,
                    display_value=f"{v1:g} {unit}".strip(),
                    unit=unit,
                    previous_value=v2,
                    change_abs=delta_abs,
                    change_pct=delta_pct,
                    comparison_period=p1 or "YoY",
                    favorable_direction=fav,
                    provenance=prov
                ))
                return

        # Pattern 3: Explicit Growth / Delta statement to target value
        # e.g., "Revenue increased by 14% year-over-year to INR 842 crore"
        # or "Operating income grew 17 percent to $128.5 billion"
        growth_match = re.search(
            r'([A-Za-z0-9\s&/,\(\)\'\-]+?)\s+(?:increased|rose|grew|expanded|surged|declined|fell|dropped)\s+(?:by\s+)?([+-]?\d+(?:\.\d+)?(?:\s*(?:%|percent))?)\s*(?:year-over-year|yoy|qoq|mom)?\s*to\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k))?)',
            s_proc, re.IGNORECASE
        )
        if growth_match:
            raw_metric = growth_match.group(1).strip()
            metric_name = clean_metric_name(raw_metric)
            delta_raw = growth_match.group(2)
            val_raw = growth_match.group(3)
            
            val, unit = resolve_unit_and_scale(val_raw, metric_name, s)
            pct_val, _, _ = parse_numeric_cell(delta_raw)
            
            verb_portion = s_proc[growth_match.start():growth_match.end()].lower()
            if any(dec in verb_portion for dec in ["declined", "fell", "dropped"]) and pct_val and pct_val > 0:
                pct_val = -pct_val

            if val is not None and len(metric_name) > 1:
                prev_val = round(val / (1 + (pct_val / 100.0)), 1) if pct_val is not None and (1 + (pct_val / 100.0)) != 0 else None
                fav = get_fav_direction(metric_name)
                delta_abs = round(val - prev_val, 2) if prev_val is not None else None
                
                metrics.append(StandaloneMetric(
                    id=f"metric_{len(metrics)+1}",
                    name=metric_name,
                    current_value=val,
                    display_value=f"{val:g} {unit}".strip(),
                    unit=unit,
                    previous_value=prev_val,
                    change_abs=delta_abs,
                    change_pct=pct_val,
                    comparison_period=period_context or "YoY",
                    favorable_direction=fav,
                    provenance=prov
                ))

                if prev_val is not None:
                    comparisons.append(ComparisonItem(
                        id=f"comp_{len(comparisons)+1}",
                        metric_name=metric_name,
                        baseline_label="Previous",
                        baseline_value=prev_val,
                        current_label="Current",
                        current_value=val,
                        unit=unit,
                        delta_abs=delta_abs,
                        delta_pct=pct_val,
                        favorable_direction=fav,
                        provenance=prov
                    ))
                return

        # Pattern 4: Two-point improvement / decline
        # e.g., "EBITDA margin improved from 18.2% to 20.1%" or "Attrition declined from 13.4% to 11.2%"
        comp_match = re.search(
            r'([A-Za-z0-9\s&/,\(\)\'\-]+?)\s+(?:improved|declined|increased|decreased|fell|rose|expanded|dropped|reached)\s+(?:from\s+([₹$€]?\d+(?:\.\d+)?%?)\s+to\s+([₹$€]?\d+(?:\.\d+)?%?)|([₹$€]?\d+(?:\.\d+)?%?)\s+compared\s+to\s+([₹$€]?\d+(?:\.\d+)?%?))',
            s_proc, re.IGNORECASE
        )
        if comp_match:
            raw_metric = comp_match.group(1).strip()
            metric_name = clean_metric_name(raw_metric)
            
            if comp_match.group(2) and comp_match.group(3):
                base_raw, curr_raw = comp_match.group(2), comp_match.group(3)
            else:
                curr_raw, base_raw = comp_match.group(4), comp_match.group(5)
                
            base_val, b_unit = resolve_unit_and_scale(base_raw, metric_name, s)
            curr_val, c_unit = resolve_unit_and_scale(curr_raw, metric_name, s)
            
            if base_val is not None and curr_val is not None and len(metric_name) > 1:
                unit = c_unit or b_unit or ("%" if "%" in s else "")
                delta_abs = round(curr_val - base_val, 2)
                delta_pct = round((delta_abs / abs(base_val)) * 100.0, 1) if base_val != 0 else None
                fav = get_fav_direction(metric_name)
                
                comparisons.append(ComparisonItem(
                    id=f"comp_{len(comparisons)+1}",
                    metric_name=metric_name,
                    baseline_label="Previous",
                    baseline_value=base_val,
                    current_label="Current",
                    current_value=curr_val,
                    unit=unit,
                    delta_abs=delta_abs,
                    delta_pct=delta_pct,
                    favorable_direction=fav,
                    provenance=prov
                ))
                
                metrics.append(StandaloneMetric(
                    id=f"metric_{len(metrics)+1}",
                    name=metric_name,
                    current_value=curr_val,
                    display_value=f"{curr_val}{unit}",
                    unit=unit,
                    previous_value=base_val,
                    change_abs=delta_abs,
                    change_pct=delta_pct,
                    comparison_period=period_context or "YoY",
                    favorable_direction=fav,
                    provenance=prov
                ))
                return

        # Pattern 5: General metric level e.g. "Total undergraduate enrollment expanded to 3,420 students"
        level_match = re.search(
            r'([A-Za-z0-9\s&/,\(\)\'\-]+?)\s+(?:reached|stood\s+at|expanded\s+to|totaled|was|were)\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|students|deliveries|employees|papers|days))?)',
            s_proc, re.IGNORECASE
        )
        if level_match:
            raw_metric = level_match.group(1).strip()
            if not raw_metric.lower().strip().endswith("there"):
                metric_name = clean_metric_name(raw_metric)
                val_raw = level_match.group(2)
                val, unit = resolve_unit_and_scale(val_raw, metric_name, s)
                if val is not None and len(metric_name) > 1:
                    pct_match = re.search(r'(?:up|increased by|grown by)\s+([+-]?\d+(?:\.\d+)?%?)', s, re.IGNORECASE)
                    pct_val = parse_numeric_cell(pct_match.group(1))[0] if pct_match else None
                    fav = get_fav_direction(metric_name)
                    
                    metrics.append(StandaloneMetric(
                        id=f"metric_{len(metrics)+1}",
                        name=metric_name,
                        current_value=val,
                        display_value=f"{val:g} {unit}".strip(),
                        unit=unit,
                        change_pct=pct_val,
                        comparison_period=period_context or ("QoQ" if "qoq" in s_lower else ("YoY" if "yoy" in s_lower else None)),
                        favorable_direction=fav,
                        provenance=prov
                    ))
                    return

        # Pattern 5b: "There were [value] [noun/metric]" e.g. "As of July 24, 2025, there were 77,014 stockholders of record"
        there_match = re.search(
            r'there\s+(?:was|were)\s+((?:INR|USD|EUR|Rs\.?|[₹$€])?\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k))?)\s+([A-Za-z0-9\s&/,\(\)\'\-]+?)(?:\.|\,|$)',
            s_proc, re.IGNORECASE
        )
        if there_match:
            val_raw = there_match.group(1)
            raw_metric = there_match.group(2)
            metric_name = clean_metric_name(raw_metric)
            if metric_name and len(metric_name) > 2:
                val, unit = resolve_unit_and_scale(val_raw, metric_name, s)
                if val is not None:
                    metrics.append(StandaloneMetric(
                        id=f"metric_{len(metrics)+1}",
                        name=metric_name,
                        current_value=val,
                        display_value=f"{val:g} {unit}".strip(),
                        unit=unit,
                        comparison_period=period_context,
                        favorable_direction=get_fav_direction(metric_name),
                        provenance=prov
                    ))
                    return

        # Pattern 6: Composition / Breakdown in prose
        if "accounted for" in s_lower or "followed by" in s_lower:
            parts = re.findall(r'([A-Za-z\s&]+?)\s+(?:accounted\s+for|at)\s+(\d+(?:\.\d+)?%?)', s)
            if len(parts) >= 2:
                items = []
                total_pct = 0.0
                for label, p_str in parts:
                    clean_label = re.sub(r'^(and|followed by|,)\s*', '', label, flags=re.IGNORECASE).strip()
                    val, _, _ = parse_numeric_cell(p_str)
                    if val is not None and len(clean_label) > 1:
                        items.append(CategoricalDataPoint(label=clean_label.title(), value=val))
                        total_pct += val
                        
                if items:
                    series_list.append(CategoricalSeries(
                        id=f"series_prose_{len(series_list)+1}",
                        metric_name="Workforce Distribution",
                        dimension_name="Department",
                        unit="%",
                        is_part_of_whole=abs(total_pct - 100.0) < 5.0,
                        items=items,
                        provenance=prov
                    ))

        # Pattern 7: Drivers & Relationships
        driver_match = re.search(r'primarily\s+driven\s+by\s+(?:a\s+)?(\d+(?:\.\d+)?%?\s+(?:increase|decrease|growth)\s+in\s+([A-Za-z\s]+))', s, re.IGNORECASE)
        if driver_match:
            detail_desc = driver_match.group(1).strip()
            driver_subject = driver_match.group(2).strip().title()
            relationships.append(Relationship(
                id=f"rel_{len(relationships)+1}",
                subject_metric="Revenue",
                driver_metric=driver_subject,
                relationship_type="driven_by",
                description=f"Revenue growth was primarily driven by {detail_desc}.",
                provenance=prov
            ))

    @classmethod
    def _extract_from_table(
        cls, raw_tbl: Any, t_idx: int, doc_name: str,
        metrics: List[StandaloneMetric], comparisons: List[ComparisonItem],
        series_list: List[CategoricalSeries]
    ):
        norm = TableNormalizer.normalize_table(raw_tbl.headers, raw_tbl.rows, section_title=raw_tbl.section_title)
        topology = norm["topology"]
        dim_name = norm["dimension_name"]
        metric_cols = norm["metric_columns"]
        rows = norm["rows"]
        headers = norm["headers"]
        default_unit = norm.get("default_unit", "")
        
        # 1. Skip non-analytical schedules from chart generation
        if topology == TableTopology.NON_ANALYTICAL_SCHEDULE:
            return
            
        prov = ProvenanceRecord(
            source_document=doc_name,
            page_number=raw_tbl.page_number,
            section_title=raw_tbl.section_title or f"Table {t_idx+1}",
            verbatim_source_span=f"Table: {raw_tbl.section_title or f'Data Table {t_idx+1}'} ({len(rows)} rows)",
            source_type="table",
            table_index=t_idx
        )

        # 2. Handle Performance Comparison Table:
        # Rows represent individual distinct performance metrics, columns represent time periods or % change
        if topology == TableTopology.PERFORMANCE_COMPARISON:
            # Identify current period col, baseline period col, and change col
            if not metric_cols:
                return

            period_cols = []
            change_col_idx = None
            for mc in metric_cols:
                m_name = mc["metric_name"].lower()
                c_idx = mc["col_idx"]
                h_name = headers[c_idx].lower() if c_idx < len(headers) else ""
                if "%" in mc["unit"] or "change" in m_name or "%" in m_name or "change" in h_name or "%" in h_name:
                    change_col_idx = c_idx
                else:
                    period_cols.append(c_idx)

            curr_col_idx = period_cols[0] if period_cols else metric_cols[0]["col_idx"]
            base_col_idx = period_cols[1] if len(period_cols) > 1 else None
            if base_col_idx is None and len(metric_cols) > 1 and metric_cols[1]["col_idx"] != change_col_idx:
                base_col_idx = metric_cols[1]["col_idx"]

            for r in rows:
                if not r or not r[0].strip():
                    continue
                row_label = r[0].strip()
                # Skip header repetitions
                if row_label.lower() in ["(in millions)", "in millions", "line item", "metric"]:
                    continue
                    
                metric_name = clean_metric_name(row_label)
                if len(metric_name) < 2:
                    continue
                    
                curr_val, curr_unit, _ = parse_numeric_cell(r[curr_col_idx]) if len(r) > curr_col_idx else (None, "", None)
                base_val, base_unit, _ = parse_numeric_cell(r[base_col_idx]) if base_col_idx and len(r) > base_col_idx else (None, "", None)
                
                pct_val = None
                if change_col_idx and len(r) > change_col_idx:
                    pct_val, _, _ = parse_numeric_cell(r[change_col_idx])
                elif curr_val is not None and base_val is not None and base_val != 0:
                    pct_val = round(((curr_val - base_val) / abs(base_val)) * 100.0, 1)

                unit = curr_unit or base_unit
                if not unit:
                    if "per share" in metric_name.lower() or "earnings per share" in metric_name.lower():
                        unit = "USD / share"
                    elif "%" in metric_name or "rate" in metric_name.lower() or "margin" in metric_name.lower():
                        unit = "%"
                    elif default_unit:
                        unit = default_unit
                    
                fav = "down" if any(neg in metric_name.lower() for neg in ["cost", "expense", "debt", "tax", "attrition"]) else "up"

                if curr_val is not None:
                    delta_abs = round(curr_val - base_val, 2) if base_val is not None else None
                    metrics.append(StandaloneMetric(
                        id=f"tbl_metric_{t_idx}_{len(metrics)+1}",
                        name=metric_name,
                        current_value=curr_val,
                        display_value=f"{curr_val:g} {unit}".strip(),
                        unit=unit,
                        previous_value=base_val,
                        change_abs=delta_abs,
                        change_pct=pct_val,
                        comparison_period="YoY",
                        favorable_direction=fav,
                        provenance=prov
                    ))

                    if base_val is not None:
                        b_label = re.sub(r'_\d+$', '', headers[base_col_idx]).strip() if base_col_idx < len(headers) else "Prior"
                        c_label = re.sub(r'_\d+$', '', headers[curr_col_idx]).strip() if curr_col_idx < len(headers) else "Current"
                        comparisons.append(ComparisonItem(
                            id=f"tbl_comp_{t_idx}_{len(comparisons)+1}",
                            metric_name=metric_name,
                            baseline_label=b_label,
                            baseline_value=base_val,
                            current_label=c_label,
                            current_value=curr_val,
                            unit=unit,
                            delta_abs=delta_abs,
                            delta_pct=pct_val,
                            favorable_direction=fav,
                            provenance=prov
                        ))
            return

        # 3. Handle Categorical Breakdown Table:
        # Rows represent homogeneous entities (segments, departments, zones, courses)
        for m_col in metric_cols:
            c_idx = m_col["col_idx"]
            col_name = m_col["metric_name"]
            unit = m_col["unit"] or default_unit
            
            # Skip duration columns (e.g. Years, Months, Days) from categorical performance series
            if unit in ["Years", "Months", "Days"]:
                continue

            # If col_name contains a date, year, or period, synthesize a meaningful metric from section
            date_match = re.search(r'(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\b20\d\d\b|FY\s*\d\d|Q[1-4])', col_name, re.IGNORECASE)
            metric_display = col_name
            if date_match:
                sec = raw_tbl.section_title or ""
                if "revenue" in sec.lower():
                    metric_display = f"Revenue ({col_name})"
                elif "income" in sec.lower():
                    metric_display = f"Operating Income ({col_name})"
                elif sec and not sec.lower().startswith("table"):
                    metric_display = f"{sec} ({col_name})"
                else:
                    metric_display = f"Performance ({col_name})"
            
            data_points = []
            total_sum = 0.0
            for r in rows:
                if len(r) > c_idx and len(r) > 0:
                    label = r[0].strip()
                    # Filter out total and subtotal rows from categorical series items
                    if re.search(r'^(?:total|subtotal|combined|overall|consolidated(?:\s+total)?)$', label, re.IGNORECASE):
                        continue
                    val, _, _ = parse_numeric_cell(r[c_idx])
                    if val is not None and label:
                        data_points.append(CategoricalDataPoint(label=label, value=val))
                        total_sum += val
                        
            # Accept series with 2 or more categories
            if len(data_points) >= 2:
                is_share = ("share" in metric_display.lower() or "%" in unit) and (90.0 <= total_sum <= 105.0)
                series_list.append(CategoricalSeries(
                    id=f"tbl_{t_idx}_col_{c_idx}",
                    metric_name=metric_display,
                    dimension_name=dim_name,
                    unit=unit,
                    is_part_of_whole=is_share,
                    items=data_points,
                    provenance=prov
                ))

    @classmethod
    def _deduplicate_metrics(cls, metrics: List[StandaloneMetric]) -> List[StandaloneMetric]:
        """Deduplicates metrics that share the same normalized name and similar values."""
        seen: Dict[str, StandaloneMetric] = {}
        for m in metrics:
            key = m.name.lower().strip()
            if key not in seen:
                seen[key] = m
            else:
                # Prefer metric with explicit deltas / change_pct
                existing = seen[key]
                if existing.change_pct is None and m.change_pct is not None:
                    seen[key] = m
        return list(seen.values())

    @classmethod
    def _deduplicate_comparisons(cls, comparisons: List[ComparisonItem]) -> List[ComparisonItem]:
        """Deduplicates comparisons that share the same metric name."""
        seen: Dict[str, ComparisonItem] = {}
        for c in comparisons:
            key = c.metric_name.lower().strip()
            if key not in seen:
                seen[key] = c
            else:
                existing = seen[key]
                if existing.delta_pct is None and c.delta_pct is not None:
                    seen[key] = c
        return list(seen.values())

    @classmethod
    def _generate_summary(
        cls, title: str, domain: str, period: Optional[str],
        metrics: List[StandaloneMetric], series: List[CategoricalSeries]
    ) -> str:
        clean_title = title
        if re.search(r'^(?:tmp[a-z0-9_]+|temp[a-z0-9_]+)$', title, re.IGNORECASE):
            clean_title = f"{domain} Review"

        period_str = f" covering {period}" if period else ""
        sentences = [f"This executive briefing synthesizes key analytical findings from the {clean_title} ({domain} domain{period_str})."]

        if metrics:
            highlighted = []
            for m in metrics[:3]:
                name = clean_metric_name(m.name)
                val_str = f"{m.current_value:g}"
                if m.unit and m.unit not in ["%", "Ratio"]:
                    val_str = f"{val_str} {m.unit}"
                elif m.unit == "%":
                    val_str = f"{val_str}%"
                    
                if m.change_pct is not None:
                    sign = "+" if m.change_pct > 0 else ""
                    comp = f" {m.comparison_period}" if m.comparison_period else ""
                    val_str += f" ({sign}{m.change_pct:g}%{comp})"
                    
                highlighted.append(f"{name} at {val_str}")
                
            if len(highlighted) == 1:
                sentences.append(f"Key performance indicators feature {highlighted[0]}.")
            elif len(highlighted) == 2:
                sentences.append(f"Key performance indicators feature {highlighted[0]} and {highlighted[1]}.")
            else:
                sentences.append(f"Key performance indicators feature {', '.join(highlighted[:-1])}, and {highlighted[-1]}.")

        if series:
            valid_series = [
                s for s in series 
                if not re.search(r'^\(?(?:in\s+)?(?:millions?|billions?|thousands?|crores?|lakhs?|usd|inr|\$)\)?$', s.dimension_name, re.IGNORECASE)
                and not s.dimension_name.lower().startswith("col_")
            ]
            s = valid_series[0] if valid_series else series[0]
            dim = s.dimension_name
            if re.search(r'^\(?(?:in\s+)?(?:millions?|billions?|thousands?|crores?|lakhs?|usd|inr|\$)\)?$', dim, re.IGNORECASE) or dim.lower().startswith("col_") or dim == "Category":
                dim_str = "operational categories"
            else:
                dim_str = f"{dim.lower()} categories"
                
            m_clean = clean_metric_name(s.metric_name)
            sentences.append(f"The report includes structured distribution of {m_clean} across {len(s.items)} {dim_str}.")

        return " ".join(sentences)
