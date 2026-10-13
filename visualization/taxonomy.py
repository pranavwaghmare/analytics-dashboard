"""Visualization Taxonomy and Data Shape Classifier.
Maps intermediate analytical structures to appropriate chart candidates:
- Part-of-whole composition (2 <= N <= 6) -> Donut Chart
- Categorical distribution (2 <= N <= 12) -> Horizontal / Vertical Bar Chart
- Explicit comparison pair (N = 2) -> Comparison Bar / Bullet Chart
- Enforces chart-type-specific observation thresholds and variance checks
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from schema.models import CategoricalSeries, ComparisonItem


class ChartType(str, Enum):
    KPI_CARD = "kpi_card"
    DONUT = "donut"
    BAR_HORIZONTAL = "bar_horizontal"
    BAR_VERTICAL = "bar_vertical"
    GROUPED_BAR = "grouped_bar"
    COMPARISON_BAR = "comparison_bar"
    LINE_TREND = "line_trend"


class ChartCandidate:
    def __init__(
        self,
        candidate_id: str,
        chart_type: ChartType,
        title: str,
        data_source: Any,
        score: float = 0.0,
        metadata: Dict[str, Any] = None
    ):
        self.candidate_id = candidate_id
        self.chart_type = chart_type
        self.title = title
        self.data_source = data_source
        self.score = score
        self.metadata = metadata or {}


class VisualizationTaxonomy:
    @classmethod
    def classify_series(cls, series: CategoricalSeries) -> Optional[ChartCandidate]:
        """
        Determines the best chart candidate for a categorical series.
        Applies chart-type-specific observation bounds:
        - Distributions require 2 <= N <= 12
        - Rejects zero-variance distributions
        """
        if not series.items:
            return None
            
        n_items = len(series.items)
        # Distribution observation threshold: 2 to 12 items
        if n_items < 2 or n_items > 12:
            return None
            
        # Variance check: reject series where all values are zero or identical
        vals = [it.value for it in series.items]
        if all(v == 0.0 for v in vals):
            return None
        if max(vals) == min(vals) and n_items > 3:
            return None

        title = f"{series.metric_name} by {series.dimension_name}"
        
        # Rule 1: Part of whole (percentages or proportions summing near 100%) and 2-6 items -> Donut
        if series.is_part_of_whole and 2 <= n_items <= 6:
            return ChartCandidate(
                candidate_id=f"chart_{series.id}",
                chart_type=ChartType.DONUT,
                title=title,
                data_source=series,
                metadata={"dimension": series.dimension_name, "metric": series.metric_name, "unit": series.unit}
            )

        # Rule 1.5: Temporal sequence -> Line Trend Chart
        import re
        dim_clean = series.dimension_name.lower().strip()
        is_temporal_dim = bool(re.search(r'\b(year|quarter|month|fiscal|fy|period|trend)\b', dim_clean))
        all_temporal_labels = all(bool(re.search(r'^(?:20\d\d|19\d\d|fy\s*\d\d|q[1-4]|h[1-2])\b', it.label.lower().strip())) for it in series.items)
        if (is_temporal_dim or all_temporal_labels) and n_items >= 2:
            return ChartCandidate(
                candidate_id=f"chart_{series.id}",
                chart_type=ChartType.LINE_TREND,
                title=f"{series.metric_name} Trend over {series.dimension_name}",
                data_source=series,
                metadata={"dimension": series.dimension_name, "metric": series.metric_name, "unit": series.unit}
            )
            
        # Rule 2: If items have long labels or > 4 items -> Horizontal Bar
        avg_label_len = sum(len(it.label) for it in series.items) / max(1, n_items)
        if avg_label_len > 12 or n_items > 4:
            return ChartCandidate(
                candidate_id=f"chart_{series.id}",
                chart_type=ChartType.BAR_HORIZONTAL,
                title=title,
                data_source=series,
                metadata={"dimension": series.dimension_name, "metric": series.metric_name, "unit": series.unit}
            )
            
        # Rule 3: Vertical Bar for compact categories (e.g. 2-4 items with short labels)
        return ChartCandidate(
            candidate_id=f"chart_{series.id}",
            chart_type=ChartType.BAR_VERTICAL,
            title=title,
            data_source=series,
            metadata={"dimension": series.dimension_name, "metric": series.metric_name, "unit": series.unit}
        )

    @classmethod
    def classify_comparison(cls, comp: ComparisonItem) -> Optional[ChartCandidate]:
        """
        Creates a side-by-side comparison bar chart candidate.
        A 2-category comparison (e.g. Actual vs Target, Current vs Previous Year) is explicitly valid (N = 2).
        """
        if comp.baseline_value == 0.0 and comp.current_value == 0.0:
            return None
            
        title = f"{comp.metric_name}: {comp.baseline_label} vs {comp.current_label}"
        return ChartCandidate(
            candidate_id=f"chart_comp_{comp.id}",
            chart_type=ChartType.COMPARISON_BAR,
            title=title,
            data_source=comp,
            metadata={"baseline": comp.baseline_value, "current": comp.current_value, "unit": comp.unit}
        )
