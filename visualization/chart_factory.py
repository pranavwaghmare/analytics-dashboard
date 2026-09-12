"""Deterministic Plotly Chart Factory.
Generates polished, interactive Plotly visualizations without fragile code generation.
Applies clean typography, consistent color palettes, and informative hover templates.
"""

import plotly.graph_objects as go
from typing import Dict, Any, Optional
from visualization.taxonomy import ChartCandidate, ChartType
from schema.models import CategoricalSeries, ComparisonItem

# Curated harmonious color palette
PALETTE = ["#0F766E", "#0284C7", "#6366F1", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981"]


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
        else:
            return cls.render_vertical_bar(candidate.data_source, candidate.title)

    @classmethod
    def render_donut(cls, series: CategoricalSeries, title: str) -> go.Figure:
        labels = [it.label for it in series.items]
        values = [it.value for it in series.items]
        unit = series.unit or "%"
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=PALETTE[:len(labels)], line=dict(color='#FFFFFF', width=2)),
            textinfo='label+percent',
            hovertemplate=f"<b>%{{label}}</b><br>Value: %{{value}} {unit}<br>Share: %{{percent}}<extra></extra>"
        )])
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            margin=dict(l=20, r=20, t=40, b=20),
            height=320,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        return fig

    @classmethod
    def render_horizontal_bar(cls, series: CategoricalSeries, title: str) -> go.Figure:
        # Sort items descending
        sorted_items = sorted(series.items, key=lambda x: x.value)
        labels = [it.label for it in sorted_items]
        values = [it.value for it in sorted_items]
        unit = series.unit or ""
        
        fig = go.Figure(data=[go.Bar(
            y=labels,
            x=values,
            orientation='h',
            marker=dict(
                color='#0F766E',
                line=dict(color='#115E59', width=1)
            ),
            hovertemplate=f"<b>%{{y}}</b><br>{series.metric_name}: %{{x}} {unit}<extra></extra>"
        )])
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            xaxis=dict(title=f"{series.metric_name} ({unit})" if unit else series.metric_name, gridcolor='rgba(128,128,128,0.2)'),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=20, r=20, t=40, b=30),
            height=320,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        return fig

    @classmethod
    def render_vertical_bar(cls, series: CategoricalSeries, title: str) -> go.Figure:
        labels = [it.label for it in series.items]
        values = [it.value for it in series.items]
        unit = series.unit or ""
        
        fig = go.Figure(data=[go.Bar(
            x=labels,
            y=values,
            marker=dict(
                color='#0284C7',
                line=dict(color='#0369A1', width=1)
            ),
            hovertemplate=f"<b>%{{x}}</b><br>{series.metric_name}: %{{y}} {unit}<extra></extra>"
        )])
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            yaxis=dict(title=f"{series.metric_name} ({unit})" if unit else series.metric_name, gridcolor='rgba(128,128,128,0.2)'),
            margin=dict(l=20, r=20, t=40, b=30),
            height=320,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        return fig

    @classmethod
    def render_comparison_bar(cls, comp: ComparisonItem, title: str) -> go.Figure:
        categories = [comp.baseline_label, comp.current_label]
        values = [comp.baseline_value, comp.current_value]
        bar_colors = ['#94A3B8', '#0F766E' if (comp.delta_abs or 0) >= 0 else '#EF4444']
        unit = comp.unit or ""
        
        fig = go.Figure(data=[go.Bar(
            x=categories,
            y=values,
            marker=dict(color=bar_colors),
            text=[f"{v} {unit}" for v in values],
            textposition='auto',
            hovertemplate=f"<b>%{{x}}</b><br>Value: %{{y}} {unit}<extra></extra>"
        )])
        
        delta_str = f"Δ: {comp.delta_abs:+g} {unit}" if comp.delta_abs is not None else ""
        if comp.delta_pct is not None:
            delta_str += f" ({comp.delta_pct:+g}%)"
            
        fig.update_layout(
            title=dict(text=f"{title} | {delta_str}", font=dict(size=14)),
            yaxis=dict(title=f"{comp.metric_name} ({unit})" if unit else comp.metric_name, gridcolor='rgba(128,128,128,0.2)'),
            margin=dict(l=20, r=20, t=40, b=30),
            height=320,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        return fig
