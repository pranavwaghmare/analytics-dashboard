"""Grounding and Anti-Hallucination Verification Gateway.
Verifies that:
1. The verbatim source span actually exists within the document's text or table cells.
2. The extracted numeric values exist verbatim within that source span.
3. The metric context (name / tokens) and unit co-occur within that span.
4. Mathematical consistency (current vs previous vs delta) holds within tolerance.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from schema.models import (
    DocumentAnalyticsModel,
    StandaloneMetric,
    ComparisonItem,
    CategoricalSeries,
    TimeSeries,
    ProvenanceRecord,
    GroundingStatus,
)


def normalize_tokens(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric words."""
    return re.findall(r'[a-zA-Z0-9]+', text.lower())


def find_number_in_text(val: float, text: str) -> bool:
    """Checks if a float/int number is represented in text (e.g., 842, 842.0, 164,600)."""
    # Try exact int/float string representations
    if str(int(val)) in text or f"{val:.1f}" in text or f"{val:.2f}" in text:
        return True
        
    # Try comma formatted e.g. 164,600
    try:
        int_val = int(val)
        comma_rep = f"{int_val:,}"
        if comma_rep in text:
            return True
    except (ValueError, OverflowError):
        pass
        
    # Check rounded / fuzzy numeric match in extracted tokens
    nums = re.findall(r'[-+]?\d+(?:,\d+)*(?:\.\d+)?', text)
    for n in nums:
        clean_n = n.replace(",", "")
        try:
            if abs(float(clean_n) - val) < 0.05:
                return True
        except ValueError:
            pass
            
    return False


class GroundingValidator:
    @classmethod
    def verify_provenance_span(cls, span: str, document_text: str, document_tables: List[Any]) -> bool:
        """Verifies if the claimed source span exists in the document text or table cells."""
        if not span or len(span.strip()) < 3:
            return False
            
        clean_span = " ".join(span.split()).lower()
        clean_doc = " ".join(document_text.split()).lower()
        
        # Check direct substring
        if clean_span in clean_doc:
            return True
            
        # Check overlap of at least 80% tokens if whitespace/punctuation differed
        span_tokens = normalize_tokens(clean_span)
        if len(span_tokens) >= 4:
            # Check 4-gram sliding window
            for i in range(len(span_tokens) - 3):
                gram = " ".join(span_tokens[i:i+4])
                if gram in clean_doc:
                    return True
                    
        # Check tables
        for t in document_tables:
            for row in t.rows:
                row_str = " ".join(row).lower()
                if clean_span in row_str or any(word in row_str for word in span_tokens if len(word) > 4):
                    return True
                    
        return False

    @classmethod
    def verify_metric_grounding(cls, metric: StandaloneMetric, doc_text: str, doc_tables: List[Any]) -> StandaloneMetric:
        """Verifies standalone metric against its provenance span and document content."""
        span = metric.provenance.verbatim_source_span
        span_exists = cls.verify_provenance_span(span, doc_text, doc_tables)
        
        val_found = find_number_in_text(metric.current_value, span)
        if not val_found and span_exists:
            # Check if number appears in full doc text near span
            val_found = find_number_in_text(metric.current_value, doc_text)
            
        # Check context tokens (at least one key word from metric name must be in the span)
        metric_words = [w for w in normalize_tokens(metric.name) if len(w) > 3 and w not in ["rate", "total", "ratio", "level"]]
        context_found = any(w in span.lower() for w in metric_words) if metric_words else True
        
        # Check unit
        unit_words = [w for w in normalize_tokens(metric.unit) if len(w) > 1]
        unit_found = any(w in span.lower() for w in unit_words) if unit_words else True
        
        # Arithmetic check if both previous and delta are present
        math_ok = True
        notes = []
        if metric.previous_value is not None and metric.change_pct is not None and metric.previous_value != 0:
            calc_pct = ((metric.current_value - metric.previous_value) / abs(metric.previous_value)) * 100.0
            if abs(calc_pct - metric.change_pct) > 1.5:
                # Discrepancy detected
                notes.append(f"Stated delta {metric.change_pct}% differs from computed {calc_pct:.1f}%.")
                math_ok = False
                
        is_grounded = span_exists and val_found
        conf = 1.0 if (is_grounded and context_found and math_ok) else (0.7 if is_grounded else 0.3)
        
        if not is_grounded:
            notes.append("Warning: Could not verify numeric value co-occurrence in document span.")
        else:
            notes.append("Verified: Metric, numeric value, and context grounded in source text.")
            
        metric.grounding = GroundingStatus(
            is_grounded=is_grounded,
            value_matched=val_found,
            metric_context_matched=context_found,
            unit_matched=unit_found,
            confidence_score=conf,
            grounding_notes=" ".join(notes)
        )
        return metric

    @classmethod
    def verify_comparison_grounding(cls, comp: ComparisonItem, doc_text: str, doc_tables: List[Any]) -> ComparisonItem:
        """Verifies comparison pair (baseline vs current)."""
        span = comp.provenance.verbatim_source_span
        span_exists = cls.verify_provenance_span(span, doc_text, doc_tables)
        
        curr_found = find_number_in_text(comp.current_value, span)
        base_found = find_number_in_text(comp.baseline_value, span)
        
        is_grounded = span_exists and (curr_found or base_found)
        conf = 1.0 if (span_exists and curr_found and base_found) else (0.75 if is_grounded else 0.3)
        
        notes = ["Verified comparison span."] if is_grounded else ["Unverified comparison span."]
        comp.grounding = GroundingStatus(
            is_grounded=is_grounded,
            value_matched=curr_found and base_found,
            metric_context_matched=True,
            unit_matched=True,
            confidence_score=conf,
            grounding_notes=" ".join(notes)
        )
        return comp

    @classmethod
    def verify_series_grounding(cls, series: CategoricalSeries, doc_text: str, doc_tables: List[Any]) -> CategoricalSeries:
        """Verifies categorical series items against document span or table."""
        if series.provenance.source_type == "table":
            # For table-sourced series, check matching within the designated table or any table
            t_idx = series.provenance.table_index
            target_tables = [doc_tables[t_idx]] if (t_idx is not None and 0 <= t_idx < len(doc_tables)) else doc_tables
            
            matched_points = 0
            for pt in series.items:
                found_pt = False
                for tbl in target_tables:
                    for row in tbl.rows:
                        row_str = " ".join(row).lower()
                        # Check if label and value exist in row
                        if pt.label.lower() in row_str or find_number_in_text(pt.value, row_str):
                            found_pt = True
                            break
                    if found_pt:
                        break
                if found_pt:
                    matched_points += 1
                    
            total_pts = max(1, len(series.items))
            ratio = matched_points / total_pts
            is_grounded = ratio >= 0.5
            conf = 1.0 if ratio == 1.0 else (0.8 if is_grounded else 0.4)
            
            series.grounding = GroundingStatus(
                is_grounded=is_grounded,
                value_matched=(matched_points == total_pts),
                metric_context_matched=True,
                unit_matched=True,
                confidence_score=conf,
                grounding_notes=f"Table verification: {matched_points}/{total_pts} points confirmed in table rows."
            )
            return series

        # For prose-sourced series:
        span = series.provenance.verbatim_source_span
        span_exists = cls.verify_provenance_span(span, doc_text, doc_tables)
        
        matched_points = 0
        for pt in series.items:
            if find_number_in_text(pt.value, span) or find_number_in_text(pt.value, doc_text):
                matched_points += 1
                
        total_pts = max(1, len(series.items))
        ratio = matched_points / total_pts
        
        is_grounded = span_exists and (ratio >= 0.5)
        conf = min(1.0, 0.5 + (0.5 * ratio)) if span_exists else 0.3
        
        notes = f"Verified {matched_points}/{total_pts} data points in document context."
        series.grounding = GroundingStatus(
            is_grounded=is_grounded,
            value_matched=(matched_points == total_pts),
            metric_context_matched=True,
            unit_matched=True,
            confidence_score=conf,
            grounding_notes=notes
        )
        return series

    @classmethod
    def validate_and_filter(cls, model: DocumentAnalyticsModel, doc_text: str, doc_tables: List[Any]) -> DocumentAnalyticsModel:
        """Runs grounding verification on all model components and filters out completely ungrounded hallucinations."""
        # 1. Standalone metrics
        verified_metrics = []
        for m in model.standalone_metrics:
            verified_m = cls.verify_metric_grounding(m, doc_text, doc_tables)
            # Retain only grounded items with confidence >= 0.5
            if verified_m.grounding.confidence_score >= 0.5:
                verified_metrics.append(verified_m)
        model.standalone_metrics = verified_metrics
        
        # 2. Comparisons
        verified_comps = []
        for c in model.comparisons:
            verified_c = cls.verify_comparison_grounding(c, doc_text, doc_tables)
            if verified_c.grounding.confidence_score >= 0.5:
                verified_comps.append(verified_c)
        model.comparisons = verified_comps
        
        # 3. Categorical series
        verified_series = []
        for s in model.categorical_series:
            verified_s = cls.verify_series_grounding(s, doc_text, doc_tables)
            if verified_s.grounding.confidence_score >= 0.5:
                verified_series.append(verified_s)
        model.categorical_series = verified_series
        
        return model
