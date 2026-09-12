"""Comprehensive regression and generalizability test suite.
Validates:
1. Compound metric extraction preservation without truncation
2. Semantic KPI prioritization (Executive / Results metrics lead over footnotes)
3. Table semantic topology classification (Performance Comparison vs Categorical Breakdown vs Schedule)
4. Contextual dimension inference without generic 'Financial Line Item' placeholders
5. Chart-type-specific observation thresholds and quality gate (>= 0.65)
6. Cross-domain generalizability across Finance, HR, Operations, and Higher Education
"""

import os
import pytest
from ingestion.docx_extractor import DOCXExtractor
from ingestion.pdf_extractor import PDFExtractor
from ingestion.table_normalizer import TableNormalizer, TableTopology
from extraction.heuristic_extractor import HeuristicExtractor, clean_metric_name
from analytics.metric_analyzer import MetricAnalyzer
from visualization.recommendation import VisualizationRecommender
from visualization.taxonomy import ChartType


def test_clean_metric_name_compound_preservation():
    """Verify compound noun phrases are preserved with commas and conjunctions."""
    raw = "Cash, cash equivalents, and short-term investments"
    cleaned = clean_metric_name(raw)
    assert "cash equivalents" in cleaned.lower()
    assert "short-term investments" in cleaned.lower()
    assert cleaned.startswith("Cash")

    raw2 = "Property, plant, and equipment, net"
    cleaned2 = clean_metric_name(raw2)
    assert "plant" in cleaned2.lower()
    assert cleaned2.startswith("Property")


def test_table_topology_classification_generic():
    """Verify generic table topology classification without hardcoded indices."""
    # 1. Performance Comparison Table
    headers_perf = ["(In millions)", "2025", "2024", "Percentage Change"]
    rows_perf = [
        ["Revenue", "281,724", "245,122", "15%"],
        ["Operating income", "128,520", "109,433", "17%"],
        ["Net income", "101,800", "88,136", "16%"],
        ["Diluted earnings per share", "13.64", "11.80", "16%"]
    ]
    norm_perf = TableNormalizer.normalize_table(headers_perf, rows_perf, section_title="Results of Operations")
    assert norm_perf["topology"] == TableTopology.PERFORMANCE_COMPARISON
    assert norm_perf["dimension_name"] != "Financial Line Item"

    # 2. Categorical Breakdown Table
    headers_cat = ["(In millions)", "2025", "2024", "2023"]
    rows_cat = [
        ["Productivity and Business Processes", "104,500", "92,300", "80,100"],
        ["Intelligent Cloud", "102,400", "87,900", "75,300"],
        ["More Personal Computing", "74,824", "64,922", "60,200"],
        ["Total", "281,724", "245,122", "215,600"]
    ]
    norm_cat = TableNormalizer.normalize_table(headers_cat, rows_cat, section_title="Segment Results and Analysis")
    assert norm_cat["topology"] == TableTopology.CATEGORICAL_BREAKDOWN
    assert norm_cat["dimension_name"] == "Segment"

    # 3. Schedule Table (Dividend declarations)
    headers_sched = ["Declaration Date", "Record Date", "Payment Date", "Amount"]
    rows_sched = [
        ["September 19, 2024", "November 21, 2024", "December 12, 2024", "$0.83"],
        ["November 28, 2024", "February 20, 2025", "March 13, 2025", "$0.83"]
    ]
    norm_sched = TableNormalizer.normalize_table(headers_sched, rows_sched, section_title="Dividends")
    assert norm_sched["topology"] == TableTopology.NON_ANALYTICAL_SCHEDULE


def test_microsoft_annual_report_regression():
    """Regression test on Microsoft 2025 Annual Report document."""
    file_path = "2025_AnnualReport.docx"
    if not os.path.exists(file_path):
        pytest.skip("2025_AnnualReport.docx not present in workspace")

    # Ingestion check
    doc_tree = DOCXExtractor.extract(file_path)
    assert doc_tree["page_count"] > 1, "DOCX should have virtual pages (> 1) instead of flat 1"
    assert len(doc_tree["all_tables"]) > 0

    # Extraction check
    model = HeuristicExtractor.extract(doc_tree)
    metric_names = [m.name.lower() for m in model.standalone_metrics]

    # Verify compound metric was extracted
    compound_found = any("cash" in n and "short-term investments" in n for n in metric_names)
    assert compound_found, "Compound metric 'Cash, cash equivalents, and short-term investments' should be extracted"

    # Verify headline metrics exist
    assert any("revenue" in n for n in metric_names), "Revenue must be extracted"
    assert any("operating income" in n for n in metric_names), "Operating Income must be extracted"
    assert any("net income" in n for n in metric_names), "Net Income must be extracted"

    # Analysis & KPI prioritization check
    analysis = MetricAnalyzer.analyze(model)
    hero_kpi_names = [k.name.lower() for k in analysis["hero_kpis"]]

    # Primary organizational indicators must lead
    top_has_primary = any("revenue" in n or "income" in n or "margin" in n for n in hero_kpi_names)
    assert top_has_primary, f"Hero KPIs must feature primary metrics: {hero_kpi_names}"

    # Verify no 'Financial Line Item' in series dimension names
    for s in model.categorical_series:
        assert s.dimension_name != "Financial Line Item", f"Generic placeholder found in series {s.id}"
        # Verify totals are not included inside items
        labels = [it.label.lower() for it in s.items]
        assert "total" not in labels, f"Total should not be an item inside {s.metric_name}"

    # Visualization recommendations check
    recommended = VisualizationRecommender.recommend_charts(
        analysis["series"],
        analysis["comparisons"],
        max_charts=4
    )
    assert len(recommended) > 0, "Should recommend high quality charts"
    for r in recommended:
        # Tightened quality gate >= 0.70
        assert r.score >= 0.70, f"Chart {r.title} score {r.score} is below tightened quality threshold 0.70"
        # Verify technical disclosures and date metrics are excluded
        title_lower = r.title.lower()
        assert "weighted average life" not in title_lower, "Technical footnote chart 'Weighted Average Life' must be excluded"
        assert not any(dt in title_lower for dt in ["june 30", "march 31", "december 31"]), "Date should not be a chart metric"


def test_cross_domain_generalizability():
    """Verify clean extraction and recommendation across HR, Academic, and Operations documents."""
    sample_docs = [
        ("sample_documents/hr_report.docx", "Human Resources"),
        ("sample_documents/sales_operations_report.pdf", "Sales & Operations"),
        ("sample_documents/academic_report.docx", "Academic")
    ]
    for rel_path, expected_domain in sample_docs:
        if not os.path.exists(rel_path):
            continue
        if rel_path.endswith(".docx"):
            tree = DOCXExtractor.extract(rel_path)
        else:
            tree = PDFExtractor.extract(rel_path)

        model = HeuristicExtractor.extract(tree)
        assert len(model.standalone_metrics) > 0, f"No metrics extracted for {rel_path}"

        analysis = MetricAnalyzer.analyze(model)
        assert len(analysis["hero_kpis"]) > 0, f"No hero KPIs for {rel_path}"

        charts = VisualizationRecommender.recommend_charts(analysis["series"], analysis["comparisons"])
        assert len(charts) > 0, f"No charts recommended for {rel_path}"
        for c in charts:
            assert c.score >= 0.70, f"Cross-domain chart {c.title} score {c.score} < 0.70"


def test_unit_and_semantic_type_disambiguation():
    """Verify non-financial measures, counts, and percentages never inherit currency units."""
    # 1. Headcount count noun
    m1 = []
    HeuristicExtractor._extract_from_sentence(
        "Total global headcount reached 228,000 employees across all regions.",
        1, 0.1, "Workforce", "doc", m1, [], [], [], []
    )
    assert len(m1) == 1
    assert m1[0].current_value == 228000.0
    assert m1[0].unit == "Employees"
    assert "usd" not in m1[0].unit.lower() and "inr" not in m1[0].unit.lower()

    # 2. Duration / Days
    m2 = []
    HeuristicExtractor._extract_from_sentence(
        "Average time-to-hire stood at 42 days during the quarter.",
        1, 0.1, "HR", "doc", m2, [], [], [], []
    )
    assert len(m2) == 1
    assert m2[0].current_value == 42.0
    assert m2[0].unit == "Days"
    assert "$" not in m2[0].unit

    # 3. Rate / Percentage (prevent INR word-boundary bug from 'years')
    m3 = []
    HeuristicExtractor._extract_from_sentence(
        "The effective tax rate for both fiscal years 2025 and 2024 was 18%.",
        1, 0.1, "Tax", "doc", m3, [], [], [], []
    )
    assert len(m3) == 1
    assert m3[0].current_value == 18.0
    assert m3[0].unit == "%"
    assert "inr" not in m3[0].unit.lower()

    # 4. Diluted EPS per-share amount
    m4 = []
    c4 = []
    HeuristicExtractor._extract_from_sentence(
        "Diluted earnings per share was $13.64, up 16 percent year-over-year.",
        1, 0.1, "Results", "doc", m4, c4, [], [], []
    )
    assert len(m4) == 1
    assert m4[0].current_value == 13.64
    assert m4[0].unit == "USD / share"
    assert "billion" not in m4[0].unit.lower()


def test_metric_name_period_entity_decoupling():
    """Verify clean decoupling of metric names from temporal preambles, entities, and relative clauses."""
    # 1. Strip 'For the fiscal year ended...'
    raw1 = "For the fiscal year ended June 30, 2025, commercial cloud revenue"
    cleaned1 = clean_metric_name(raw1)
    assert cleaned1 == "Commercial Cloud Revenue"

    # 2. Strip 'As of June 30, 2025 and 2024...'
    raw2 = "As of June 30, 2025 and 2024, long-term accounts receivable"
    cleaned2 = clean_metric_name(raw2)
    assert cleaned2 == "Long-Term Accounts Receivable"

    # 3. Strip 'During fiscal years 2025, 2024, and 2023...'
    raw3 = "During fiscal years 2025, 2024, and 2023, depreciation expense"
    cleaned3 = clean_metric_name(raw3)
    assert cleaned3 == "Depreciation Expense"

    # 4. Strip non-restrictive relative clause
    raw4 = "Microsoft Cloud revenue, which includes Microsoft 365 Commercial cloud and Azure,"
    cleaned4 = clean_metric_name(raw4)
    assert cleaned4.lower() == "microsoft cloud revenue"

    # 5. Non-metric pronoun rejection
    raw5 = "there"
    assert clean_metric_name(raw5) == ""
