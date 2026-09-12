import sys, os
sys.path.insert(0, os.path.abspath("."))
from ingestion.document_parser import DocumentParser

def test_sample_documents_ingestion():
    docs = [
        "sample_documents/financial_report.pdf",
        "sample_documents/hr_report.docx",
        "sample_documents/sales_operations_report.pdf",
        "sample_documents/academic_report.docx"
    ]
    for d in docs:
        res = DocumentParser.parse(d)
        print(f"Parsed {d}:")
        print(f"  Title: {res['title']}")
        print(f"  Pages: {res['page_count']}")
        print(f"  Tables found: {len(res['all_tables'])}")
        assert res['page_count'] >= 1, f"Expected at least 1 page for {d}"
        assert len(res['all_tables']) >= 1, f"Expected at least 1 table for {d}"
        assert len(res['full_text']) > 50, f"Expected extracted text for {d}"
        safe_headers = [str(h).encode('ascii', 'replace').decode('ascii') for h in res['all_tables'][0].headers]
        print(f"  First table headers: {safe_headers}")
        print("  OK\n")

if __name__ == "__main__":
    test_sample_documents_ingestion()
    print("All ingestion tests passed!")
