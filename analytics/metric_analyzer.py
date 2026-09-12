import re
from typing import List, Dict, Any, Optional
from extraction.heuristic_extractor import clean_metric_name
from schema.models import (
    DocumentAnalyticsModel,
    StandaloneMetric,
    ComparisonItem,
    CategoricalSeries,
    AnalyticalInsight,
    ProvenanceRecord
)


class MetricAnalyzer:
    @classmethod
    def analyze(cls, model: DocumentAnalyticsModel) -> Dict[str, Any]:
        """
        Analyzes the validated document model:
        1. Ranks standalone metrics for the KPI ribbon using semantic signals (section importance, aggregate scope, deltas)
        2. Cleans metric and dimension names, removing generic placeholders
        3. Identifies key comparison pairs
        4. Synthesizes high-level analytical takeaways
        """
        # Clean and sanitize metric names and dimensions
        for m in model.standalone_metrics:
            m.name = clean_metric_name(m.name)

        for c in model.comparisons:
            c.metric_name = clean_metric_name(c.metric_name)

        for s in model.categorical_series:
            s.metric_name = clean_metric_name(s.metric_name)
            if re.search(r'^\(?(?:in\s+)?(?:millions?|billions?|thousands?|crores?|lakhs?|usd|inr|\$)\)?$', s.dimension_name, re.IGNORECASE) or s.dimension_name.lower().startswith("col_"):
                sec = s.provenance.section_title or ""
                if "segment" in sec.lower():
                    s.dimension_name = "Segment"
                elif "department" in sec.lower() or "workforce" in sec.lower():
                    s.dimension_name = "Department"
                elif "region" in sec.lower() or "zone" in sec.lower():
                    s.dimension_name = "Region"
                else:
                    s.dimension_name = "Category"

        # 1. Rank metrics for KPI Ribbon using multi-factor semantic prioritization
        ranked_metrics = cls._rank_kpi_metrics(model.standalone_metrics)
        
        # 2. Key comparisons
        ranked_comparisons = sorted(
            model.comparisons,
            key=lambda c: abs(c.delta_pct or 0.0) if c.delta_pct is not None else abs(c.delta_abs or 0.0),
            reverse=True
        )
        
        # 3. Filter and rank categorical series
        # Prioritize series with clean item counts (2 to 8 items) and part-of-whole composition
        ranked_series = sorted(
            model.categorical_series,
            key=lambda s: (1.2 if s.is_part_of_whole else 1.0) * (1.1 if 2 <= len(s.items) <= 6 else 0.7),
            reverse=True
        )

        # 4. Generate synthesized insights if none present
        auto_insights = list(model.insights)
        if not auto_insights:
            auto_insights = cls._generate_automated_insights(model)

        return {
            "title": model.document_title,
            "domain": model.inferred_domain,
            "period": model.reporting_period,
            "summary": model.executive_summary,
            "hero_kpis": ranked_metrics[:4],
            "all_metrics": ranked_metrics,
            "comparisons": ranked_comparisons,
            "series": ranked_series,
            "relationships": model.relationships,
            "insights": auto_insights
        }

    @classmethod
    def _rank_kpi_metrics(cls, metrics: List[StandaloneMetric]) -> List[StandaloneMetric]:
        """
        Scores and sorts metrics using semantic signals:
        - Section Semantic Importance: Strong weight to Executive Summary, Overview, Results, MD&A
        - Grammatical Role & Discourse Prominence: Main clause subjects, summary sentences
        - Aggregate vs Component Scope: Aggregate organizational measures vs narrow component details
        - Explicit Comparisons & Deltas: YoY/QoQ percentage changes
        - Grounding Confidence & Supporting Signals
        - Domain vocabulary is strictly a weak supplementary tie-breaker
        """
        def score_metric(m: StandaloneMetric) -> float:
            score = 0.30
            name_lower = m.name.lower()
            sec_title = (m.provenance.section_title or "").lower()

            # 1. Section Semantic Importance (Weight ~0.35)
            high_importance_sections = [
                "executive summary", "executive overview", "overview", "highlights",
                "key findings", "results of operations", "operating results", "results",
                "management discussion", "financial highlights", "performance summary",
                "business overview", "summary of operations"
            ]
            moderate_importance_sections = [
                "segment results", "operations", "departmental review", "review",
                "performance", "discussion"
            ]
            footnote_sections = [
                "notes to consolidated", "accounting policies", "commitments and contingencies",
                "income taxes", "leases", "pension", "footnote", "subsequent events"
            ]

            if any(sec in sec_title for sec in high_importance_sections):
                score += 0.35
            elif any(sec in sec_title for sec in moderate_importance_sections):
                score += 0.15
            elif any(sec in sec_title for sec in footnote_sections):
                score -= 0.15

            # 2. Aggregate-vs-Component Scope (Weight ~0.20)
            aggregate_terms = [
                "total", "overall", "net", "operating", "consolidated", "full-year",
                "annual", "comprehensive", "core", "gross", "diluted", "revenue"
            ]
            component_terms = [
                "allowance", "accrued", "deferred", "amortization", "withholding",
                "severance", "unvested", "fair value", "foreign exchange", "par value",
                "restructuring", "impairment"
            ]

            if any(agg in name_lower for agg in aggregate_terms):
                score += 0.20
            elif any(comp in name_lower for comp in component_terms):
                score -= 0.15

            # 3. Explicit Comparisons & Deltas (Weight ~0.15)
            if m.change_pct is not None:
                score += 0.10
            if m.previous_value is not None:
                score += 0.05

            # 4. Grammatical Role & Source Prominence (Weight ~0.10)
            if m.provenance.source_type == "prose":
                score += 0.10

            # 5. Document Position Supporting Signal (Weight ~0.05)
            if m.provenance.page_number <= 3:
                score += 0.05

            # 6. Confidence & Supplementary Domain Tie-Breaker (Weight ~0.05)
            score += m.grounding.confidence_score * 0.03
            key_names = ["revenue", "headcount", "enrollment", "volume", "ebitda", "profit", "placement", "attrition", "sla"]
            if any(k in name_lower for k in key_names):
                score += 0.02

            return score

        return sorted(metrics, key=score_metric, reverse=True)

    @classmethod
    def _generate_automated_insights(cls, model: DocumentAnalyticsModel) -> List[AnalyticalInsight]:
        """Synthesizes high-level analytical takeaways from metrics, deltas, and series."""
        insights: List[AnalyticalInsight] = []
        
        # Insights from standalone metrics
        for m in model.standalone_metrics[:3]:
            if m.change_pct is not None and m.previous_value is not None:
                direction = "increased" if m.change_pct > 0 else "decreased"
                sentiment = "positive" if (m.change_pct > 0 and m.favorable_direction == "up") or (m.change_pct < 0 and m.favorable_direction == "down") else "negative"
                insights.append(AnalyticalInsight(
                    id=f"auto_ins_{len(insights)+1}",
                    headline=f"{m.name} {direction.capitalize()} by {abs(m.change_pct)}%",
                    detail=f"{m.name} moved from {m.previous_value:g} {m.unit} to {m.current_value:g} {m.unit} ({m.comparison_period or 'period'}).".strip(),
                    sentiment=sentiment,
                    related_metric_ids=[m.id],
                    provenance=m.provenance
                ))

        # Insights from categorical series (Top segment)
        for s in model.categorical_series[:2]:
            if s.items:
                sorted_items = sorted(s.items, key=lambda x: x.value, reverse=True)
                top = sorted_items[0]
                insights.append(AnalyticalInsight(
                    id=f"auto_ins_{len(insights)+1}",
                    headline=f"{top.label} Leads {s.metric_name}",
                    detail=f"Leading contribution in {s.metric_name} is {top.label} at {top.value:g} {s.unit}.".strip(),
                    sentiment="neutral",
                    related_metric_ids=[s.id],
                    provenance=s.provenance
                ))
                
        return insights
