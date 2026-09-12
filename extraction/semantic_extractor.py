"""Unified Semantic Extraction Orchestrator.
Coordinates:
1. LLM Semantic Parsing (if API key available) with strict JSON schema constraints.
2. Deterministic Heuristic Extraction (always active as robust tabular & regex backbone).
3. Grounding & Anti-Hallucination Verification (enforcing verbatim source span checks).
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional
from extraction.heuristic_extractor import HeuristicExtractor, clean_metric_name
from schema.models import (
    DocumentAnalyticsModel,
    StandaloneMetric,
    ComparisonItem,
    CategoricalSeries,
    ProvenanceRecord,
    GroundingStatus,
    Relationship,
    AnalyticalInsight
)
from schema.validator import GroundingValidator

logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = """You are a rigorous, domain-agnostic semantic information extractor for organizational documents.
Your goal is to extract analytically useful quantitative facts without hallucinating any data.
You MUST output strictly valid JSON matching this schema:
{
  "document_title": "string",
  "inferred_domain": "Financial | Human Resources | Sales & Operations | Academic | General",
  "reporting_period": "string or null",
  "executive_summary": "1-2 sentence overview",
  "standalone_metrics": [
    {
      "name": "Metric name (e.g., Revenue, Headcount, Attrition Rate, Cash, cash equivalents, and short-term investments)",
      "current_value": float_number,
      "previous_value": float_number or null,
      "unit": "string (e.g., Crore INR, %, Employees, Deliveries)",
      "change_pct": float_number or null,
      "comparison_period": "YoY | QoQ | null",
      "favorable_direction": "up | down | neutral",
      "verbatim_source_span": "EXACT sentence from the document containing this number",
      "page_number": integer
    }
  ],
  "comparisons": [
    {
      "metric_name": "string",
      "baseline_label": "e.g., Previous, FY23",
      "baseline_value": float_number,
      "current_label": "e.g., Current, FY24",
      "current_value": float_number,
      "unit": "string",
      "favorable_direction": "up | down | neutral",
      "verbatim_source_span": "EXACT sentence from document",
      "page_number": integer
    }
  ],
  "relationships": [
    {
      "subject_metric": "string",
      "driver_metric": "string",
      "relationship_type": "driven_by | correlated_with",
      "description": "string",
      "verbatim_source_span": "EXACT sentence from document",
      "page_number": integer
    }
  ],
  "insights": [
    {
      "headline": "Short takeaway",
      "detail": "Description",
      "sentiment": "positive | negative | neutral",
      "verbatim_source_span": "EXACT sentence from document",
      "page_number": integer
    }
  ]
}

CRITICAL RULES:
1. Every numeric value MUST be explicitly stated in the document. NEVER invent or extrapolate numbers.
2. The "verbatim_source_span" MUST be an exact copy-paste from the text provided.
3. Preserve complete compound noun phrases (e.g., 'Cash, cash equivalents, and short-term investments', 'Property, plant, and equipment', 'Total operating expenses'). NEVER truncate noun phrases at commas.
4. Focus on primary organizational metrics from Executive Summary, Overview, and Results sections. Avoid extracting incidental footnote or accounting disclosures as primary standalone metrics.
5. If no clear previous value or delta is stated, leave previous_value and change_pct as null.
6. Output ONLY raw JSON, with no markdown backticks or commentary.
"""


def safe_parse_float(val: Any) -> Optional[float]:
    """Safely extracts a float from int, float, or formatted strings like '245,123', '14%', '$842'."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").strip()
    match = re.search(r'[-+]?\d+(?:\.\d+)?', s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def select_dense_document_text(doc_tree: Dict[str, Any], max_chars: int = 14000) -> str:
    """Selects the most analytically informative pages (executive summary, MD&A, highlights) for LLM reasoning."""
    full_text = doc_tree.get("full_text", "")
    pages = doc_tree.get("pages", [])
    
    if len(full_text) > max_chars and pages:
        priority_texts = []
        # Include first 3 pages
        for p in pages[:3]:
            if p.text:
                priority_texts.append(p.text)
                
        # Search for key analytical sections in remaining pages
        keywords = ["results of operations", "executive summary", "financial highlights", "revenue increased", "net income", "operating income", "headcount", "enrollment", "logistics"]
        for p in pages[3:]:
            p_lower = p.text.lower()
            if any(k in p_lower for k in keywords):
                priority_texts.append(p.text)
                if sum(len(t) for t in priority_texts) >= max_chars:
                    break
        return "\n\n".join(priority_texts)[:max_chars]
        
    return full_text[:max_chars]


class SemanticExtractor:
    @classmethod
    def extract(
        cls, doc_tree: Dict[str, Any], api_key: Optional[str] = None,
        provider: str = "groq", model_name: str = "llama-3.1-8b-instant"
    ) -> DocumentAnalyticsModel:
        """
        Executes semantic extraction:
        1. Always extracts deterministic tabular and linguistic facts.
        2. If LLM is available (Groq or Gemini), augments with semantic prose reasoning.
        3. Enforces anti-hallucination grounding verification.
        """
        # Step 1: Base heuristic extraction (guarantees zero failure)
        base_model = HeuristicExtractor.extract(doc_tree)
        
        # Step 2: Attempt Groq or Gemini LLM augmentation
        groq_key = api_key if provider == "groq" else (os.environ.get("GROQ_API_KEY") or api_key)
        gemini_key = api_key if provider == "gemini" else (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

        if groq_key:
            try:
                base_model = cls._augment_with_groq(doc_tree, base_model, groq_key, model_name=model_name)
                base_model.extraction_metadata["llm_status"] = "success"
                base_model.extraction_metadata["llm_provider"] = "groq"
            except Exception as e:
                logger.warning(f"Groq extraction failed: {e}. Falling back to deterministic model.")
                base_model.extraction_metadata["llm_status"] = f"failed: {e}"
        elif gemini_key:
            try:
                base_model = cls._augment_with_gemini(doc_tree, base_model, gemini_key)
                base_model.extraction_metadata["llm_status"] = "success"
                base_model.extraction_metadata["llm_provider"] = "gemini"
            except Exception as e:
                logger.warning(f"Gemini extraction failed: {e}. Falling back to deterministic model.")
                base_model.extraction_metadata["llm_status"] = f"failed: {e}"
        else:
            base_model.extraction_metadata["llm_status"] = "offline"

        # Step 3: Run Anti-Hallucination & Grounding Validation
        validated_model = GroundingValidator.validate_and_filter(
            model=base_model,
            doc_text=doc_tree.get("full_text", ""),
            doc_tables=doc_tree.get("all_tables", [])
        )
        return validated_model

    @classmethod
    def _augment_with_groq(
        cls, doc_tree: Dict[str, Any], base_model: DocumentAnalyticsModel,
        api_key: str, model_name: str = "llama-3.1-8b-instant"
    ) -> DocumentAnalyticsModel:
        """Invokes Groq API with strict JSON mode, safe TPM window, and automatic model fallback."""
        from groq import Groq
        client = Groq(api_key=api_key)
        
        prompt_text = f"Document Text:\n{select_dense_document_text(doc_tree, max_chars=14000)}"
        target_model = model_name or "llama-3.1-8b-instant"
        
        try:
            completion = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
        except Exception as e:
            err_str = str(e).lower()
            if ("model_not_found" in err_str or "does not exist" in err_str or "404" in err_str) and target_model != "llama-3.1-8b-instant":
                logger.info(f"Model {target_model} not found, retrying with llama-3.1-8b-instant...")
                target_model = "llama-3.1-8b-instant"
                completion = client.chat.completions.create(
                    model=target_model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt_text}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
            else:
                raise e
                
        base_model.extraction_metadata["llm_model"] = target_model
        raw_json = completion.choices[0].message.content.strip()
        # Clean any markdown code fence wrappers
        if raw_json.startswith("```"):
            raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
            raw_json = re.sub(r'\s*```$', '', raw_json)
            
        parsed = json.loads(raw_json)
        return cls._merge_parsed_json(parsed, doc_tree, base_model)

    @classmethod
    def _augment_with_gemini(cls, doc_tree: Dict[str, Any], base_model: DocumentAnalyticsModel, api_key: str) -> DocumentAnalyticsModel:
        """Invokes Gemini API via google-genai as fallback provider."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt_text = f"Document Text:\n{select_dense_document_text(doc_tree, max_chars=28000)}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=EXTRACTION_SYSTEM_PROMPT,
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        raw_json = response.text.strip()
        if raw_json.startswith("```"):
            raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
            raw_json = re.sub(r'\s*```$', '', raw_json)
            
        parsed = json.loads(raw_json)
        return cls._merge_parsed_json(parsed, doc_tree, base_model)

    @classmethod
    def _merge_parsed_json(cls, parsed: Dict[str, Any], doc_tree: Dict[str, Any], base_model: DocumentAnalyticsModel) -> DocumentAnalyticsModel:
        """Merges parsed LLM JSON entities into the canonical model."""
        
        doc_name = doc_tree.get("file_path", "document").split("/")[-1].split("\\")[-1]
        
        # Merge standalone metrics (avoiding exact duplicates)
        existing_names = {m.name.lower() for m in base_model.standalone_metrics}
        for item in parsed.get("standalone_metrics", []):
            m_name = clean_metric_name(item.get("name", "").strip())
            curr_val = safe_parse_float(item.get("current_value"))
            if m_name and m_name.lower() not in existing_names and curr_val is not None:
                prov = ProvenanceRecord(
                    source_document=doc_name,
                    page_number=int(item.get("page_number") or 1),
                    verbatim_source_span=item.get("verbatim_source_span", ""),
                    source_type="prose"
                )
                prev_val = safe_parse_float(item.get("previous_value"))
                chg_pct = safe_parse_float(item.get("change_pct"))
                
                base_model.standalone_metrics.append(StandaloneMetric(
                    id=f"llm_m_{len(base_model.standalone_metrics)+1}",
                    name=m_name,
                    current_value=curr_val,
                    display_value=f"{curr_val:g} {item.get('unit', '')}".strip(),
                    unit=item.get("unit", ""),
                    previous_value=prev_val,
                    change_pct=chg_pct,
                    comparison_period=item.get("comparison_period"),
                    favorable_direction=item.get("favorable_direction", "neutral"),
                    provenance=prov
                ))
                existing_names.add(m_name.lower())

        # Merge comparisons
        existing_comps = {c.metric_name.lower() for c in base_model.comparisons}
        for comp in parsed.get("comparisons", []):
            c_name = clean_metric_name(comp.get("metric_name", "").strip())
            curr_val = safe_parse_float(comp.get("current_value"))
            base_val = safe_parse_float(comp.get("baseline_value")) or 0.0
            if c_name and c_name.lower() not in existing_comps and curr_val is not None:
                prov = ProvenanceRecord(
                    source_document=doc_name,
                    page_number=int(comp.get("page_number") or 1),
                    verbatim_source_span=comp.get("verbatim_source_span", ""),
                    source_type="prose"
                )
                delta_abs = round(curr_val - base_val, 2)
                delta_pct = round((delta_abs / abs(base_val)) * 100.0, 1) if base_val != 0 else None
                
                base_model.comparisons.append(ComparisonItem(
                    id=f"llm_c_{len(base_model.comparisons)+1}",
                    metric_name=c_name,
                    baseline_label=comp.get("baseline_label", "Previous"),
                    baseline_value=base_val,
                    current_label=comp.get("current_label", "Current"),
                    current_value=curr_val,
                    delta_abs=delta_abs,
                    delta_pct=delta_pct,
                    unit=comp.get("unit", ""),
                    favorable_direction=comp.get("favorable_direction", "neutral"),
                    provenance=prov
                ))
                existing_comps.add(c_name.lower())

        # Merge relationships
        for rel in parsed.get("relationships", []):
            prov = ProvenanceRecord(
                source_document=doc_name,
                page_number=rel.get("page_number", 1),
                verbatim_source_span=rel.get("verbatim_source_span", ""),
                source_type="prose"
            )
            base_model.relationships.append(Relationship(
                id=f"llm_r_{len(base_model.relationships)+1}",
                subject_metric=rel.get("subject_metric", ""),
                driver_metric=rel.get("driver_metric", ""),
                relationship_type=rel.get("relationship_type", "driven_by"),
                description=rel.get("description", ""),
                provenance=prov
            ))

        # Merge insights
        for ins in parsed.get("insights", []):
            prov = ProvenanceRecord(
                source_document=doc_name,
                page_number=ins.get("page_number", 1),
                verbatim_source_span=ins.get("verbatim_source_span", ""),
                source_type="prose"
            )
            base_model.insights.append(AnalyticalInsight(
                id=f"llm_ins_{len(base_model.insights)+1}",
                headline=ins.get("headline", ""),
                detail=ins.get("detail", ""),
                sentiment=ins.get("sentiment", "neutral"),
                provenance=prov
            ))

        if parsed.get("document_title"):
            llm_title = str(parsed["document_title"]).strip()
            if re.search(r'^(?:tmp[a-z0-9_]+|temp[a-z0-9_]+)$', base_model.document_title, re.IGNORECASE) or base_model.document_title in ["Organizational Report", "Executive Formal Report"]:
                base_model.document_title = llm_title

        if parsed.get("executive_summary"):
            base_model.executive_summary = str(parsed["executive_summary"]).strip()
            
        return base_model
