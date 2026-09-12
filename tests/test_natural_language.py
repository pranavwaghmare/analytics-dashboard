"""Test natural language summary generation, metric name cleaning, and dimension sanitization."""
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from extraction.heuristic_extractor import clean_metric_name, HeuristicExtractor
from ingestion.table_normalizer import TableNormalizer
from schema.models import StandaloneMetric, CategoricalSeries, CategoricalDataPoint, ProvenanceRecord


def test_clean_metric_name():
    assert clean_metric_name("And Short-Term Investments") == "Short-Term Investments"
    assert clean_metric_name("and of the workforce") == "Workforce"
    assert clean_metric_name("the total revenue") == "Revenue"
    assert clean_metric_name("Overall placement rate") == "Placement Rate"
    assert clean_metric_name("- **EBITDA Margin**:") == "EBITDA Margin"
    assert clean_metric_name("as well as operating cash flow") == "Operating Cash Flow"


def test_natural_summary_generation():
    prov = ProvenanceRecord(
        source_document="msft_annual_report.pdf",
        page_number=1,
        verbatim_source_span="Short-Term Investments totaled $94.6 billion in 2025.",
        source_type="prose"
    )
    metric = StandaloneMetric(
        id="m1",
        name="And Short-Term Investments",
        current_value=94.6,
        unit="Billion USD",
        provenance=prov
    )
    series = CategoricalSeries(
        id="s1",
        metric_name="Shares",
        dimension_name="(In millions)",
        unit="Million",
        items=[CategoricalDataPoint(label=f"Item {i}", value=10.0 * i) for i in range(1, 7)],
        provenance=prov
    )
    summary = HeuristicExtractor._generate_summary(
        title="Tmp8g0ltbby",
        domain="Financial",
        period="2025",
        metrics=[metric],
        series=[series]
    )
    
    # Verify no temp artifacts or awkward fragments
    assert "Tmp8g0ltbby" not in summary
    assert "And Short-Term" not in summary
    assert "(In millions)" not in summary
    assert "Short-Term Investments" in summary
    assert "94.6 Billion USD" in summary
    assert "executive briefing synthesizes key analytical findings" in summary
    print("[PASS] Natural language summary generated successfully:\n", summary)


def test_table_normalizer_scale_and_dimension():
    headers = ["(In millions)", "Shares", "Amount"]
    rows = [
        ["Common Stock", "1,200", "5,400"],
        ["Preferred Stock", "300", "900"]
    ]
    norm = TableNormalizer.normalize_table(headers, rows)
    # Ensure generic 'Financial Line Item' and scale '(In millions)' are never output
    assert norm["dimension_name"] != "Financial Line Item"
    assert norm["dimension_name"] != "(In millions)"
    assert norm["dimension_name"] in ["Category", "Stock Class", "Class"]
    assert len(norm["metric_columns"]) == 2
    assert norm["metric_columns"][0]["unit"] == "Million Shares"
    assert norm["metric_columns"][1]["unit"] == "Million"
    print("[PASS] TableNormalizer properly detected scale unit and sanitized dimension name without generic placeholders!")


if __name__ == "__main__":
    test_clean_metric_name()
    test_natural_summary_generation()
    test_table_normalizer_scale_and_dimension()
