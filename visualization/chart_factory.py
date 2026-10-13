"""Deterministic Plotly Chart Factory.
Generates polished, interactive Plotly visualizations without fragile code generation.
Applies clean typography, consistent color palettes, rounded bar geometries,
center donut metrics, and informative hover templates.
"""

import plotly.graph_objects as go
from typing import Dict, Any, Optional, List
from visualization.taxonomy import ChartCandidate, ChartType
from schema.models import CategoricalSeries, ComparisonItem

# Curated harmonious color palette (modern SaaS / FinTech aesthetic)
PALETTE = ["#0284C7", "#0F766E", "#6366F1", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981"]


def format_val(val: float, unit: str = "") -> str:
    """Formats numeric values with clean abbreviations, thousand separators, and units."""
    if val is None:
        return ""
    try:
        fval = float(val)
    except (ValueError, TypeError):
        return str(val)

    if abs(fval) >= 1_000_000:
        val_str = f"{fval/1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    elif abs(fval) >= 10_000:
        val_str = f"{fval:,.0f}"
    elif fval.is_integer():
        val_str = f"{int(fval):,}"
    else:
        val_str = f"{fval:.1f}"

    clean_unit = str(unit or "").strip()
    if clean_unit and clean_unit != "%":
        return f"{val_str} {clean_unit}".strip()
    elif clean_unit == "%":
        return f"{val_str}%"
    return val_str


class ChartFactory:
    @classmethod
    def render_chart(cls, candidate: ChartCandidate) -> go.Figure:
        """Entry point that renders a Plotly Figure from a ChartCandidate."""
        if candidate.chart_type == ChartType.DONUT:
            return cls.render_donut(candidate.data_source, candidate.title)
        elif candidate.chart_type == ChartType.BAR_HORIZONTAL:
            return cls.render_horizontal_bar(candidate.data_source, candidate.title)
        elif candidate.chart_type == ChartType.BAR_VERTICAL:
            return cls.render_vertical_bar(candidate.data_source, candidate.title)
        elif candidate.chart_type == ChartType.COMPARISON_BAR:
            return cls.render_comparison_bar(candidate.data_source, candidate.title)
        elif candidate.chart_type == ChartType.LINE_TREND:
            return cls.render_line_trend(candidate.data_source, candidate.title)
        else:
            return cls.render_vertical_bar(candidate.data_source, candidate.title)

    @classmethod
    def _apply_base_layout(cls, fig: go.Figure, title: str, height: int = 350) -> go.Figure:
        """Applies consistent executive typography, clean spacing, and transparent backgrounds."""
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=14, color="#0F172A", family="Inter, -apple-system, sans-serif"),
                x=0.01,
                y=0.96
            ),
            font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12, color="#334155"),
            margin=dict(l=24, r=32, t=52, b=32),
            height=height,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(
                bgcolor="#0F172A",
                bordercolor="#1E293B",
                font=dict(family="Inter, sans-serif", size=12, color="#FFFFFF")
            )
        )
        return fig

    @classmethod
    def render_donut(cls, series: CategoricalSeries, title: str) -> go.Figure:
        labels = [it.label for it in series.items]
        values = [it.value for it in series.items]
        unit = series.unit or "%"

        colors = PALETTE[:len(labels)]
        if len(labels) > len(PALETTE):
            colors = PALETTE * ((len(labels) // len(PALETTE)) + 1)

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2.5)),
            textinfo="percent",
            textposition="inside",
            insidetextorientation="horizontal",
            hovertemplate=f"<b>%{{label}}</b><br>Value: %{{value}} {unit}<br>Share: %{{percent}}<extra></extra>"
        )])

        # Center KPI Total callout
        total_val = sum(values) if values else 0
        if total_val > 0:
            center_label = "TOTAL" if unit != "%" else "TOTAL SHARE"
            center_val_str = format_val(total_val, unit if unit != "%" else "")
            fig.add_annotation(
                text=f"<b>{center_val_str}</b><br><span style='font-size:10px;color:#64748B;font-weight:600;letter-spacing:0.5px;'>{center_label}</span>",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=15, color="#0F172A", family="Inter, sans-serif"),
                align="center"
            )

        cls._apply_base_layout(fig, title, height=350)
        fig.update_layout(
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.22,
                xanchor="center",
                x=0.5,
                font=dict(size=11, color="#475569")
            )
        )
        return fig

    @classmethod
    def render_horizontal_bar(cls, series: CategoricalSeries, title: str) -> go.Figure:
        # Sort descending by value so highest value is displayed on top
        sorted_items = sorted(series.items, key=lambda x: x.value, reverse=True)
        labels = [it.label for it in sorted_items]
        values = [it.value for it in sorted_items]
        unit = series.unit or ""

        colors = PALETTE[:len(labels)]
        if len(labels) > len(PALETTE):
            colors = PALETTE * ((len(labels) // len(PALETTE)) + 1)

        fig = go.Figure(data=[go.Bar(
            y=labels,
            x=values,
            orientation="h",
            marker=dict(
                color=colors,
                cornerradius=6,
                line=dict(color="rgba(255,255,255,0.7)", width=1.5)
            ),
            text=[format_val(v, unit) for v in values],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=11, color="#334155", family="Inter, sans-serif"),
            hovertemplate=f"<b>%{{y}}</b><br>{series.metric_name}: %{{x}} {unit}<extra></extra>"
        )])

        cls._apply_base_layout(fig, title, height=350)
        fig.update_layout(
            margin=dict(l=24, r=50, t=52, b=32),
            xaxis=dict(
                title=dict(text=f"{series.metric_name} ({unit})" if unit else series.metric_name, font=dict(size=11, color="#64748B")),
                gridcolor="rgba(148, 163, 184, 0.18)",
                gridwidth=1,
                showgrid=True,
                zeroline=False
            ),
            yaxis=dict(
                autorange="reversed",
                showgrid=False,
                tickfont=dict(size=11, color="#334155")
            )
        )
        return fig

    @classmethod
    def render_vertical_bar(cls, series: CategoricalSeries, title: str) -> go.Figure:
        labels = [it.label for it in series.items]
        values = [it.value for it in series.items]
        unit = series.unit or ""

        colors = PALETTE[:len(labels)]
        if len(labels) > len(PALETTE):
            colors = PALETTE * ((len(labels) // len(PALETTE)) + 1)

        fig = go.Figure(data=[go.Bar(
            x=labels,
            y=values,
            marker=dict(
                color=colors,
                cornerradius=6,
                line=dict(color="rgba(255,255,255,0.7)", width=1.5)
            ),
            text=[format_val(v, unit) for v in values],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=11, color="#334155", family="Inter, sans-serif"),
            hovertemplate=f"<b>%{{x}}</b><br>{series.metric_name}: %{{y}} {unit}<extra></extra>"
        )])

        cls._apply_base_layout(fig, title, height=350)
        fig.update_layout(
            bargap=0.35,
            yaxis=dict(
                title=dict(text=f"{series.metric_name} ({unit})" if unit else series.metric_name, font=dict(size=11, color="#64748B")),
                gridcolor="rgba(148, 163, 184, 0.18)",
                gridwidth=1,
                showgrid=True,
                zeroline=False
            ),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=11, color="#334155")
            )
        )
        return fig

    @classmethod
    def render_comparison_bar(cls, comp: ComparisonItem, title: str) -> go.Figure:
        categories = [comp.baseline_label, comp.current_label]
        values = [comp.baseline_value, comp.current_value]
        is_favorable = (comp.delta_abs or 0) >= 0
        current_bar_color = "#10B981" if is_favorable else "#EF4444"
        bar_colors = ["#94A3B8", current_bar_color]
        unit = comp.unit or ""

        fig = go.Figure(data=[go.Bar(
            x=categories,
            y=values,
            marker=dict(
                color=bar_colors,
                cornerradius=6,
                line=dict(color="rgba(255,255,255,0.7)", width=1.5)
            ),
            text=[format_val(v, unit) for v in values],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=11, color="#334155", family="Inter, sans-serif"),
            hovertemplate=f"<b>%{{x}}</b><br>Value: %{{y}} {unit}<extra></extra>"
        )])

        cls._apply_base_layout(fig, title, height=350)

        # Delta badge annotation in top-right corner
        delta_str = ""
        if comp.delta_pct is not None:
            arrow = "▲" if comp.delta_pct >= 0 else "▼"
            delta_str = f"{arrow} {comp.delta_pct:+g}%"
        elif comp.delta_abs is not None:
            arrow = "▲" if comp.delta_abs >= 0 else "▼"
            delta_str = f"{arrow} {comp.delta_abs:+g} {unit}".strip()

        if delta_str:
            badge_color = "#10B981" if is_favorable else "#EF4444"
            bg_color = "rgba(16, 185, 129, 0.14)" if is_favorable else "rgba(239, 68, 68, 0.14)"
            fig.add_annotation(
                text=f"<span style='color:{badge_color}; background:{bg_color}; padding:4px 10px; border-radius:12px; font-weight:700; font-size:11px;'>{delta_str}</span>",
                xref="paper", yref="paper",
                x=0.98, y=1.08,
                showarrow=False,
                align="right"
            )

        fig.update_layout(
            bargap=0.45,
            yaxis=dict(
                title=dict(text=f"{comp.metric_name} ({unit})" if unit else comp.metric_name, font=dict(size=11, color="#64748B")),
                gridcolor="rgba(148, 163, 184, 0.18)",
                gridwidth=1,
                showgrid=True,
                zeroline=False
            ),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=12, color="#334155", family="Inter, sans-serif")
            )
        )
        return fig

    @classmethod
    def render_line_trend(cls, series: CategoricalSeries, title: str) -> go.Figure:
        labels = [it.label for it in series.items]
        values = [it.value for it in series.items]
        unit = series.unit or ""

        fig = go.Figure(data=[go.Scatter(
            x=labels,
            y=values,
            mode="lines+markers+text",
            line=dict(shape="spline", width=3, color="#0284C7"),
            fill="tozeroy",
            fillcolor="rgba(2, 132, 199, 0.10)",
            marker=dict(size=8, color="#0284C7", line=dict(color="#FFFFFF", width=2)),
            text=[format_val(v, unit) for v in values],
            textposition="top center",
            cliponaxis=False,
            textfont=dict(size=11, color="#334155", family="Inter, sans-serif"),
            hovertemplate=f"<b>%{{x}}</b><br>{series.metric_name}: %{{y}} {unit}<extra></extra>"
        )])

        cls._apply_base_layout(fig, title, height=350)
        fig.update_layout(
            yaxis=dict(
                title=dict(text=f"{series.metric_name} ({unit})" if unit else series.metric_name, font=dict(size=11, color="#64748B")),
                gridcolor="rgba(148, 163, 184, 0.18)",
                gridwidth=1,
                showgrid=True,
                zeroline=False
            ),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=11, color="#334155")
            )
        )
        return fig
