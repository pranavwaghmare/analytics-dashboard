"""Unit and security test for Grounding and Anti-Hallucination Gateway.
Verifies that:
1. Hallucinated numbers not present in the document are rejected.
2. Contrived source spans not present in the text are rejected.
3. Authentic extracted figures pass with high confidence.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from schema.models import (
    DocumentAnalyticsModel,
    StandaloneMetric,
    ProvenanceRecord,
    GroundingStatus
)
from schema.validator import GroundingValidator

def test_hallucination_rejection():
    real_text = "Revenue increased by 14% year-over-year to INR 842 crore, primarily driven by domestic sales."
    
    # 1. Grounded Metric
    valid_metric = StandaloneMetric(
        id="m_valid",
        name="Revenue",
        current_value=842.0,
        unit="INR Crore",
        provenance=ProvenanceRecord(
            source_document="test.pdf",
            page_number=1,
            verbatim_source_span="Revenue increased by 14% year-over-year to INR 842 crore",
            source_type="prose"
        )
    )
    
    # 2. Hallucinated Metric (fabricated number)
    hallucinated_metric = StandaloneMetric(
        id="m_fake_num",
        name="EBITDA",
        current_value=99999.0,
        unit="USD",
        provenance=ProvenanceRecord(
            source_document="test.pdf",
            page_number=1,
            verbatim_source_span="EBITDA reached 99999 USD",  # Span does not exist in real_text!
            source_type="prose"
        )
    )
    
    # 3. Partially Hallucinated (real span but fake number)
    tampered_metric = StandaloneMetric(
        id="m_tampered",
        name="Revenue",
        current_value=12345.0,  # Real span says 842, not 12345!
        unit="INR Crore",
        provenance=ProvenanceRecord(
            source_document="test.pdf",
            page_number=1,
            verbatim_source_span="Revenue increased by 14% year-over-year to INR 842 crore",
            source_type="prose"
        )
    )
    
    model = DocumentAnalyticsModel(
        document_title="Test Report",
        standalone_metrics=[valid_metric, hallucinated_metric, tampered_metric]
    )
    
    validated = GroundingValidator.validate_and_filter(model, real_text, [])
    
    # Assertions
    retained_ids = [m.id for m in validated.standalone_metrics]
    print(f"Retained metric IDs: {retained_ids}")
    
    assert "m_valid" in retained_ids, "Valid metric must be retained"
    assert "m_fake_num" not in retained_ids, "Hallucinated metric must be rejected"
    assert "m_tampered" not in retained_ids, "Tampered number must be rejected"
    print("[PASS] Anti-hallucination gateway successfully blocked fabricated metrics!")

if __name__ == "__main__":
    test_hallucination_rejection()
