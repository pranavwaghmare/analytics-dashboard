"""Visualization Recommendation Engine.
Scores, filters, and ranks candidate charts based on:
- Analytical relevance & decision-making density
- Strict Quality Gate: candidates scoring below 0.65 are omitted entirely
- Chart-type-specific observation bounds
- Elimination of redundant or uninformative candidates
- Balanced visual representation (comparisons + breakdowns)
"""

from typing import List, Dict, Any
from visualization.taxonomy import VisualizationTaxonomy, ChartCandidate, ChartType
from schema.models import CategoricalSeries, ComparisonItem


class VisualizationRecommender:
    @classmethod
    def recommend_charts(
        cls,
        series_list: List[CategoricalSeries],
        comparisons: List[ComparisonItem],
        max_charts: int = 4
    ) -> List[ChartCandidate]:
        """Generates, scores, filters by quality gate, and ranks candidate charts."""
        candidates: List[ChartCandidate] = []
        
        # 1. Generate candidates from categorical series (distributions, segments)
        for s in series_list:
            if not s.items:
                continue
            cand = VisualizationTaxonomy.classify_series(s)
            if cand is not None:
                cand.score = cls._score_series_candidate(s, cand.chart_type)
                # Tightened Quality Gate: omit candidates scoring below 0.70
                if cand.score >= 0.70:
                    candidates.append(cand)
            
        # 2. Generate candidates from explicit comparisons (YoY / Target vs Actual)
        for c in comparisons:
            cand = VisualizationTaxonomy.classify_comparison(c)
            if cand is not None:
                cand.score = cls._score_comparison_candidate(c)
                # Tightened Quality Gate: omit candidates scoring below 0.70
                if cand.score >= 0.70:
                    candidates.append(cand)

        # 3. Deduplicate Redundant Candidates
        filtered = cls._filter_redundancy(candidates)

        # 4. Sort by score descending and take top N
        sorted_charts = sorted(filtered, key=lambda c: c.score, reverse=True)
        return sorted_charts[:max_charts]

    @classmethod
    def _score_series_candidate(cls, s: CategoricalSeries, chart_type: ChartType) -> float:
        import re
        m_lower = s.metric_name.lower().strip()
        dim_lower = s.dimension_name.lower().strip()
        sec_lower = (s.provenance.section_title or "").lower().strip()

        # Reject generic, uninformative series or dates as metrics
        if m_lower in ["col", "amount", "shares", "total", "thereafter", "other", "value", "measure", "item"]:
            return 0.0
        if m_lower.startswith("col_") or dim_lower.startswith("col_"):
            return 0.0
        if "in millions" in dim_lower or "in billions" in dim_lower or "in thousands" in dim_lower:
            return 0.0
        if any(name in m_lower or name in dim_lower for name in ["satya nadella", "catherine macgregor", "director", "chief executive"]):
            return 0.0
            
        # A calendar date is a temporal dimension, not an analytical metric
        if re.search(r'^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\b20\d\d\b|FY\s*\d\d|Q[1-4])$', m_lower):
            return 0.0

        score = 0.50
        
        # 1. Section Context & Analytical Utility (Weight ~0.35)
        if any(w in sec_lower for w in ["executive", "overview", "highlight", "results", "operating", "performance", "segment", "discussion"]):
            score += 0.25
        elif any(w in sec_lower for w in ["note", "disclosure", "accounting policy", "commitments", "footnote", "statutory", "appendix"]):
            score -= 0.35

        # 2. Metric Type & Semantic Unit (Weight ~0.30)
        # Isolated duration metrics (years, months, days) represent technical disclosure reference data
        if s.unit in ["Years", "Months", "Days", "Hours"] or any(w in m_lower for w in ["life", "term", "tenure", "duration", "age"]):
            score -= 0.30

        # Part of whole composition bonus
        if s.is_part_of_whole:
            score += 0.20
            
        # 3. Observation Count & Dimensionality (Weight ~0.20)
        n = len(s.items)
        if 3 <= n <= 6:
            score += 0.15
        elif n == 2 or (7 <= n <= 8):
            score += 0.05
        elif n > 8:
            score -= 0.20
            
        # Dimensionality prominence
        if any(w in dim_lower for w in ["segment", "department", "zone", "region", "branch", "program", "product", "channel"]):
            score += 0.20
        elif dim_lower in ["category", "item", "class", "asset class", "stock class"]:
            score -= 0.10

        # 4. Variance check
        vals = [it.value for it in s.items]
        if max(vals) == min(vals):
            score -= 0.30

        # Grounding confidence weighting
        score += s.grounding.confidence_score * 0.10
            
        return round(score, 3)

    @classmethod
    def _score_comparison_candidate(cls, c: ComparisonItem) -> float:
        sec_lower = (c.provenance.section_title or "").lower().strip()
        metric_lower = c.metric_name.lower()
        score = 0.65
        
        # 1. Section context
        if any(w in sec_lower for w in ["executive", "overview", "highlight", "results", "operating", "performance", "segment", "discussion"]):
            score += 0.20
        elif any(w in sec_lower for w in ["note", "disclosure", "accounting policy", "commitments", "footnote", "statutory"]):
            score -= 0.25

        # 2. Meaningful delta percentage bonus
        if c.delta_pct is not None:
            score += min(0.20, abs(c.delta_pct) / 50.0)
            
        score += c.grounding.confidence_score * 0.10
        
        # 3. Primary operational indicators
        key_indicators = ["revenue", "profit", "income", "margin", "volume", "deliveries", "headcount", "placement", "ebitda", "sales", "enrollment"]
        if any(k in metric_lower for k in key_indicators):
            score += 0.10
            
        return round(score, 3)

    @classmethod
    def _filter_redundancy(cls, candidates: List[ChartCandidate]) -> List[ChartCandidate]:
        """Filters out near-duplicate candidates (e.g. same dimension and metric values)."""
        seen_keys = set()
        unique_candidates = []
        
        for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
            if isinstance(cand.data_source, CategoricalSeries):
                s = cand.data_source
                labels_sig = "-".join(sorted(it.label.lower() for it in s.items))
                key = f"series_{s.dimension_name.lower()}_{labels_sig}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                unique_candidates.append(cand)
            elif isinstance(cand.data_source, ComparisonItem):
                c = cand.data_source
                key = f"comp_{c.metric_name.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                unique_candidates.append(cand)
            else:
                unique_candidates.append(cand)
                
        return unique_candidates
