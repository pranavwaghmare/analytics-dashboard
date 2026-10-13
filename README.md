# 📊 Intelligent Formal Document → Analytics Dashboard

> **Transform unstructured formal documents into grounded, interactive analytical dashboards.**  
> Domain-agnostic document ingestion, semantic metric extraction, anti-hallucination source grounding, and automated Plotly visualizations.

---

## 🚀 Overview

The **Intelligent Formal Document → Analytics Dashboard** is an end-to-end Python & Streamlit application that converts formal organizational documents (financial reports, operational updates, HR talent reviews, accreditation audits) into production-grade interactive analytical dashboards.

It bridges the gap between static documents and business intelligence:
- **Zero manual schema mapping**: Automatically identifies KPIs, tables, comparative metrics, and trend series.
- **Anti-Hallucination Grounding Gateway**: Links every single extracted metric directly back to verbatim source text spans with confidence scoring and page citations.
- **Hybrid Extraction Engine**: Leverages high-throughput Groq LLM inference (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) with a 100% offline, deterministic heuristic fallback.
- **Automated Visualization Engine**: Intelligently recommends and renders interactive Plotly figures based on underlying data shapes and analytical relevance.

---

## ✨ Features

- **📄 Multi-Format Ingestion**: Native structural extraction for **PDF** (via PyMuPDF & pdfplumber), **DOCX** (via python-docx), **XLSX**, and **CSV**.
- **⚡ Dual Extraction Modes**:
  - **Groq LLM Integration**: Ultra-fast semantic reasoning over document prose and complex tables.
  - **Offline Deterministic Fallback**: Rule-based heuristic extraction when no API key is supplied or when offline.
- **🛡️ Anti-Hallucination & Provenance Tracking**:
  - Verifies extracted values, units, and contexts against verbatim source text spans.
  - Interactive "Source Span" drill-down badges displaying page number and extraction confidence.
- **🧬 Canonical Intermediate Representation (IR)**:
  - Strongly typed Pydantic models for metrics, time series, explicit comparisons, and entity relationships.
  - Full schema validation and serialization.
- **📈 Automated Interactive Visualizations**:
  - Taxonomy-driven chart recommendation (time-series lines, distribution bars, comparison charts).
  - Responsive, dark/light-compatible Plotly visualizations.
- **💡 Analytical Insights & Relationships**:
  - Executive summary synthesis and Hero KPI ribbon.
  - Directional sentiment tags (positive, negative, neutral) on key takeaways.
  - Driver relationship discovery (e.g., metric A driving metric B).
- **🛠️ Technical Audit & Transparency**:
  - **Grounded Facts Audit**: Searchable table of all extracted metrics and verification status.
  - **Canonical IR**: Interactive JSON inspector of the raw Pydantic representation.
  - **Structural Tables**: View normalized tabular grids extracted from source pages.
- **🧪 Pre-Loaded Demo Reports**:
  - Corporate Financial Report (`.pdf`)
  - HR & Talent Review (`.docx`)
  - Sales & Logistics Operations (`.pdf`)
  - Academic Accreditation Report (`.docx`)

---

## 🏗️ Architecture & Pipeline

```text
┌─────────────────┐       ┌──────────────────────┐       ┌────────────────────────┐
│ Input Document  │  ──>  │ Ingestion & Parsing  │  ──>  │  Semantic Extraction   │
│ (PDF/DOCX/XLSX) │       │ (PyMuPDF, docx, etc) │       │  (Groq LLM / Heuristic)│
└─────────────────┘       └──────────────────────┘       └────────────────────────┘
                                                                     │
                                                                     ▼
┌─────────────────┐       ┌──────────────────────┐       ┌────────────────────────┐
│  Streamlit UI   │  <──  │ Metric Analysis &    │  <──  │ Grounding Gateway      │
│  (KPIs & Charts)│       │ Chart Recommendation │       │ (Verbatim Validation)  │
└─────────────────┘       └──────────────────────┘       └────────────────────────┘
```

1. **Ingestion**: Document parsed into a hierarchical document tree (sections, paragraphs, tables, pages).
2. **Semantic Extraction**: Structured facts, standalone metrics, and data series extracted into canonical Pydantic schemas.
3. **Grounding Gateway**: Validates numeric precision and units against document text; flags hallucinations.
4. **Metric Analysis**: Synthesizes summary, calculates deltas/growth rates, and maps metric drivers.
5. **Visualization Recommender**: Scores data candidates and instantiates suitable Plotly chart specifications.
6. **Presentation**: Interactive Streamlit dashboard with expandable provenance and audit logs.

---

## 📁 Project Structure

```text
analytics-dashboard/
├── app.py                      # Main Streamlit web application
├── requirements.txt            # Python dependencies
├── analytics/                  # Metric analysis and insight synthesis
│   └── metric_analyzer.py      # Hero KPIs, comparisons, driver relationships
├── extraction/                 # Semantic fact extraction logic
│   ├── heuristic_extractor.py  # Deterministic offline extraction engine
│   └── semantic_extractor.py   # Groq LLM extraction and grounding gate
├── ingestion/                  # Multi-format document parsing
│   ├── document_parser.py      # Unified document entry router
│   ├── docx_extractor.py       # Word (.docx) parser
│   ├── pdf_extractor.py        # PDF parser (PyMuPDF / pdfplumber)
│   └── table_normalizer.py     # Table sanitization and header deduplication
├── schema/                     # Canonical Intermediate Representation (IR)
│   ├── models.py               # Pydantic models (Metric, Series, Grounding, etc.)
│   └── validator.py            # Model validation routines
├── visualization/              # Visualization recommendation and rendering
│   ├── chart_factory.py        # Plotly chart builders
│   ├── recommendation.py       # Candidate scoring and chart selector
│   └── taxonomy.py             # Chart type taxonomy definitions
├── ui/                         # Reusable Streamlit HTML/CSS components
│   └── components.py           # KPI cards, badges, and provenance cards
├── sample_documents/           # Demonstration files and synthetic generator
│   ├── academic_report.docx
│   ├── financial_report.pdf
│   ├── generate_samples.py
│   ├── hr_report.docx
│   └── sales_operations_report.pdf
└── tests/                      # Automated test suite (Pytest)
```

---

## 🛠️ Getting Started

### Prerequisites

- **Python 3.10+** (Python 3.11 / 3.12 recommended)
- Optional: A [Groq API Key](https://console.groq.com) for fast LLM inference (free tier available).

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone https://github.com/pranavwaghmare/analytics-dashboard.git
cd analytics-dashboard

# Create and activate virtual environment
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On macOS/Linux:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Key (Optional)

The application works completely offline using the built-in deterministic heuristic engine. If you wish to use Groq LLM extraction:

```bash
# Set in environment:
export GROQ_API_KEY="your-groq-api-key"        # Linux/macOS
$env:GROQ_API_KEY="your-groq-api-key"          # Windows PowerShell

# Or simply paste your key into the sidebar in the Streamlit UI.
```

---

## 💻 How to Use

### Launch the Application

```bash
streamlit run app.py
```

The application will launch locally at `http://localhost:8501`.

### Exploring the Dashboard

1. **Select or Upload a Document**:
   - Choose one of the 4 pre-loaded samples from the sidebar dropdown (*Corporate Financial Report*, *HR & Talent Review*, etc.), **or**
   - Drag & drop your own **PDF**, **DOCX**, **XLSX**, or **CSV** file into the uploader.
2. **Configure Engine Settings** (Sidebar):
   - Provide a Groq API key or leave blank for offline deterministic mode.
   - Select the desired model (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, etc.).
3. **Inspect the Generated Dashboard**:
   - **Executive Summary & Metadata**: Domain classification and detected reporting periods.
   - **Hero KPI Cards**: Click **🔍 Source Span** on any card to view the exact sentence and page it was derived from.
   - **Interactive Charts**: Hover, zoom, pan, and filter series in the generated Plotly charts.
   - **Analytical Insights & Relationships**: Review synthesized drivers and notable changes.
   - **Technical Audit Tabs**:
     - *Grounded Facts Audit*: Review verification status, confidence score, and raw text citations.
     - *Canonical IR (JSON Schema)*: Inspect the structured Pydantic payload.
     - *Structural Tables*: Browse detected data tables extracted from the source document.

---

## 🧪 Running Tests

The test suite validates ingestion, table normalization, heuristic extraction, schema validation, and visualization generation:

```bash
pytest
```

---

## 📄 License

This project is licensed under the MIT License.
