"""Unit test for Table Normalizer duplicate header handling and PyArrow compatibility."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
import pyarrow as pa
from ingestion.table_normalizer import deduplicate_headers, TableNormalizer

def test_duplicate_headers_handling():
    # Exact duplicate headers extracted from Microsoft 10-K Stockholders' Equity table
    duplicate_headers = [
        '(In millions)', 'Col_1', 'Shares', 'Shares', 'Shares', 'Col_5',
        'Amount', 'Amount', 'Amount', 'Col_9', 'Shares', 'Shares', 'Shares',
        'Col_13', 'Amount', 'Amount', 'Amount', 'Col_17', 'Shares', 'Shares',
        'Shares', 'Col_21', 'Amount', 'Amount', 'Amount'
    ]
    
    clean_headers = deduplicate_headers(duplicate_headers)
    print("Deduplicated headers count:", len(clean_headers))
    assert len(clean_headers) == len(duplicate_headers)
    assert len(set(clean_headers)) == len(clean_headers), "All headers must be unique!"
    
    # Test PyArrow conversion (Streamlit's internal dataframe rendering)
    dummy_row = ["Test"] * len(clean_headers)
    df = pd.DataFrame([dummy_row], columns=clean_headers)
    
    # This call previously failed with ValueError: Duplicate column names found
    table = pa.Table.from_pandas(df)
    assert table is not None
    assert table.num_columns == len(clean_headers)
    print("[PASS] Successfully converted deduplicated table to PyArrow without duplicate column error!")

if __name__ == "__main__":
    test_duplicate_headers_handling()
