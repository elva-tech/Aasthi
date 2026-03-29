# oc_wrapper.py
import os
import json
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
import pytesseract

# keep your model choices
EXTRACTION_MODEL = "models/gemini-2.0-flash-lite"
RISK_MODEL = "models/gemini-2.0-flash-lite"

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ---------------- OCR (selected pages) ----------------
def ocr_pdf_to_text_selected(pdf_path: str, page_numbers=(0, 1, 19), dpi: int = 220) -> str:
    """
    OCR only key pages for OC risk scoring:
      - page 1 (index 0): OC header + issuing authority
      - page 2 (index 1): inspection/notes (often deviations)
      - page 20 (index 19): conditions
    """
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(pdf_path)
    out: List[str] = []

    for p in page_numbers:
        if p < 0 or p >= len(doc):
            continue
        page = doc[p]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        txt = (pytesseract.image_to_string(img) or "").strip()
        if txt:
            out.append(f"\n--- OCR PAGE {p+1} ---\n{txt}")

    return "\n".join(out).strip()


# ---------------- Gemini helpers ----------------
from google import genai

load_dotenv()

def get_extraction_client():
    key = os.getenv("GEMINI_EXTRACTION_KEY")
    if not key:
        raise RuntimeError("Missing GEMINI_EXTRACTION_KEY")
    return genai.Client(api_key=key)

def get_risk_client():
    key = os.getenv("GEMINI_RISK_KEY")
    if not key:
        raise RuntimeError("Missing GEMINI_RISK_KEY")
    return genai.Client(api_key=key)


def parse_json_robust(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ---------------- Gemini extraction ----------------
def gemini_extract_oc_json(client, oc_text: str) -> Dict[str, Any]:
    schema_example = {
        "document_type": "Occupancy Certificate | Unknown",
        "issuing_authority": "string | null",
        "oc_number": "string | null",
        "issue_date": "string | null (prefer YYYY-MM-DD if present)",
        "project_name": "string | null",
        "property_address": "string | null",
        "builder_or_owner": "string | null",
        "sanction_plan_reference": "string | null",
        "site_area": "string | null",
        "builtup_area": "string | null",
        "floors_or_blocks": "string | null",
        "usage_type": "string | null",
        "conditions": ["string", "..."],
        "noted_deviations": ["string", "..."],
        "required_clearances": ["string", "..."],
        "confidence_notes": "string"
    }

    prompt = f"""
Extract fields from an Occupancy Certificate (OC).

Return ONLY valid JSON (no markdown, no extra text) matching this schema example:
{json.dumps(schema_example, indent=2)}

Rules:
- If not found: use null (or [] for arrays).
- Do NOT guess or infer missing facts.
- Put OC conditions/clauses into "conditions".
- Put only explicitly mentioned deviations into "noted_deviations".
- If conditions mention: fire, basement use, deviations, drainage/RWH, waste management, inspections—include them.

OC TEXT (OCR):
{oc_text[:120000]}
""".strip()

    resp = client.models.generate_content(
        model=EXTRACTION_MODEL,
        contents=prompt,
        config={"temperature": 0}
    )
    return parse_json_robust(resp.text)


# ---------------- Gemini LLM risk assessment ----------------
def gemini_llm_risk_assessment(client, oc_json: Dict[str, Any]) -> Dict[str, Any]:
    risk_prompt = f"""
You are a Building Compliance and Risk Assessment Expert.

Use ONLY the information provided below. Do NOT assume missing facts.

OCCUPANCY DATA (JSON):
{json.dumps(oc_json, indent=2)}

Return ONLY valid JSON:

{{
  "risk_summary": "...",
  "risks": [
    {{
      "category": "...",
      "severity": "LOW|MODERATE|HIGH|CRITICAL",
      "issue": "...",
      "impact": "...",
      "reasoning": "..."
    }}
  ],
  "recommended_actions": ["...", "..."],
  "overall_risk_level": "Low|Moderate|High|Critical",
  "suggested_score_out_of_100": 0
}}
""".strip()

    resp = client.models.generate_content(
        model=RISK_MODEL,
        contents=risk_prompt,
        config={"temperature": 0}
    )
    return parse_json_robust(resp.text)


# ---------------- Deterministic risk score ----------------
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_risk_score(
    oc_data: Dict[str, Any],
    user_inputs: Optional[Dict[str, Any]] = None,
    unknown_policy: str = "conservative"
) -> Tuple[int, List[Dict[str, Any]]]:
    if user_inputs is None:
        user_inputs = {}

    weights = {
        "statutory_oc": 25,
        "fire_life": 20,
        "structural": 15,
        "electrical_utilities": 10,
        "basement_flood": 10,
        "water_environment": 10,
        "legal_docs": 5,
        "maintenance_ops": 5,
    }

    bucket = dict(weights)
    deductions: List[Dict[str, Any]] = []

    deviations = oc_data.get("noted_deviations", []) or []

    # Statutory/OC: explicit deviations/exclusions
    if deviations:
        bucket["statutory_oc"] -= 8
        deductions.append({
            "bucket": "statutory_oc",
            "points": 8,
            "reason": "Deviations/exclusions noted in OC",
            "evidence": deviations[:3]
        })

    # Fire & life
    fire_noc_valid = user_inputs.get("fire_noc_valid")
    if fire_noc_valid is False:
        bucket["fire_life"] -= 15
        deductions.append({"bucket": "fire_life", "points": 15, "reason": "Fire NOC missing/expired"})
    elif fire_noc_valid is None and unknown_policy == "conservative":
        bucket["fire_life"] -= 3
        deductions.append({"bucket": "fire_life", "points": 3, "reason": "Unknown: Fire NOC validity"})

    # Structural
    major_cracks = user_inputs.get("major_structural_cracks")
    if major_cracks is True:
        bucket["structural"] -= 12
        deductions.append({"bucket": "structural", "points": 12, "reason": "Major structural cracks/settlement"})
    elif major_cracks is None and unknown_policy == "conservative":
        bucket["structural"] -= 2
        deductions.append({"bucket": "structural", "points": 2, "reason": "Unknown: structural condition"})

    # Electrical/utilities
    lift_cert_valid = user_inputs.get("lift_certificate_valid")
    if lift_cert_valid is False:
        bucket["electrical_utilities"] -= 5
        deductions.append({"bucket": "electrical_utilities", "points": 5, "reason": "Lift certificate expired/missing"})
    elif lift_cert_valid is None and unknown_policy == "conservative":
        bucket["electrical_utilities"] -= 1
        deductions.append({"bucket": "electrical_utilities", "points": 1, "reason": "Unknown: lift certificate"})

    # Basement/flood
    basement_misuse = user_inputs.get("basement_used_for_non_parking")
    if basement_misuse is True:
        bucket["basement_flood"] -= 8
        deductions.append({"bucket": "basement_flood", "points": 8, "reason": "Basement used for non-parking"})
    elif basement_misuse is None and unknown_policy == "conservative":
        bucket["basement_flood"] -= 2
        deductions.append({"bucket": "basement_flood", "points": 2, "reason": "Unknown: basement usage compliance"})

    basement_flooding = user_inputs.get("basement_flooding_history")
    if basement_flooding is True:
        bucket["basement_flood"] -= 5
        deductions.append({"bucket": "basement_flood", "points": 5, "reason": "Basement flooding/waterlogging reported"})
    elif basement_flooding is None and unknown_policy == "conservative":
        bucket["basement_flood"] -= 1
        deductions.append({"bucket": "basement_flood", "points": 1, "reason": "Unknown: basement flooding history"})

    # Water/environment
    stp_ok = user_inputs.get("stp_functional")
    if stp_ok is False:
        bucket["water_environment"] -= 6
        deductions.append({"bucket": "water_environment", "points": 6, "reason": "STP not functional/non-compliant"})
    elif stp_ok is None and unknown_policy == "conservative":
        bucket["water_environment"] -= 2
        deductions.append({"bucket": "water_environment", "points": 2, "reason": "Unknown: STP status"})

    rwh_ok = user_inputs.get("rainwater_harvesting_present")
    if rwh_ok is False:
        bucket["water_environment"] -= 4
        deductions.append({"bucket": "water_environment", "points": 4, "reason": "Rainwater harvesting missing"})
    elif rwh_ok is None and unknown_policy == "conservative":
        bucket["water_environment"] -= 1
        deductions.append({"bucket": "water_environment", "points": 1, "reason": "Unknown: RWH status"})

    # Legal/docs
    title_clear = user_inputs.get("title_clear")
    if title_clear is False:
        bucket["legal_docs"] -= 5
        deductions.append({"bucket": "legal_docs", "points": 5, "reason": "Title not clear / litigation risk"})
    elif title_clear is None and unknown_policy == "conservative":
        bucket["legal_docs"] -= 1
        deductions.append({"bucket": "legal_docs", "points": 1, "reason": "Unknown: title clarity"})

    # Maintenance/ops
    amc_present = user_inputs.get("critical_amcs_present")
    if amc_present is False:
        bucket["maintenance_ops"] -= 4
        deductions.append({"bucket": "maintenance_ops", "points": 4, "reason": "Critical AMCs missing"})
    elif amc_present is None and unknown_policy == "conservative":
        bucket["maintenance_ops"] -= 1
        deductions.append({"bucket": "maintenance_ops", "points": 1, "reason": "Unknown: AMCs status"})

    for k, w in weights.items():
        bucket[k] = int(clamp(bucket[k], 0, w))

    total = int(clamp(sum(bucket.values()), 0, 100))
    return total, deductions


def blend_scores(rule_score: int, llm_score: Optional[float], rule_weight: float = 0.7) -> Optional[int]:
    if llm_score is None:
        return None
    try:
        llm_score_f = float(llm_score)
    except (TypeError, ValueError):
        return None
    final = rule_weight * rule_score + (1 - rule_weight) * llm_score_f
    return int(round(clamp(final, 0, 100)))


# ============================================================
# ✅ NEW: RISK SCORE = 100 - SAFETY SCORE (HELPERS)
# ============================================================

def risk_score_from_safety(score: Optional[int]) -> Optional[int]:
    if score is None:
        return None
    try:
        s = int(score)
    except (TypeError, ValueError):
        return None
    s = int(clamp(s, 0, 100))
    return 100 - s


# ============================================================
# NEW: COMPACT SUMMARY (no OCR text)
# ============================================================

def compact_oc_summary(oc_json: Dict[str, Any]) -> dict:
    # take only important fields
    return {
        "issuing_authority": oc_json.get("issuing_authority"),
        "oc_number": oc_json.get("oc_number"),
        "issue_date": oc_json.get("issue_date"),
        "project_name": oc_json.get("project_name"),
        "property_address": oc_json.get("property_address"),
        "builtup_area": oc_json.get("builtup_area"),
        "usage_type": oc_json.get("usage_type"),
        "required_clearances": (oc_json.get("required_clearances") or [])[:5],
        "noted_deviations": (oc_json.get("noted_deviations") or [])[:5],
        "conditions_top": (oc_json.get("conditions") or [])[:8],
    }


def reasons_from_audit(audit: List[Dict[str, Any]]) -> List[str]:
    # convert audit deductions to human-friendly reasons
    out = []
    for a in audit[:8]:
        pts = a.get("points")
        reason = a.get("reason")
        out.append(f"-{pts} : {reason}")
    return out


# ============================================================
# WRAPPER: returns COMPACT JSON (now includes risk_score = 100-score)
# ============================================================

def run_oc_wrapper_compact(
    pdf_path: str,
    tesseract_cmd: Optional[str] = None,
    page_numbers=(0, 1, 19),
    dpi: int = 220,
    user_inputs: Optional[Dict[str, Any]] = None,
    unknown_policy: str = "conservative",
    run_llm_risk: bool = True,
    blend_rule_weight: float = 0.7,
    session_id: str = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    out: Dict[str, Any] = {
        "document_type": "OC",
        "pdf_path": pdf_path,
        "important_data": None,
        "scores": {
            "rule_score": None,
            "rule_risk_score": None,          # ✅ 100 - rule_score
            "llm_suggested_score": None,
            "llm_risk_score": None,           # ✅ 100 - llm_suggested_score
            "blended_score": None,
            "blended_risk_score": None,       # ✅ 100 - blended_score
            "overall_risk_level": None
        },
        "reasons": {
            "rule_deductions": [],
            "llm_risk_summary": None,
            "top_llm_risks": []
        },
        "errors": {"ocr": None, "extraction": None, "llm_risk": None}
    }

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found at: {pdf_path}")

    # Capture screenshot for report
    if screenshot_dir and session_id:
        import fitz
        from PIL import Image
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"oc_result_{session_id}.png")
        try:
            doc = fitz.open(pdf_path)
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img.save(screenshot_path)
                print(f"DEBUG: Saved OC screenshot to {screenshot_path}")
            doc.close()
        except Exception as e:
            print(f"DEBUG: Failed to save OC screenshot: {e}")

    # 1) OCR (internal only, do not store in output)
    try:
        oc_text = ocr_pdf_to_text_selected(pdf_path, page_numbers=page_numbers, dpi=dpi)
        if not oc_text:
            raise RuntimeError("OCR produced no text. Try higher DPI or check the PDF scan quality.")
    except Exception as e:
        out["errors"]["ocr"] = str(e)
        return out

    # 2) Extract JSON
    try:
        extraction_client = get_extraction_client()
        oc_json = gemini_extract_oc_json(extraction_client, oc_text)
    except Exception as e:
        out["errors"]["extraction"] = str(e)
        return out

    out["important_data"] = compact_oc_summary(oc_json)

    # 3) LLM Risk optional
    llm_risk = None
    if run_llm_risk:
        try:
            risk_client = get_risk_client()
            llm_risk = gemini_llm_risk_assessment(risk_client, oc_json)
        except Exception as e:
            out["errors"]["llm_risk"] = str(e)

    # 4) Rule score
    if user_inputs is None:
        user_inputs = {
            "fire_noc_valid": None,
            "major_structural_cracks": None,
            "lift_certificate_valid": None,
            "basement_used_for_non_parking": None,
            "basement_flooding_history": None,
            "stp_functional": None,
            "rainwater_harvesting_present": None,
            "title_clear": None,
            "critical_amcs_present": None,
        }

    rule_score, audit = compute_risk_score(oc_json, user_inputs, unknown_policy=unknown_policy)
    out["scores"]["rule_score"] = rule_score
    out["scores"]["rule_risk_score"] = risk_score_from_safety(rule_score)  # ✅ 100 - rule_score
    out["reasons"]["rule_deductions"] = reasons_from_audit(audit)

    # 5) Blend score
    if llm_risk is not None:
        llm_suggested = llm_risk.get("suggested_score_out_of_100")
        out["scores"]["llm_suggested_score"] = llm_suggested
        out["scores"]["llm_risk_score"] = risk_score_from_safety(llm_suggested)  # ✅ 100 - llm score
        out["scores"]["overall_risk_level"] = llm_risk.get("overall_risk_level")

        blended = blend_scores(rule_score, llm_suggested, rule_weight=blend_rule_weight)
        out["scores"]["blended_score"] = blended
        out["scores"]["blended_risk_score"] = risk_score_from_safety(blended)  # ✅ 100 - blended

        out["reasons"]["llm_risk_summary"] = llm_risk.get("risk_summary")
        risks = llm_risk.get("risks") or []
        out["reasons"]["top_llm_risks"] = [
            {
                "severity": r.get("severity"),
                "category": r.get("category"),
                "issue": r.get("issue")
            }
            for r in risks[:6]
        ]

    return out


# ============================================================
# OPTIONAL CLI ENTRY
# ============================================================
if __name__ == "__main__":
    load_dotenv()
    PDF_PATH = r"/home/ravella/landed/OC-PLH-C.pdf"

    result = run_oc_wrapper_compact(
        pdf_path=PDF_PATH,
        tesseract_cmd=None,
        page_numbers=(0, 1, 19),
        dpi=220,
        run_llm_risk=True,
        blend_rule_weight=0.7
    )

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
