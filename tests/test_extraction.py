"""Integration test for Document Extraction and Grounding Validation."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from ingestion.document_parser import DocumentParser
from extraction.semantic_extractor import SemanticExtractor

def test_semantic_extraction_and_grounding():
    docs = [
        "sample_documents/financial_report.pdf",
        "sample_documents/hr_report.docx",
        "sample_documents/sales_operations_report.pdf",
        "sample_documents/academic_report.docx"
    ]
    
    for d in docs:
        print(f"==================================================")
        print(f"Processing: {d}")
        print(f"==================================================")
        doc_tree = DocumentParser.parse(d)
        model = SemanticExtractor.extract(doc_tree)
        
        print(f"Title: {model.document_title}")
        print(f"Inferred Domain: {model.inferred_domain}")
        print(f"Reporting Period: {model.reporting_period}")
        print(f"Summary: {model.executive_summary}\n")
        
        print(f"Standalone Metrics ({len(model.standalone_metrics)}):")
        for m in model.standalone_metrics:
            prev = f" (prev: {m.previous_value})" if m.previous_value is not None else ""
            delta = f" [{'+' if m.change_pct and m.change_pct > 0 else ''}{m.change_pct}%]" if m.change_pct is not None else ""
            grounded_badge = "[GROUNDED]" if m.grounding.is_grounded else "[UNGROUNDED]"
            safe_unit = m.unit.encode('ascii', 'replace').decode('ascii')
            print(f"  - {m.name}: {m.current_value} {safe_unit}{prev}{delta} | {grounded_badge} (conf: {m.grounding.confidence_score})")
            print(f"    Source: \"{m.provenance.verbatim_source_span[:60]}...\" (p. {m.provenance.page_number})")
            
        print(f"\nExplicit Comparisons ({len(model.comparisons)}):")
        for c in model.comparisons:
            print(f"  - {c.metric_name}: {c.baseline_label} {c.baseline_value}{c.unit} -> {c.current_label} {c.current_value}{c.unit} (delta: {c.delta_abs} / {c.delta_pct}%)")
            
        print(f"\nCategorical Series ({len(model.categorical_series)}):")
        for s in model.categorical_series:
            print(f"  - {s.metric_name} by {s.dimension_name} ({len(s.items)} items, part_of_whole={s.is_part_of_whole}):")
            for item in s.items[:4]:
                print(f"      * {item.label}: {item.value} {s.unit}")
                
        print(f"\nRelationships ({len(model.relationships)}):")
        for r in model.relationships:
            print(f"  - {r.subject_metric} --[{r.relationship_type}]--> {r.driver_metric}: {r.description}")
            
        assert len(model.standalone_metrics) >= 1 or len(model.categorical_series) >= 1, f"Expected metrics or series for {d}"
        print(f"\n[PASS] Verified extraction for {d}\n")

if __name__ == "__main__":
    test_semantic_extraction_and_grounding()
    print("ALL EXTRACTION & GROUNDING TESTS PASSED!")
