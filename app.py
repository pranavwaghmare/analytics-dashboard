"""Intelligent Formal Document -> Analytics Dashboard
Streamlit Application Entry Point.
"""

import os
import sys
import re
import tempfile
import json
import streamlit as st
import pandas as pd
import html

# Add project root to path
sys.path.insert(0, os.path.abspath("."))

from ingestion.document_parser import DocumentParser
import extraction.semantic_extractor
import importlib
importlib.reload(extraction.semantic_extractor)
from extraction.semantic_extractor import SemanticExtractor
from analytics.metric_analyzer import MetricAnalyzer
from visualization.recommendation import VisualizationRecommender
from visualization.chart_factory import ChartFactory
from ui.components import render_kpi_card_html, render_provenance_badge_html

# Defensive deduplication helper
try:
    from ingestion.table_normalizer import deduplicate_headers
except (ImportError, AttributeError):
    def deduplicate_headers(headers):
        seen = {}
        deduped = []
        for i, h in enumerate(headers):
            clean_name = str(h).strip() if h is not None and str(h).strip() else f"Col_{i+1}"
            if clean_name in seen:
                seen[clean_name] += 1
                deduped.append(f"{clean_name}_{seen[clean_name]}")
            else:
                seen[clean_name] = 1
                deduped.append(clean_name)
        return deduped

# Streamlit Page Config
st.set_page_config(
    page_title="Intelligent Document Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main-header {
        font-size: 26px;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 2px;
    }
    .sub-header {
        font-size: 14px;
        color: #64748B;
        margin-bottom: 20px;
    }
    .badge-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 8px;
    }
    .badge-domain {
        background-color: #EEF2FF;
        color: #4F46E5;
        border: 1px solid #C7D2FE;
    }
    .badge-period {
        background-color: #F0FDF4;
        color: #16A34A;
        border: 1px solid #BBF7D0;
    }
    .summary-box {
        background: rgba(15, 118, 110, 0.08);
        border-left: 4px solid #0F766E;
        padding: 14px 18px;
        border-radius: 8px;
        font-size: 14px;
        margin-bottom: 24px;
        line-height: 1.5;
    }
    .insight-card {
        background: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
</style>
""", unsafe_allow_html=True)


def process_document(file_path: str, api_key: str = None, doc_title: str = None, model_name: str = "openai/gpt-oss-120b"):
    """Executes the full pipeline: Ingestion -> Extraction -> Grounding -> Analytics -> Visualization."""
    with st.spinner("1/4 Ingesting document and extracting structural elements..."):
        doc_tree = DocumentParser.parse(file_path, original_title=doc_title)
        
    with st.spinner(f"2/4 Extracting semantic facts via {model_name if api_key else 'deterministic engine'} & grounding..."):
        try:
            model = SemanticExtractor.extract(doc_tree, api_key=api_key, model_name=model_name)
        except TypeError:
            model = SemanticExtractor.extract(doc_tree, api_key=api_key)
        
    with st.spinner("3/4 Analyzing metrics, comparisons, and deriving key takeaways..."):
        analysis = MetricAnalyzer.analyze(model)
        
    with st.spinner("4/4 Generating and ranking recommended Plotly visualizations..."):
        recommended_charts = VisualizationRecommender.recommend_charts(
            series_list=analysis["series"],
            comparisons=analysis["comparisons"],
            max_charts=4
        )
        
    return doc_tree, model, analysis, recommended_charts


def main():
    st.sidebar.title("⚙️ Engine Settings")
    st.sidebar.markdown("---")
    
    # Optional Groq Key
    groq_key = st.sidebar.text_input(
        "Groq API Key (Optional)",
        type="password",
        value=os.environ.get("GROQ_API_KEY", ""),
        help="Optional: Enter a Groq API key (free at console.groq.com) for reasoning with openai/gpt-oss-120b. The system operates fully offline via deterministic parsing if omitted."
    )
    
    groq_model = st.sidebar.selectbox(
        "Groq Model",
        options=[
            "openai/gpt-oss-120b"
        ],
        index=0,
        help="Groq inference using openai/gpt-oss-120b."
    )
    
    extraction_mode = f"⚡ Groq ({groq_model}) + Grounding Gateway" if groq_key else "🛡️ Deterministic Heuristic + Grounding Gateway"
    st.sidebar.info(f"**Active Mode:**\n{extraction_mode}")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🧪 Quick-Load Pre-Built Tests")
    
    sample_files = {
        "📈 Corporate Financial Report (PDF)": "sample_documents/financial_report.pdf",
        "👥 HR & Talent Review (DOCX)": "sample_documents/hr_report.docx",
        "🚚 Sales & Logistics Operations (PDF)": "sample_documents/sales_operations_report.pdf",
        "🎓 Academic Accreditation Report (DOCX)": "sample_documents/academic_report.docx"
    }
    
    selected_sample = st.sidebar.selectbox("Choose a demo document:", ["-- Select a Sample --"] + list(sample_files.keys()))
    
    # Document Input Router
    active_file_path = None
    active_doc_title = None
    
    st.markdown('<div class="main-header">Intelligent Formal Document → Analytics Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Domain-Agnostic Extraction, Anti-Hallucination Grounding & Automated Interactive Visualizations</div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Upload a formal document (PDF, DOCX, XLSX, CSV)",
        type=["pdf", "docx", "xlsx", "csv"],
        help="Provide any organizational report. The pipeline will parse text, tables, and generate an analytical dashboard without manual schema mapping."
    )
    
    if uploaded_file is not None:
        raw_name = os.path.splitext(uploaded_file.name)[0]
        active_doc_title = re.sub(r'[_\-]+', ' ', raw_name).strip().title()
        suffix = f".{uploaded_file.name.split('.')[-1]}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.read())
            active_file_path = tmp.name
    elif selected_sample != "-- Select a Sample --":
        active_file_path = sample_files[selected_sample]
        active_doc_title = selected_sample.split(" (")[0].replace("📈 ", "").replace("👥 ", "").replace("🚚 ", "").replace("🎓 ", "").strip()

    if not active_file_path:
        st.info("👆 Please upload a document or choose one of the 4 pre-built demonstration reports in the sidebar to begin.")
        
        # Display Feature Highlights
        st.markdown("### How the Pipeline Works")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.markdown("#### 1. Ingestion")
            st.caption("PDF & DOCX structural extraction using PyMuPDF, pdfplumber, and python-docx.")
        with col_b:
            st.markdown("#### 2. Semantic IR")
            st.caption("Canonical Pydantic models for metrics, series, explicit comparisons, and relationships.")
        with col_c:
            st.markdown("#### 3. Grounding Gate")
            st.caption("Verifies numeric values, contexts, and units directly against verbatim source spans.")
        with col_d:
            st.markdown("#### 4. Auto Visuals")
            st.caption("Data-shape taxonomy & objective relevance scoring generate responsive Plotly charts.")
        return

    # Process Document
    try:
        doc_tree, model, analysis, recommended_charts = process_document(
            active_file_path, api_key=groq_key, doc_title=active_doc_title, model_name=groq_model
        )
    except Exception as e:
        st.error(f"Error processing document: {e}")
        st.exception(e)
        return

    # Display LLM Status in Sidebar
    llm_status = model.extraction_metadata.get("llm_status", "offline")
    actual_model = model.extraction_metadata.get("llm_model", groq_model)
    if llm_status == "success":
        st.sidebar.success(f"⚡ Groq ({actual_model}) Active & Grounded")
    elif str(llm_status).startswith("failed"):
        st.sidebar.warning(f"⚠️ Groq Note: {llm_status}\n(Fell back to deterministic model)")
    else:
        st.sidebar.info("🛡️ Offline Deterministic Engine Active")

    # -------------------------------------------------------------
    # Render Dashboard
    # -------------------------------------------------------------
    st.markdown("---")
    
    # Document Header & Metadata
    col_head_1, col_head_2 = st.columns([3, 1])
    with col_head_1:
        st.subheader(analysis["title"])
        st.markdown(
            f'<span class="badge-pill badge-domain">{analysis["domain"]}</span>'
            f'<span class="badge-pill badge-period">{analysis["period"] or "All Periods"}</span>',
            unsafe_allow_html=True
        )
    with col_head_2:
        st.caption(f"**Pages Parsed:** {doc_tree['page_count']} | **Tables Detected:** {len(doc_tree['all_tables'])}")
        
    st.markdown(f'<div class="summary-box"><b>Executive Summary:</b> {analysis["summary"]}</div>', unsafe_allow_html=True)

    # 1. Hero KPI Ribbon
    if analysis["hero_kpis"]:
        st.markdown("### 📌 Key Performance Indicators")
        kpi_cols = st.columns(len(analysis["hero_kpis"]))
        for idx, kpi in enumerate(analysis["hero_kpis"]):
            with kpi_cols[idx]:
                st.markdown(render_kpi_card_html(kpi), unsafe_allow_html=True)
                with st.expander("🔍 Source Span"):
                    st.markdown(render_provenance_badge_html(kpi.provenance, kpi.grounding), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # 2. Automated Visualizations Grid
    if recommended_charts:
        st.markdown("### 📊 Interactive Visualizations")
        chart_cols = st.columns(2)
        
        CHART_BADGES = {
            "donut": ("🍩 Composition", "#4F46E5", "rgba(79, 70, 229, 0.1)"),
            "bar_horizontal": ("📊 Ranking & Breakdown", "#0284C7", "rgba(2, 132, 199, 0.1)"),
            "bar_vertical": ("📊 Distribution", "#0F766E", "rgba(15, 118, 110, 0.1)"),
            "comparison_bar": ("🔄 Variance & Comparison", "#10B981", "rgba(16, 185, 129, 0.1)"),
            "line_trend": ("📈 Historical Trend", "#8B5CF6", "rgba(139, 92, 246, 0.1)")
        }
        
        for idx, cand in enumerate(recommended_charts):
            col_target = chart_cols[idx % 2]
            with col_target:
                with st.container(border=True):
                    c_type_val = cand.chart_type.value if hasattr(cand.chart_type, 'value') else str(cand.chart_type)
                    badge_label, b_color, b_bg = CHART_BADGES.get(c_type_val, ("📊 Analytics", "#0284C7", "rgba(2, 132, 199, 0.1)"))
                    
                    prov = cand.data_source.provenance
                    grounding = cand.data_source.grounding
                    
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
                        f'<span style="font-size:11px; font-weight:700; color:{b_color}; background:{b_bg}; padding:3px 9px; border-radius:12px; text-transform:uppercase; letter-spacing:0.4px;">{badge_label}</span>'
                        f'<span style="font-size:11px; color:#64748B;">✓ Grounded · Page {prov.page_number}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    
                    fig = ChartFactory.render_chart(cand)
                    chart_config = {"displayModeBar": False, "responsive": True}
                    try:
                        st.plotly_chart(fig, width="stretch", config=chart_config)
                    except TypeError:
                        st.plotly_chart(fig, use_container_width=True, config=chart_config)
                    
                    # Provenance disclosure
                    with st.expander("🔍 Inspect Grounding Span & Confidence"):
                        st.markdown(render_provenance_badge_html(prov, grounding), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # 3. Key Insights & Relationships
    col_ins_1, col_ins_2 = st.columns([1, 1])
    
    with col_ins_1:
        st.markdown("### 💡 Key Analytical Insights")
        if analysis["insights"]:
            for ins in analysis["insights"][:4]:
                color_border = "#10B981" if ins.sentiment == "positive" else ("#EF4444" if ins.sentiment == "negative" else "#6366F1")
                card_ins = (
                    f'<div class="insight-card" style="border-left:4px solid {color_border};">'
                    f'<div style="font-weight:600; font-size:14px; margin-bottom:4px;">{html.escape(ins.headline)}</div>'
                    f'<div style="font-size:13px; opacity:0.85;">{html.escape(ins.detail)}</div>'
                    f'</div>'
                )
                st.markdown(card_ins, unsafe_allow_html=True)
        else:
            st.info("No explicit outlier insights synthesized.")

    with col_ins_2:
        st.markdown("### 🔗 Semantic Drivers & Relationships")
        if analysis["relationships"]:
            for rel in analysis["relationships"]:
                card_rel = (
                    f'<div class="insight-card" style="border-left:4px solid #F59E0B;">'
                    f'<div style="font-weight:600; font-size:14px;">{html.escape(rel.subject_metric)} ➔ {html.escape(rel.driver_metric)}</div>'
                    f'<div style="font-size:13px; opacity:0.85; margin-top:4px;">{html.escape(rel.description)}</div>'
                    f'</div>'
                )
                st.markdown(card_rel, unsafe_allow_html=True)
        else:
            st.info("No explicit driver relationships identified in document prose.")

    # 4. Technical Viva & Audit Tabs
    st.markdown("---")
    st.markdown("### 🛠️ Technical Audit & Intermediate Representation")
    
    tab_facts, tab_ir, tab_tables = st.tabs(["📋 Grounded Facts Audit", "🧬 Canonical IR (JSON Schema)", "📑 Structural Tables"])
    
    with tab_facts:
        facts_records = []
        for m in model.standalone_metrics:
            facts_records.append({
                "Metric Name": m.name,
                "Value": m.current_value,
                "Unit": m.unit,
                "Prev Value": m.previous_value,
                "Change %": f"{m.change_pct}%" if m.change_pct else "-",
                "Page": m.provenance.page_number,
                "Grounded": "✓ Verified" if m.grounding.is_grounded else "⚠️ Unverified",
                "Confidence": f"{int(m.grounding.confidence_score * 100)}%",
                "Verbatim Source Span": m.provenance.verbatim_source_span
            })
        if facts_records:
            try:
                st.dataframe(pd.DataFrame(facts_records), width="stretch")
            except TypeError:
                st.dataframe(pd.DataFrame(facts_records), use_container_width=True)
        else:
            st.info("No standalone metrics captured.")
            
    with tab_ir:
        st.caption("Pydantic `DocumentAnalyticsModel` serialized to canonical JSON.")
        st.json(model.model_dump())
        
    with tab_tables:
        if doc_tree["all_tables"]:
            for i, tbl in enumerate(doc_tree["all_tables"]):
                st.markdown(f"**Table {i+1} (Page {tbl.page_number}):** *{tbl.section_title or 'Data Grid'}*")
                clean_headers = deduplicate_headers(tbl.headers)
                num_cols = len(clean_headers)
                padded_rows = [
                    list(r) + [""] * (num_cols - len(r)) if len(r) < num_cols else list(r[:num_cols])
                    for r in tbl.rows
                ]
                df_tbl = pd.DataFrame(padded_rows, columns=clean_headers)
                try:
                    st.dataframe(df_tbl, width="stretch")
                except TypeError:
                    st.dataframe(df_tbl, use_container_width=True)
        else:
            st.info("No structured tables extracted from this document.")


if __name__ == "__main__":
    main()
