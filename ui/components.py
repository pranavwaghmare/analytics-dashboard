"""Streamlit UI Components for KPIs, Provenance Drawers, and Badges.
Fully theme-adaptive (Dark & Light Mode compatible) with zero-indentation strings
to guarantee that Streamlit's Markdown parser never interprets HTML as code blocks.
"""

import html
from typing import Dict, Any, Optional
import streamlit as st
from schema.models import StandaloneMetric, ProvenanceRecord, GroundingStatus


def render_kpi_metric_native(metric: StandaloneMetric):
    """
    Renders a native Streamlit metric card inside a styled border container.
    100% immune to markdown code block indentation bugs and automatically
    adapts to the user's Dark / Light mode theme.
    """
    with st.container(border=True):
        delta_str = None
        delta_color = "normal"
        
        if metric.change_pct is not None:
            period_str = f" {metric.comparison_period}" if metric.comparison_period else ""
            delta_str = f"{metric.change_pct:+g}%{period_str}"
            
            # Favorable direction: down is good for Attrition, Cost, Return Rate
            if metric.favorable_direction == "down":
                delta_color = "inverse"
            elif metric.favorable_direction == "neutral":
                delta_color = "off"
            else:
                delta_color = "normal"
                
        val_display = f"{metric.current_value:g} {metric.unit}".strip()
        help_str = f"Previous: {metric.previous_value:g} {metric.unit}\nSource: Page {metric.provenance.page_number}" if metric.previous_value is not None else f"Source: Page {metric.provenance.page_number}"
        
        st.metric(
            label=metric.name.upper(),
            value=val_display,
            delta=delta_str,
            delta_color=delta_color,
            help=help_str
        )
        if metric.previous_value is not None:
            st.caption(f"Previous: **{metric.previous_value:g} {metric.unit}**")


def render_kpi_card_html(metric: StandaloneMetric) -> str:
    """
    Renders a custom HTML KPI card formatted strictly as a single unindented string.
    Zero leading spaces prevents Markdown parsers from triggering <pre><code> blocks.
    Uses theme-adaptive RGBA colors for seamless Dark/Light mode rendering.
    """
    name = html.escape(metric.name)
    val = f"{metric.current_value:g}"
    unit = html.escape(metric.unit)
    
    delta_html = ""
    if metric.change_pct is not None:
        sign = "+" if metric.change_pct > 0 else ""
        delta_str = f"{sign}{metric.change_pct:g}%"
        
        if metric.favorable_direction == "up":
            color = "#10B981" if metric.change_pct >= 0 else "#EF4444"
            bg = "rgba(16, 185, 129, 0.18)" if metric.change_pct >= 0 else "rgba(239, 68, 68, 0.18)"
        elif metric.favorable_direction == "down":
            color = "#10B981" if metric.change_pct <= 0 else "#EF4444"
            bg = "rgba(16, 185, 129, 0.18)" if metric.change_pct <= 0 else "rgba(239, 68, 68, 0.18)"
        else:
            color = "#0284C7"
            bg = "rgba(2, 132, 199, 0.18)"
            
        period = f" {html.escape(metric.comparison_period)}" if metric.comparison_period else ""
        delta_html = f'<div style="display:inline-flex; align-items:center; background:{bg}; color:{color}; font-weight:600; font-size:12px; padding:3px 8px; border-radius:12px; margin-top:4px;">{delta_str}{period}</div>'
        
    prev_html = ""
    if metric.previous_value is not None:
        prev_html = f'<div style="font-size:11px; opacity:0.75; margin-top:4px;">Prev: {metric.previous_value:g} {unit}</div>'

    # STRICTLY NO LEADING SPACES OR NEWLINES INSIDE HTML FRAGMENTS
    card = (
        f'<div style="border:1px solid rgba(128,128,128,0.25); border-radius:12px; padding:16px 18px; box-shadow:0 1px 3px rgba(0,0,0,0.06); min-height:120px; display:flex; flex-direction:column; justify-content:space-between; background:rgba(128,128,128,0.06);">'
        f'<div style="font-size:12px; font-weight:600; opacity:0.75; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;">{name}</div>'
        f'<div style="display:flex; align-items:baseline; gap:6px;">'
        f'<span style="font-size:28px; font-weight:700; line-height:1.2;">{val}</span>'
        f'<span style="font-size:14px; font-weight:500; opacity:0.8;">{unit}</span>'
        f'</div>'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:6px;">'
        f'{delta_html}'
        f'{prev_html}'
        f'</div>'
        f'</div>'
    )
    return card


def render_provenance_badge_html(prov: ProvenanceRecord, grounding: GroundingStatus) -> str:
    """Renders a theme-adaptive provenance audit badge without leading spaces."""
    doc_name = html.escape(prov.source_document)
    page_num = prov.page_number
    span = html.escape(prov.verbatim_source_span)
    conf = int(grounding.confidence_score * 100)
    
    badge_color = "#10B981" if grounding.is_grounded else "#F59E0B"
    badge_text = "Verified Grounded" if grounding.is_grounded else "Uncertain Context"
    
    badge = (
        f'<div style="border:1px solid rgba(128,128,128,0.2); border-radius:8px; padding:12px; margin-top:6px; font-size:12px; background:rgba(128,128,128,0.04);">'
        f'<div style="display:flex; justify-content:space-between; margin-bottom:6px;">'
        f'<span><b>Source:</b> {doc_name} (Page {page_num})</span>'
        f'<span style="border:1px solid {badge_color}; color:{badge_color}; padding:2px 8px; border-radius:10px; font-weight:600;">{badge_text} ({conf}%)</span>'
        f'</div>'
        f'<div style="font-style:italic; opacity:0.9; padding:6px 10px; border-radius:6px; border-left:3px solid {badge_color}; background:rgba(128,128,128,0.08);">"{span}"</div>'
        f'<div style="font-size:11px; opacity:0.75; margin-top:6px;">{html.escape(grounding.grounding_notes)}</div>'
        f'</div>'
    )
    return badge
