#!/usr/bin/env python3
"""
BANK LOAN (CERSAI) WRAPPER - Buyer Risk Scoring
==============================================

Pipeline:
1) PDF text extraction (pypdf)
2) LLM extraction (Key A) -> structured LoanDetails JSON
3) Deterministic risk scoring (rule-based)
4) LLM risk scoring (Key B) -> structured RiskScore JSON (stable prompt)
5) Blend deterministic + LLM -> final score
6) Save JSON to output/bankloan_result.json

Usage:
  python bankloan_wrapper.py --pdf "CERSAI_Search_Report.pdf"
  python bankloan_wrapper.py --pdf "..." --out "output/bankloan_result.json"
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pypdf import PdfReader

# NEW SDK (recommended)
from google import genai


# =========================
# CONFIG
# =========================
EXTRACTION_MODEL = "models/gemini-2.0-flash-lite"
RISK_MODEL = "models/gemini-2.0-flash-lite"

DEFAULT_OUT = "output/bankloan_result.json"


# =========================
# MODELS
# =========================
class LoanDetails(BaseModel):
    debtor_name: str = "Unknown"
    loan_amount: Optional[str] = None
    land_type: Optional[str] = None
    mortgaged_property: Optional[str] = None
    security_details: Optional[str] = None
    registration_status: Optional[str] = None  # "Satisfied" / "Not Satisfied"
    ltv_ratio: Optional[float] = None
    property_value: Optional[str] = None
    no_of_charges: Optional[int] = None
    charge_status: Optional[str] = None  # Satisfied/Unsatisfied/Not Satisfied
    property_age_years: Optional[int] = None
    occupancy_type: Optional[str] = None  # owner-occupied / vacant / tenant
    title_disputes: Optional[bool] = None


class RiskScore(BaseModel):
    overall_risk_score: float  # 0-100 (0=SAFE, 100=DON'T BUY)
    risk_level: str  # SAFE_TO_BUY, PROCEED_WITH_CAUTION, HIGH_RISK, DO_NOT_BUY

    land_type_risk: float
    security_risk: float
    registration_risk: float
    ltv_risk: float
    cersai_charges_risk: float
    title_quality_risk: float
    occupancy_risk: float

    key_findings: List[str]
    recommendations: List[str]
    risk_factor_breakdown: Dict[str, Any] = Field(default_factory=dict)

    # extra debug
    deterministic_overall: Optional[float] = None
    llm_overall: Optional[float] = None
    blend_weights: Optional[Dict[str, float]] = None


# =========================
# HELPERS
# =========================
def _ensure_dirs(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def extract_pdf_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    parts = []
    for p in reader.pages:
        t = p.extract_text() or ""
        parts.append(t)
    return "\n".join(parts).strip()


def _load_env_keys() -> Tuple[str, str]:
    extract_key = os.getenv("GEMINI_Bank_Extract", "").strip()
    risk_key = os.getenv("GEMINI_BANK_RISK", "").strip()
    if not extract_key:
        raise RuntimeError("Missing GEMINI_Bank_Extract in .env or environment")
    if not risk_key:
        raise RuntimeError("Missing GEMINI_BANK_RISK in .env or environment")
    return extract_key, risk_key


def _safe_json_load(text: str) -> Dict[str, Any]:
    # Trim code fences if any
    text = text.strip()
    text = re.sub(r"^\s*```json\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*```\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Try strict parse
    return json.loads(text)


def _genai_json(client: genai.Client, model: str, prompt: str) -> Dict[str, Any]:
    """
    Stable JSON:
      - temperature=0
      - ask for only JSON
    """
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "temperature": 0,
            "max_output_tokens": 2048,
        },
    )
    return _safe_json_load(resp.text or "")


def _normalize_status(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    x = s.strip().lower()
    # common normalization
    if "not satisfied" in x or "unsatisfied" in x or "not-satisfied" in x:
        return "Not Satisfied"
    if "satisfied" in x:
        return "Satisfied"
    return s.strip()


def _parse_amount_to_float(amount_str: Optional[str]) -> Optional[float]:
    if not amount_str:
        return None
    # keep digits only
    digits = re.sub(r"[^\d.]", "", amount_str)
    if not digits:
        return None
    try:
        return float(digits)
    except Exception:
        return None


# =========================
# 1) LLM EXTRACTION
# =========================
def analyze_loan_with_llm_extract(extract_client: genai.Client, pdf_text: str) -> LoanDetails:
    prompt = f"""
You are an expert bank-loan & CERSAI report parser.

Return ONLY valid JSON (no markdown, no extra text).
Fill missing as null.

Schema:
{{
  "debtor_name": "string",
  "loan_amount": "string|null",
  "land_type": "string|null",
  "mortgaged_property": "string|null",
  "security_details": "string|null",
  "registration_status": "Satisfied|Not Satisfied|null",
  "property_value": "string|null",
  "ltv_ratio": "number|null",
  "no_of_charges": "integer|null",
  "charge_status": "Satisfied|Not Satisfied|null",
  "property_age_years": "integer|null",
  "occupancy_type": "string|null",
  "title_disputes": "boolean|null"
}}

Rules:
- If registration/charge shows NOT SATISFIED/UNSATISFIED => "Not Satisfied"
- If clearly cleared => "Satisfied"
- no_of_charges: count how many separate charges/registrations appear in the report.
- ltv_ratio: compute if loan_amount + property_value are available.

CERSAI PDF TEXT:
\"\"\"{pdf_text[:22000]}\"\"\"
""".strip()

    try:
        data = _genai_json(extract_client, EXTRACTION_MODEL, prompt)

        # Normalize + coerce some fields
        data["registration_status"] = _normalize_status(data.get("registration_status"))
        data["charge_status"] = _normalize_status(data.get("charge_status"))

        # Ensure string for amounts
        if data.get("loan_amount") is not None:
            data["loan_amount"] = str(data["loan_amount"])
        if data.get("property_value") is not None:
            data["property_value"] = str(data["property_value"])

        # Only keep known fields
        filtered = {k: v for k, v in data.items() if k in LoanDetails.model_fields}
        return LoanDetails(**filtered)

    except Exception as e:
        # Minimal fallback (still usable)
        return LoanDetails(debtor_name="Unknown")


# =========================
# 2) DETERMINISTIC SCORING (BUYER VIEW)
# =========================
def deterministic_score(details: LoanDetails) -> Dict[str, Any]:
    """
    Returns:
      - per-factor risks 0..100
      - overall 0..100
      - risk_level
      - key_findings / recommendations (short)
    Buyer logic:
      - Active loan (Not Satisfied) => DO NOT BUY => 100
      - Multiple charges => higher risk
      - Title disputes => critical
      - Unknowns => moderate caution (not extreme)
    """
    reg = _normalize_status(details.registration_status or details.charge_status)
    charges = details.no_of_charges if details.no_of_charges is not None else None

    title_disputes = bool(details.title_disputes) if details.title_disputes is not None else False

    # Factor defaults
    land_type_risk = 30.0
    if details.land_type:
        lt = details.land_type.lower()
        if "res" in lt:
            land_type_risk = 15.0
        elif "agri" in lt or "agric" in lt:
            land_type_risk = 35.0
        elif "indus" in lt:
            land_type_risk = 55.0
        elif "comm" in lt:
            land_type_risk = 40.0

    occupancy_risk = 25.0
    if details.occupancy_type:
        oc = details.occupancy_type.lower()
        if "owner" in oc or "self" in oc:
            occupancy_risk = 10.0
        elif "vacant" in oc:
            occupancy_risk = 25.0
        elif "tenant" in oc or "rented" in oc:
            occupancy_risk = 45.0

    # Title is critical
    title_quality_risk = 10.0 if not title_disputes else 95.0

    # Charges
    if charges is None:
        cersai_charges_risk = 35.0  # unknown
    elif charges == 0:
        cersai_charges_risk = 0.0
    elif charges == 1:
        cersai_charges_risk = 20.0
    elif charges == 2:
        cersai_charges_risk = 45.0
    else:
        cersai_charges_risk = 70.0

    # Registration/loan status
    if reg == "Not Satisfied":
        registration_risk = 100.0
        security_risk = 100.0
        ltv_risk = 100.0
    elif reg == "Satisfied":
        registration_risk = 10.0
        security_risk = 10.0
        ltv_risk = 10.0
    else:
        registration_risk = 45.0
        security_risk = 40.0
        ltv_risk = 40.0

    # Weighted overall (buyer)
    # Title(40%) + Charges(30%) + Land(15%) + Occupancy(10%) + Others(5%)
    overall = (
        0.40 * title_quality_risk +
        0.30 * cersai_charges_risk +
        0.15 * land_type_risk +
        0.10 * occupancy_risk +
        0.05 * (registration_risk + security_risk) / 2.0
    )

    def level(score: float) -> str:
        if score >= 85:
            return "DO_NOT_BUY"
        if score >= 60:
            return "HIGH_RISK"
        if score >= 35:
            return "PROCEED_WITH_CAUTION"
        return "SAFE_TO_BUY"

    # Hard rule: active loan => do not buy
    if reg == "Not Satisfied":
        overall = 100.0

    findings = []
    recs = []

    if reg == "Not Satisfied":
        findings.append("❌ DEAL BREAKER: CERSAI shows 'Not Satisfied' (active charge) – property is encumbered.")
        recs.append("Reject unless seller clears the loan and CERSAI updates to 'Satisfied'.")
    else:
        if title_disputes:
            findings.append("⚠️ Title disputes indicated – extremely risky for buyer.")
            recs.append("Do not proceed without a lawyer-led title search and dispute resolution proof.")
        if charges is None:
            findings.append("⚠️ Number of charges not clearly extracted – needs manual verification.")
            recs.append("Re-check the CERSAI report and confirm how many charges exist and their status.")
        elif charges > 1:
            findings.append(f"⚠️ Multiple charges detected ({charges}) – increases complexity and risk.")
            recs.append("Collect lender NOC / satisfaction proof for each charge and verify updated status.")

    if not findings:
        findings = ["No critical red flags detected in deterministic pass, subject to manual verification."]
    if not recs:
        recs = ["Verify title chain, tax dues, and latest CERSAI status before signing."]

    return {
        "overall": round(float(overall), 2),
        "risk_level": level(overall),
        "factors": {
            "land_type_risk": round(land_type_risk, 2),
            "security_risk": round(security_risk, 2),
            "registration_risk": round(registration_risk, 2),
            "ltv_risk": round(ltv_risk, 2),
            "cersai_charges_risk": round(cersai_charges_risk, 2),
            "title_quality_risk": round(title_quality_risk, 2),
            "occupancy_risk": round(occupancy_risk, 2),
        },
        "key_findings": findings[:5],
        "recommendations": recs[:5],
        "breakdown": {
            "normalized_status": reg,
            "no_of_charges": charges,
            "title_disputes": title_disputes,
        },
    }


# =========================
# 3) LLM SCORING (KEY B)
# =========================
def llm_risk_score(risk_client: genai.Client, details: LoanDetails, pdf_text: str) -> RiskScore:
    # If active loan => automatic NO (kept deterministic + stable)
    norm_status = _normalize_status(details.charge_status or details.registration_status)
    if norm_status == "Not Satisfied":
        return RiskScore(
            overall_risk_score=100.0,
            risk_level="DO_NOT_BUY",
            land_type_risk=0.0,
            security_risk=100.0,
            registration_risk=100.0,
            ltv_risk=100.0,
            cersai_charges_risk=100.0,
            title_quality_risk=0.0,
            occupancy_risk=0.0,
            key_findings=[
                "❌ DEAL BREAKER: Active loan/charge exists with 'Not Satisfied' status.",
                "Property is encumbered; clear title transfer is not possible until charge is satisfied.",
                "High fraud risk if seller asks for payment before clearance.",
                "Buyer should treat this as automatic rejection unless updated proof is provided."
            ],
            recommendations=[
                "Reject the property unless the seller clears the charge and updates CERSAI.",
                "Ask for lender NOC + Letter of Satisfaction.",
                "Re-check fresh CERSAI report after clearance (same debtor/property).",
                "Proceed only after advocate confirms charge removal and title is clear."
            ],
            risk_factor_breakdown={
                "charge_status": f"CRITICAL: {norm_status}",
                "buyer_rule": "Active charge => DO_NOT_BUY",
            },
        )

    # Stable JSON scoring prompt
    prompt = f"""
You are a land purchase risk assessment expert helping a BUYER decide if it is safe to buy.

Return ONLY valid JSON (no markdown, no extra text) matching EXACTLY this schema:

{{
  "overall_risk_score": number,
  "risk_level": "SAFE_TO_BUY" | "PROCEED_WITH_CAUTION" | "HIGH_RISK" | "DO_NOT_BUY",
  "land_type_risk": number,
  "security_risk": number,
  "registration_risk": number,
  "ltv_risk": number,
  "cersai_charges_risk": number,
  "title_quality_risk": number,
  "occupancy_risk": number,
  "key_findings": string[],
  "recommendations": string[],
  "risk_factor_breakdown": object
}}

Scoring meaning:
- 0 = SAFE/GOOD for buyer
- 100 = VERY BAD / DON'T BUY

Weights to internally consider:
Title(40%) + Charges(30%) + Land(15%) + Occupancy(10%) + Others(5%)

Property Details (extracted):
- debtor_name: {details.debtor_name}
- loan_amount: {details.loan_amount}
- land_type: {details.land_type}
- mortgaged_property: {details.mortgaged_property}
- security_details: {details.security_details}
- registration_status: {details.registration_status}
- charge_status: {details.charge_status}
- no_of_charges: {details.no_of_charges}
- property_value: {details.property_value}
- ltv_ratio: {details.ltv_ratio}
- occupancy_type: {details.occupancy_type}
- title_disputes: {details.title_disputes}

Use this PDF evidence snippet:
\"\"\"{pdf_text[:3500]}\"\"\"

Rules:
- If charge/registration is "Satisfied" => registration/security risk should be LOW (0-20)
- If 0 charges => cersai_charges_risk should be near 0
- If multiple charges even if satisfied => small residual risk (10-35)
- Title disputes => title_quality_risk near 90-100
- Keep key_findings and recommendations to 4-6 items each.
""".strip()

    data = _genai_json(risk_client, RISK_MODEL, prompt)
    return RiskScore(**data)


# =========================
# 4) BLEND
# =========================
def blend_scores(det: Dict[str, Any], llm: RiskScore, w_det: float = 0.55, w_llm: float = 0.45) -> RiskScore:
    """
    Blend only the overall score; keep factor scores from LLM where available,
    but attach deterministic + llm overall for transparency.
    """
    det_overall = float(det["overall"])
    llm_overall = float(llm.overall_risk_score)

    blended = (w_det * det_overall) + (w_llm * llm_overall)
    blended = round(float(blended), 2)

    # risk level from blended score
    if blended >= 85:
        lvl = "DO_NOT_BUY"
    elif blended >= 60:
        lvl = "HIGH_RISK"
    elif blended >= 35:
        lvl = "PROCEED_WITH_CAUTION"
    else:
        lvl = "SAFE_TO_BUY"

    # Merge key findings (dedupe)
    merged_findings = []
    for x in (det.get("key_findings", []) + llm.key_findings):
        if x and x not in merged_findings:
            merged_findings.append(x)

    merged_recs = []
    for x in (det.get("recommendations", []) + llm.recommendations):
        if x and x not in merged_recs:
            merged_recs.append(x)

    # Build final RiskScore
    final = llm.model_copy(deep=True)
    final.overall_risk_score = blended
    final.risk_level = lvl

    # overwrite factors if LLM missed (rare)
    for k, v in det["factors"].items():
        if getattr(final, k, None) is None:
            setattr(final, k, float(v))

    final.key_findings = merged_findings[:6]
    final.recommendations = merged_recs[:6]

    final.deterministic_overall = det_overall
    final.llm_overall = llm_overall
    final.blend_weights = {"deterministic": w_det, "llm": w_llm}

    # add deterministic breakdown
    final.risk_factor_breakdown = final.risk_factor_breakdown or {}
    final.risk_factor_breakdown["deterministic_breakdown"] = det.get("breakdown", {})
    return final


# =========================
# MAIN WRAPPER
# =========================
def run_bankloan(pdf_path: str, out_path: str = DEFAULT_OUT, session_id: str = None, screenshot_dir: str = None) -> Dict[str, Any]:
    load_dotenv()
    extract_key, risk_key = _load_env_keys()

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Capture screenshot for report
    if screenshot_dir and session_id:
        import fitz
        from PIL import Image
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"bankloan_result_{session_id}.png")
        try:
            doc = fitz.open(pdf_path)
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(screenshot_path)
                print(f"DEBUG: Saved BANKLOAN screenshot to {screenshot_path}")
            doc.close()
        except Exception as e:
            print(f"DEBUG: Failed to save BANKLOAN screenshot: {e}")

    pdf_text = extract_pdf_text(pdf_path)

    extract_client = genai.Client(api_key=extract_key)
    risk_client = genai.Client(api_key=risk_key)

    loan_details = analyze_loan_with_llm_extract(extract_client, pdf_text)
    det = deterministic_score(loan_details)
    llm = llm_risk_score(risk_client, loan_details, pdf_text)
    final = blend_scores(det, llm)

    result = {
        "document_type": "BANK_LOAN",
        "models": {
            "extract": EXTRACTION_MODEL,
            "risk": RISK_MODEL,
        },
        "input": {
            "pdf_path": str(pdf_path),
        },
        "loan_details": loan_details.model_dump(),
        "risk": final.model_dump(),
    }

    _ensure_dirs(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="Path to CERSAI PDF")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output JSON path")
    args = ap.parse_args()

    res = run_bankloan(args.pdf, args.out)

    # Console summary (minimal)
    r = res["risk"]
    print("\n================================================================================")
    print("BANKLOAN RESULT")
    print("================================================================================")
    print(json.dumps(res, indent=2, ensure_ascii=False))

    print("\n--------------------------------------------------------------------------------")
    print(f"Overall Risk Score: {r['overall_risk_score']}/100 (0=SAFE, 100=DON'T BUY)")
    print(f"Recommendation: {r['risk_level']}")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
