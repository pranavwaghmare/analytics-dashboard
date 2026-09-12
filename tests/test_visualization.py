"""Integration test for Analytics and Visualization Recommendation Layer."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from ingestion.document_parser import DocumentParser
from extraction.semantic_extractor import SemanticExtractor
from analytics.metric_analyzer import MetricAnalyzer
from visualization.recommendation import VisualizationRecommender
from visualization.chart_factory import ChartFactory

def test_visualization_pipeline():
    docs = [
        "sample_documents/financial_report.pdf",
        "sample_documents/hr_report.docx",
        "sample_documents/sales_operations_report.pdf",
        "sample_documents/academic_report.docx"
    ]
    
    for d in docs:
        print(f"==================================================")
        print(f"Testing Visualization Pipeline for: {d}")
        print(f"==================================================")
        doc_tree = DocumentParser.parse(d)
        model = SemanticExtractor.extract(doc_tree)
        analysis = MetricAnalyzer.analyze(model)
        
        print(f"Hero KPIs ({len(analysis['hero_kpis'])}):")
        for kpi in analysis['hero_kpis']:
            print(f"  * {kpi.name}: {kpi.current_value} {kpi.unit} (prev: {kpi.previous_value}, change: {kpi.change_pct}%)")
            
        recommended = VisualizationRecommender.recommend_charts(
            series_list=analysis['series'],
            comparisons=analysis['comparisons'],
            max_charts=4
        )
        print(f"\nRecommended Visualizations ({len(recommended)}):")
        for cand in recommended:
            print(f"  * [{cand.chart_type.value}] {cand.title} (Score: {cand.score:.2f})")
            # Verify that Plotly can render this without exception
            fig = ChartFactory.render_chart(cand)
            assert fig is not None, f"Failed to render figure for {cand.title}"
            assert len(fig.data) > 0, f"Figure has no data traces for {cand.title}"
            
        print(f"\nAuto Insights ({len(analysis['insights'])}):")
        import html
        for ins in analysis['insights']:
            print(f"  - [{ins.sentiment.upper()}] {ins.headline}: {ins.detail}")
            card = f'<div style="border-left:4px solid #10B981;"><b>{html.escape(ins.headline)}</b><div>{html.escape(ins.detail)}</div></div>'
            assert len(card) > 0
            
        for rel in analysis['relationships']:
            card_rel = f'<div><b>{html.escape(rel.subject_metric)} -> {html.escape(rel.driver_metric)}</b><div>{html.escape(rel.description)}</div></div>'
            assert len(card_rel) > 0
            
        assert len(analysis['hero_kpis']) >= 1, f"Expected hero KPIs for {d}"
        assert len(recommended) >= 1, f"Expected recommended charts for {d}"
        print(f"\n[PASS] Successfully verified visualizations for {d}\n")

if __name__ == "__main__":
    test_visualization_pipeline()
    print("ALL VISUALIZATION PIPELINE TESTS PASSED!")
