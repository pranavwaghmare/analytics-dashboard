"""Canonical Intermediate Analytical Representation (IR) Models.
This is the central contract decoupling document extraction from analytics & visualization.
Explicitly represents:
- Standalone metrics (with current/previous/delta)
- Explicit pair comparisons
- Categorical series (breakdowns, distributions)
- Time series (ordered temporal progressions)
- Semantic relationships & drivers
- Analytical insights
- Provenance & Grounding status
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ProvenanceRecord(BaseModel):
    """Tracks exact provenance to the source document."""
    source_document: str = Field(description="Name or path of the source document")
    page_number: int = Field(default=1, description="1-indexed page number where the fact was found")
    section_title: Optional[str] = Field(default=None, description="Enclosing heading or section title")
    verbatim_source_span: str = Field(description="Exact sentence or table row/cell from the document")
    source_type: str = Field(default="prose", description="'prose' or 'table'")
    table_index: Optional[int] = Field(default=None, description="Index of table if source_type == 'table'")


class GroundingStatus(BaseModel):
    """Grounding verification details ensuring value + metric + unit co-occur in the source span."""
    is_grounded: bool = Field(default=True, description="True if verified against source span")
    value_matched: bool = Field(default=True, description="Numeric value verified in source span")
    metric_context_matched: bool = Field(default=True, description="Metric name tokens found in source span")
    unit_matched: bool = Field(default=True, description="Unit found in or inferred from source span")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall confidence [0.0 - 1.0]")
    grounding_notes: str = Field(default="Verified directly against document span.")


class StandaloneMetric(BaseModel):
    """Individual high-level quantitative indicator."""
    id: str
    name: str
    current_value: float
    display_value: str = ""
    unit: str = ""
    canonical_value: Optional[float] = None
    previous_value: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    comparison_period: Optional[str] = None  # e.g., "YoY", "QoQ", "vs Last Year"
    favorable_direction: str = Field(default="neutral", description="'up', 'down', or 'neutral'")
    period: Optional[str] = None
    provenance: ProvenanceRecord
    grounding: GroundingStatus = Field(default_factory=GroundingStatus)


class ComparisonItem(BaseModel):
    """Explicit 2-period or target vs actual comparison (e.g. EBITDA margin 18.2% -> 20.1%)."""
    id: str
    metric_name: str
    baseline_label: str = Field(default="Previous")
    baseline_value: float
    current_label: str = Field(default="Current")
    current_value: float
    unit: str = ""
    delta_abs: Optional[float] = None
    delta_pct: Optional[float] = None
    favorable_direction: str = Field(default="neutral", description="'up', 'down', or 'neutral'")
    provenance: ProvenanceRecord
    grounding: GroundingStatus = Field(default_factory=GroundingStatus)


class CategoricalDataPoint(BaseModel):
    """Single item in a categorical series."""
    label: str
    value: float
    secondary_value: Optional[float] = None  # e.g., for multi-metric tables (SLA and Return Rate)
    share_pct: Optional[float] = None


class CategoricalSeries(BaseModel):
    """Series representing distributions, departmental splits, or regional breakdowns."""
    id: str
    metric_name: str
    dimension_name: str  # e.g., "Department", "Business Segment", "Zone"
    unit: str = ""
    secondary_metric_name: Optional[str] = None
    secondary_unit: Optional[str] = None
    is_part_of_whole: bool = Field(default=False, description="True if items represent composition summing near 100%")
    items: List[CategoricalDataPoint] = Field(default_factory=list)
    provenance: ProvenanceRecord
    grounding: GroundingStatus = Field(default_factory=GroundingStatus)


class TimeDataPoint(BaseModel):
    """Single point in a time series."""
    period_label: str  # e.g. "Q1 FY23", "2021", "Month 1"
    sequence_index: int = 0
    value: float


class TimeSeries(BaseModel):
    """Multi-period ordered chronological data."""
    id: str
    metric_name: str
    time_dimension: str = "period"  # "quarter", "year", "month"
    unit: str = ""
    points: List[TimeDataPoint] = Field(default_factory=list)
    provenance: ProvenanceRecord
    grounding: GroundingStatus = Field(default_factory=GroundingStatus)


class Relationship(BaseModel):
    """Explicit semantic driver, correlation, or dependency between metrics."""
    id: str
    subject_metric: str
    driver_metric: str
    relationship_type: str = Field(default="driven_by", description="'driven_by', 'correlated_with', 'inverse_to'")
    description: str
    provenance: ProvenanceRecord


class AnalyticalInsight(BaseModel):
    """Synthesized takeaway or notable pattern."""
    id: str
    headline: str
    detail: str
    sentiment: str = Field(default="neutral", description="'positive', 'negative', 'neutral'")
    related_metric_ids: List[str] = Field(default_factory=list)
    provenance: ProvenanceRecord


class DocumentAnalyticsModel(BaseModel):
    """The central Intermediate Representation (IR) of the entire document."""
    document_title: str
    inferred_domain: str = Field(default="General", description="e.g. Finance, HR, Operations, Academic")
    reporting_period: Optional[str] = None
    executive_summary: str = ""
    standalone_metrics: List[StandaloneMetric] = Field(default_factory=list)
    comparisons: List[ComparisonItem] = Field(default_factory=list)
    categorical_series: List[CategoricalSeries] = Field(default_factory=list)
    time_series: List[TimeSeries] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    insights: List[AnalyticalInsight] = Field(default_factory=list)
    extraction_metadata: Dict[str, Any] = Field(default_factory=dict)
