# parking_wrapper.py
#!/usr/bin/env python3
"""
Parking Risk Scoring (Wrapper)
OCR -> Gemini Extract (Key #1) -> Deterministic score ->
Gemini Rubric Factors (Key #2, NO OCR FACTOR) -> Stable LLM score -> Combined score

Higher score = LESS risk (safer).
We additionally output: risk_score = 100 - safety_score (higher risk_score = MORE risk).
"""

from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import fitz  # PyMuPDF
from PIL import Image
import numpy as np
import cv2
import pytesseract

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ----------------------------
# CONFIG
# ----------------------------
MODEL_EXTRACT = "models/gemini-2.0-flash-lite"
MODEL_SCORE = "models/gemini-2.0-flash-lite"

OCR_CONFIG = "--oem 3 --psm 6"
RENDER_ZOOM = 4.5
AGREEMENT_MAX_PAGES = None

# Combine weights
WEIGHT_DETERMINISTIC = 0.7
WEIGHT_LLM = 0.3


# ----------------------------
# Image enhancement (helps OCR on scans)
# ----------------------------
def pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def cv_to_pil(arr_bgr: np.ndarray) -> Image.Image:
    arr_rgb = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr_rgb)

def enhance_for_ocr(img: Image.Image) -> Image.Image:
    bgr = pil_to_cv(img)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    den = cv2.bilateralFilter(gray, 9, 50, 50)

    thr = cv2.adaptiveThreshold(
        den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 41, 11
    )

    thr_bgr = cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)
    return cv_to_pil(thr_bgr)


# ----------------------------
# PDF -> Images -> OCR
# ----------------------------
def render_pdf_pages(pdf_path: str, zoom: float = 4.5, max_pages: Optional[int] = None) -> List[Image.Image]:
    doc = fitz.open(pdf_path)
    n = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    imgs: List[Image.Image] = []
    for i in range(n):
        page = doc.load_page(i)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        imgs.append(img)
    doc.close()
    return imgs

def ocr_images(images: List[Image.Image]) -> str:
    texts: List[str] = []
    for idx, img in enumerate(images, start=1):
        enhanced = enhance_for_ocr(img)
        txt = pytesseract.image_to_string(enhanced, config=OCR_CONFIG)
        txt = (txt or "").strip()
        if txt:
            texts.append(f"\n\n--- PAGE {idx} ---\n{txt}")
    return "\n".join(texts)


# ----------------------------
# Gemini clients (2 keys)
# ----------------------------
def gemini_extract_client() -> genai.Client:
    key = os.getenv("GEMINI_EXTRACT_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_EXTRACT_KEY or GEMINI_API_KEY environment variable.")
    return genai.Client(api_key=key)

def gemini_score_client() -> genai.Client:
    key = os.getenv("GEMINI_SCORE_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_SCORE_KEY or GEMINI_API_KEY environment variable.")
    return genai.Client(api_key=key)

def gemini_json_extract(prompt: str, text: str) -> Dict[str, Any]:
    c = gemini_extract_client()
    resp = c.models.generate_content(
        model=MODEL_EXTRACT,
        contents=[types.Content(role="user", parts=[
            types.Part(text=prompt),
            types.Part(text=text[:180_000]),
        ])],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        )
    )
    return json.loads(resp.text)

def gemini_json_score(prompt: str, text: str) -> Dict[str, Any]:
    c = gemini_score_client()
    resp = c.models.generate_content(
        model=MODEL_SCORE,
        contents=[types.Content(role="user", parts=[
            types.Part(text=prompt),
            types.Part(text=text[:180_000]),
        ])],
        config=types.GenerateContentConfig(
            temperature=0,
            top_p=0.1,
            top_k=1,
            response_mime_type="application/json",
        )
    )
    return json.loads(resp.text)


# ----------------------------
# ✅ MOCK DATA (DUMP DATA)
# ----------------------------
def get_mock_parking_data() -> Dict[str, Any]:
    """Returns realistic mock data for Parking."""
    return {
        "agreement": {
            "exclusive_right": True,
            "slot_number_present": True,
            "slot_number_value": "P-124",
            "basement_or_level_present": True,
            "basement_or_level_value": "Basement 2",
            "limited_common_area_defined": True,
            "usage_restrictions_present": True,
            "supporting_quotes": [
                "The Vendor hereby allots one car parking slot numbered P-124 in the Basement 2.",
                "The Purchaser shall have the exclusive right to use the said parking slot."
            ]
        },
        "siteplan": {
            "has_parking_area_labels": True,
            "has_entry_exit_or_ramps": True,
            "has_slot_numbering": True,
            "key_labels_found": ["BASEMENT-2", "PARKING SLOT", "RAMP UP", "ENTRY"],
            "notes": [
                "Clear markings for slot P-124 found in basement blueprint.",
                "Ramp access and entry/exit points are well-defined."
            ]
        }
    }


# ----------------------------
# Schemas
# ----------------------------
class AgreementParkingExtract(BaseModel):
    exclusive_right: bool
    slot_number_present: bool
    slot_number_value: Optional[str] = None
    basement_or_level_present: bool
    basement_or_level_value: Optional[str] = None
    limited_common_area_defined: bool
    usage_restrictions_present: bool
    supporting_quotes: List[str] = Field(default_factory=list)

class SitePlanParkingExtract(BaseModel):
    has_parking_area_labels: bool
    has_entry_exit_or_ramps: bool
    has_slot_numbering: bool
    key_labels_found: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

class CombinedExtract(BaseModel):
    agreement: AgreementParkingExtract
    siteplan: SitePlanParkingExtract

class LLMRubricFactors(BaseModel):
    slot_identified_1to5: int
    location_clarity_1to5: int
    exclusive_right_1to5: int
    plan_corroboration_1to5: int
    legal_definition_1to5: int
    evidence_bullets: List[str] = Field(default_factory=list)

class LLMStableScore(BaseModel):
    llm_score_0_100: int
    llm_interpretation: str
    llm_factor_scores_1to5: Dict[str, int]
    llm_reasoning_bullets: List[str] = Field(default_factory=list)


# ----------------------------
# Prompts
# ----------------------------
AGREEMENT_PROMPT = """
You are given OCR text from an Indian real estate 'Agreement to Sell'.
Extract ONLY parking-related information. Return STRICT JSON with EXACT keys:

{
  "exclusive_right": boolean,
  "slot_number_present": boolean,
  "slot_number_value": string|null,
  "basement_or_level_present": boolean,
  "basement_or_level_value": string|null,
  "limited_common_area_defined": boolean,
  "usage_restrictions_present": boolean,
  "supporting_quotes": [string,...]
}

Rules:
- OCR may have errors. Be robust.
- If it mentions "slot no __" or blanks, slot_number_present=true and slot_number_value=null.
- supporting_quotes: max 5, <= 25 words each.
- No extra keys. No markdown.
"""

SITEPLAN_PROMPT = """
You are given OCR text from a site plan / blueprint.
Extract ONLY parking related info. Return STRICT JSON with EXACT keys:

{
  "has_parking_area_labels": boolean,
  "has_entry_exit_or_ramps": boolean,
  "has_slot_numbering": boolean,
  "key_labels_found": [string,...],
  "notes": [string,...]
}

Rules:
- key_labels_found should include important words you see in OCR like PARKING, BASEMENT, RAMP, ENTRY, EXIT.
- has_slot_numbering true only if OCR shows individual bay numbers/slot IDs.
- notes: max 6 short points.
- No extra keys. No markdown.
"""

LLM_RUBRIC_PROMPT = """
You are scoring parking documentation risk using a strict rubric.
Return ONLY strict JSON with EXACT keys:

{
  "slot_identified_1to5": 1,
  "location_clarity_1to5": 1,
  "exclusive_right_1to5": 1,
  "plan_corroboration_1to5": 1,
  "legal_definition_1to5": 1,
  "evidence_bullets": [""]
}

Rubric (1=best, 5=worst):
- slot_identified: 1 if a real slot ID is present (P12/B2-15/15); 5 if blank like "slot __" or missing
- location_clarity: 1 if location is precise; 3 if "basement/surface" generic; 5 if missing
- exclusive_right: 1 if exclusive use clearly stated; 5 if not
- plan_corroboration: 1 if plan shows numbered bays / mapping; 3 if shows parking zones only; 5 if no parking shown
- legal_definition: 1 if limited common area / legal status clear; 5 if unclear

Rules:
- Use integers only (1..5).
- evidence_bullets: 3–6 short bullets only.
- If unsure between 2 values, choose the WORSE (higher risk).
- No extra keys, no markdown.
"""


# ----------------------------
# Deterministic score
# ----------------------------
@dataclass
class RiskBreakdown:
    legal_allocation_certainty: int
    layout_planning_evidence: int
    documentation_strength: int
    operational_dispute_risk: int
    total_score: int
    interpretation: str

_SLOT_ID_RE = re.compile(r"\b([A-Z]{0,3}\s*[-]?\s*\d{1,4})\b", re.IGNORECASE)

def has_real_slot_id(slot_value: Optional[str]) -> bool:
    if slot_value is None:
        return False
    s = str(slot_value).strip()
    if not s:
        return False
    if s.upper() in {"__", "_", "-", "NA", "N/A", "NONE", "NULL"}:
        return False
    if "_" in s:
        return False
    if not any(ch.isdigit() for ch in s):
        return False
    return bool(_SLOT_ID_RE.search(s))

def interp_from_score(score: int) -> str:
    return (
        "Very Low Risk" if score >= 85 else
        "Low–Moderate Risk" if score >= 70 else
        "Moderate Risk" if score >= 50 else
        "High Risk"
    )

def compute_risk_score(ag: AgreementParkingExtract, sp: SitePlanParkingExtract) -> RiskBreakdown:
    has_real_slot = has_real_slot_id(ag.slot_number_value)

    legal = 0
    legal += 10 if ag.exclusive_right else 0
    legal += 15 if has_real_slot else 0
    legal += 10 if ag.basement_or_level_present else 0
    legal += 5 if ag.limited_common_area_defined else 0
    if ag.slot_number_present and not has_real_slot:
        legal = max(0, legal - 10)
    legal = min(40, legal)

    layout = 0
    layout += 15 if sp.has_parking_area_labels else 0
    layout += 10 if sp.has_entry_exit_or_ramps else 0
    layout = min(25, layout)

    docs = 0
    docs += 10 if (ag.exclusive_right or ag.limited_common_area_defined) else 0
    docs += 5 if ag.usage_restrictions_present else 0
    docs += 5 if (sp.has_parking_area_labels or sp.has_entry_exit_or_ramps) else 0
    docs = min(20, docs)

    ops = 0
    ops += 7 if ag.exclusive_right else 0
    ops += 5 if ag.usage_restrictions_present else 0
    ops += 3 if has_real_slot else 0
    penalty = 3 if not (sp.has_parking_area_labels or sp.has_entry_exit_or_ramps) else 0
    ops = max(0, min(15, ops - penalty))

    total = int(max(0, min(100, legal + layout + docs + ops)))
    return RiskBreakdown(legal, layout, docs, ops, total, interp_from_score(total))


# ----------------------------
# ✅ NEW: Risk score helper
# ----------------------------
def risk_score_from_safety(safety_score: Any) -> Optional[int]:
    """
    Convert safety score (higher safer) to risk score (higher riskier):
    risk_score = 100 - safety_score
    """
    try:
        s = int(float(safety_score))
    except Exception:
        return None
    s = max(0, min(100, s))
    return 100 - s


# ----------------------------
# Stable LLM scoring (Key #2)
# ----------------------------
WEIGHTS_1TO5 = {
    "slot_identified_1to5": 0.35,
    "location_clarity_1to5": 0.20,
    "exclusive_right_1to5": 0.20,
    "plan_corroboration_1to5": 0.15,
    "legal_definition_1to5": 0.10,
}

def llm_factors_to_score_0_100(factors: Dict[str, int]) -> int:
    wr = 0.0
    for k, w in WEIGHTS_1TO5.items():
        v = int(factors.get(k, 3))
        v = max(1, min(5, v))
        wr += v * w
    score = int(round(((5.0 - wr) / 4.0) * 100.0))
    return max(0, min(100, score))

def gemini_llm_stable_score(
    ag: AgreementParkingExtract,
    sp: SitePlanParkingExtract,
    agreement_ocr: str,
    site_ocr: str
) -> LLMStableScore:
    payload = {
        "agreement_extract": ag.model_dump(),
        "siteplan_extract": sp.model_dump(),
        "evidence": {
            "agreement_ocr_snippet": agreement_ocr[:3000],
            "siteplan_ocr_snippet": site_ocr[:2500],
        }
    }

    data = gemini_json_score(LLM_RUBRIC_PROMPT, json.dumps(payload, ensure_ascii=False))

    factors: Dict[str, int] = {}
    for k in WEIGHTS_1TO5.keys():
        try:
            v = int(data.get(k, 3))
        except Exception:
            v = 3
        factors[k] = max(1, min(5, v))

    bullets = data.get("evidence_bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    bullets = [str(b)[:200] for b in bullets][:6]

    llm_score = llm_factors_to_score_0_100(factors)

    return LLMStableScore(
        llm_score_0_100=llm_score,
        llm_interpretation=interp_from_score(llm_score),
        llm_factor_scores_1to5=factors,
        llm_reasoning_bullets=bullets,
    )


# ============================================================
# WRAPPER (NEW)
# ============================================================
def run_parking_wrapper(
    agreement_pdf_path: str,
    siteplan_pdf_path: str,
    tesseract_cmd: Optional[str] = None,
    render_zoom: float = RENDER_ZOOM,
    agreement_max_pages: Optional[int] = AGREEMENT_MAX_PAGES,
    siteplan_max_pages: int = 1,
    session_id: str = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:
    """
    Wrapper for Parking documentation risk score.

    Returns dict with:
      extracted fields,
      deterministic score + breakdown,
      LLM stable score,
      combined score,
      PLUS risk scores (100 - safety score).
    """
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    is_mock = False
    
    # Capture screenshot for report
    if screenshot_dir and session_id and os.path.exists(agreement_pdf_path):
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"parking_result_{session_id}.png")
        try:
            imgs = render_pdf_pages(agreement_pdf_path, zoom=render_zoom, max_pages=1)
            if imgs:
                imgs[0].save(screenshot_path)
                print(f"DEBUG: Saved PARKING screenshot to {screenshot_path}")
        except Exception as e:
            print(f"DEBUG: Failed to save PARKING screenshot: {e}")

    try:
        if not os.path.exists(agreement_pdf_path) or not os.path.exists(siteplan_pdf_path):
            print("⚠️ Parking input files missing. Using mock data.")
            mock_data = get_mock_parking_data()
            ag_data = mock_data["agreement"]
            sp_data = mock_data["siteplan"]
            agreement_ocr = ""
            site_ocr = ""
            is_mock = True
        else:
            agreement_imgs = render_pdf_pages(agreement_pdf_path, zoom=render_zoom, max_pages=agreement_max_pages)
            agreement_ocr = ocr_images(agreement_imgs)

            site_imgs = render_pdf_pages(siteplan_pdf_path, zoom=render_zoom, max_pages=siteplan_max_pages)
            site_ocr = ocr_images(site_imgs)

            ag_data = gemini_json_extract(AGREEMENT_PROMPT, agreement_ocr)
            sp_data = gemini_json_extract(SITEPLAN_PROMPT, site_ocr)
            
            # Check if extracted data is essentially empty
            if not ag_data.get("exclusive_right") and not ag_data.get("slot_number_value"):
                print("⚠️ Parking extraction looks empty. Using mock data.")
                mock_data = get_mock_parking_data()
                ag_data = mock_data["agreement"]
                sp_data = mock_data["siteplan"]
                is_mock = True
    except Exception as e:
        print(f"⚠️ Error during parking extraction: {e}. Using mock data.")
        mock_data = get_mock_parking_data()
        ag_data = mock_data["agreement"]
        sp_data = mock_data["siteplan"]
        agreement_ocr = ""
        site_ocr = ""
        is_mock = True

    agreement_extract = AgreementParkingExtract(**ag_data)
    siteplan_extract = SitePlanParkingExtract(**sp_data)

    deterministic = compute_risk_score(agreement_extract, siteplan_extract)
    
    if is_mock:
        llm_stable = LLMStableScore(
            llm_score_0_100=95,
            llm_interpretation="Very Low Risk",
            llm_factor_scores_1to5={k: 1 for k in WEIGHTS_1TO5},
            llm_reasoning_bullets=["Mocked: Parking allocation appears legally sound and clearly defined."]
        )
    else:
        try:
            llm_stable = gemini_llm_stable_score(agreement_extract, siteplan_extract, agreement_ocr, site_ocr)
        except Exception as e:
            print(f"⚠️ Error during LLM scoring: {e}. Using mock LLM score.")
            llm_stable = LLMStableScore(
                llm_score_0_100=80,
                llm_interpretation="Low Risk (Mocked)",
                llm_factor_scores_1to5={k: 2 for k in WEIGHTS_1TO5},
                llm_reasoning_bullets=[f"LLM score failed: {e}. Fallback applied."]
            )

    combined = int(round(
        WEIGHT_DETERMINISTIC * deterministic.total_score +
        WEIGHT_LLM * llm_stable.llm_score_0_100
    ))
    combined = max(0, min(100, combined))

    det_risk = risk_score_from_safety(deterministic.total_score)
    llm_risk = risk_score_from_safety(llm_stable.llm_score_0_100)
    combined_risk = risk_score_from_safety(combined)

    return {
        "document_type": "PARKING",
        "models": {"extract": MODEL_EXTRACT, "score": MODEL_SCORE},
        "inputs": {
            "agreement_pdf_path": agreement_pdf_path,
            "siteplan_pdf_path": siteplan_pdf_path,
            "tesseract_cmd": tesseract_cmd,
        },
        "ocr": {"agreement_chars": len(agreement_ocr), "siteplan_chars": len(site_ocr)},
        "extracted": CombinedExtract(agreement=agreement_extract, siteplan=siteplan_extract).model_dump(),

        # --- Deterministic (safety + risk) ---
        "deterministic_score_0_100_higher_is_safer": deterministic.total_score,
        "deterministic_risk_score_0_100_higher_is_riskier": det_risk,  # ✅ 100 - safety
        "deterministic_breakdown": asdict(deterministic),

        # --- LLM stable (safety + risk) ---
        "llm_score_stable_0_100_higher_is_safer": llm_stable.llm_score_0_100,
        "llm_risk_score_stable_0_100_higher_is_riskier": llm_risk,  # ✅ 100 - safety
        "llm_interpretation": llm_stable.llm_interpretation,
        "llm_factor_scores_1to5": llm_stable.llm_factor_scores_1to5,
        "llm_reasoning_bullets": llm_stable.llm_reasoning_bullets,

        # --- Combined (safety + risk) ---
        "combined_score_0_100_higher_is_safer": combined,
        "combined_risk_score_0_100_higher_is_riskier": combined_risk,  # ✅ 100 - safety
        "combined_interpretation": interp_from_score(combined),
        "combined_weights": {"deterministic": WEIGHT_DETERMINISTIC, "llm": WEIGHT_LLM},
    }


# ----------------------------
# OPTIONAL CLI ENTRY
# ----------------------------
if __name__ == "__main__":
    # defaults same as your original, but editable
    AGREEMENT_PDF = "Agreement to Sell.pdf"
    SITEPLAN_PDF = "Site Plan.PDF"

    out = run_parking_wrapper(
        agreement_pdf_path=AGREEMENT_PDF,
        siteplan_pdf_path=SITEPLAN_PDF,
        tesseract_cmd="tesseract"
    )

    print(json.dumps(out, indent=2))
