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
from PIL import Image
import fitz
import os
import re
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pypdf import PdfReader

from anthropic import Anthropic


# =========================
# CONFIG
# =========================

DEFAULT_OUT = "output/bankloan_result.json"
EXTRACTION_MODEL = "qwen3:8b"
RISK_MODEL = "claude-opus-4-7"

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


def _load_env_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")

    return api_key

def _safe_json_load(text: str) -> Dict[str, Any]:
    # Trim code fences if any
    text = text.strip()
    text = re.sub(r"^\s*```json\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*```\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Try strict parse
    return json.loads(text)


def _claude_json(client, model: str, prompt: str) -> Dict[str, Any]:

    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    text = resp.content[0].text

    return _safe_json_load(text)

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
from openai import OpenAI

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

def analyze_loan_with_qwen(pdf_text: str) -> LoanDetails:
    prompt = f"""
# ROLE

You are a Senior CERSAI, Mortgage Registration, and Property Due Diligence Analyst
with expertise in Indian banking regulations, secured lending, and real estate
transactions.

# CONTEXT

You are analyzing an official CERSAI Search Report to help a prospective property
buyer determine whether the property has any existing secured loans,
mortgages, charges, or other security interests.

# TASK

Extract ONLY information that is explicitly present in the CERSAI report.

Do NOT infer, assume, calculate, or invent information.

Return ONLY valid JSON.

# IMPORTANT EXTRACTION RULES

1. Use the exact terminology used in the CERSAI report whenever possible.

2. Do NOT confuse different fields.

3. "Type Of Asset" or "Asset Category" describes the PROPERTY/ASSET TYPE.
   It does NOT describe occupancy.

4. "Satisfaction Status" describes whether the registered security interest/
   charge has been satisfied.

5. "Satisfaction Status" MUST NOT automatically be copied into
   "registration_status".

6. "registration_status" should ONLY be populated if the document explicitly
   contains a field describing registration status.

7. If the report contains "Satisfaction Status: Not Satisfied", extract:

   "charge_status": "Not Satisfied"

   and NOT:

   "registration_status": "Not Satisfied"

   unless the report separately and explicitly states a registration status.

8. "occupancy_type" means the actual occupancy of the property:
   - Owner Occupied
   - Tenant Occupied
   - Vacant

   Do NOT use:
   - Residential
   - Commercial
   - Agricultural
   - Industrial
   - Immovable

   as occupancy_type.

9. If the report does not explicitly state whether the property is
   owner-occupied, tenant-occupied, or vacant, return:

   "occupancy_type": null

10. "land_type" should represent the property/asset type explicitly stated
    in the document, such as Residential, Commercial, Agricultural,
    Industrial, etc.

11. "title_disputes" should ONLY be true if the document explicitly mentions
    a title dispute, litigation, dispute, or similar issue.

12. Do NOT infer title disputes merely because a mortgage or charge exists.

13. "no_of_charges" should represent the number of distinct security
    interests/charges shown in the report.

14. Do NOT count transaction history modifications as separate charges if
    they refer to the same Security Interest ID.

15. "loan_amount" should use the secured amount explicitly stated in the
    security-interest section.

16. "property_value" should ONLY be extracted if the report explicitly
    provides a property/asset value.

17. "ltv_ratio" should ONLY be extracted if the report explicitly provides
    an LTV or Loan-to-Value ratio.

18. "property_age_years" should ONLY be extracted if the report explicitly
    provides the property's age or enough explicit information to state it.
    Do NOT calculate age from construction dates unless the report explicitly
    provides the property age.

19. Missing information MUST be represented as null.

20. Never guess.

# FIELD DEFINITIONS

## debtor_name
Name of the debtor shown in the CERSAI report.

## loan_amount
Total secured amount associated with the security interest.
Use the exact amount from the report.

## land_type
Property/asset type explicitly stated in the report.

Examples:
- Residential
- Commercial
- Agricultural
- Industrial

This is NOT occupancy status.

## mortgaged_property
Description identifying the mortgaged/security-interest property.

Include relevant explicit identifiers such as:
- Bungalow
- Flat
- Survey Number
- Municipal Number
- Plot Number
- PID

## security_details
Details explicitly describing the security interest.

Include information such as:
- Type Of Security Interest
- Type Of Finance
- Details Of Charge
- Entity Identification Number

## registration_status
ONLY extract this if the CERSAI report explicitly contains a
REGISTRATION STATUS field.

Possible values:

- "Satisfied"
- "Not Satisfied"
- null

IMPORTANT:
Do NOT use "Satisfaction Status" as "registration_status".

If the report only says:

"Satisfaction Status: Not Satisfied"

then:

"registration_status": null

## property_value
Explicit property/asset value, if present.

Otherwise null.

## ltv_ratio
Explicit Loan-to-Value ratio, if present.

Otherwise null.

## no_of_charges
Number of DISTINCT security interests/charges.

Use Security Interest ID to distinguish separate security interests.

A transaction history entry such as "Modification" for the same
Security Interest ID is NOT another charge.

## charge_status
Extract the explicit "Satisfaction Status" of the security interest.

Possible values:

- "Satisfied"
- "Not Satisfied"
- null

For example:

"Satisfaction Status: Not Satisfied"

must produce:

"charge_status": "Not Satisfied"

## property_age_years
Explicit property age if stated.

Otherwise null.

## occupancy_type
ONLY actual occupancy status.

Allowed values:

- "Owner Occupied"
- "Tenant Occupied"
- "Vacant"
- null

"Residential" is NOT an occupancy type.

If the document says:

"Type Of Asset: Residential"

this must NOT be placed in occupancy_type.

## title_disputes
Boolean.

true ONLY if the document explicitly states a title dispute,
litigation, ownership dispute, or similar title-related dispute.

false ONLY if the document explicitly indicates that there is no such
dispute.

Otherwise:

null

# OUTPUT SCHEMA

Return exactly this JSON structure:

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
    "occupancy_type": "Owner Occupied|Tenant Occupied|Vacant|null",
    "title_disputes": "boolean|null"
}}

# CERSAI REPORT

\"\"\"{pdf_text[:22000]}\"\"\"

# FINAL VALIDATION

Before returning the JSON, verify:

- Residential is NOT placed in occupancy_type.
- Commercial is NOT placed in occupancy_type.
- Agricultural is NOT placed in occupancy_type.
- Immovable is NOT placed in occupancy_type.
- Satisfaction Status is placed in charge_status.
- Satisfaction Status is NOT automatically placed in registration_status.
- Transaction modifications for the same Security Interest ID are NOT
  counted as separate charges.
- Missing information is null.
- No field contains an inferred value.
- Return ONLY valid JSON.
"""

    try:
        response = qwen_client.chat.completions.create(
            model="qwen3:8b",
            messages=[
                {
                    "role": "system",
                    "content": "You are an information extraction engine. Return ONLY valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )

        data = json.loads(response.choices[0].message.content)

        # Normalize values
        data["registration_status"] = _normalize_status(
            data.get("registration_status")
        )
        data["charge_status"] = _normalize_status(
            data.get("charge_status")
        )

        if data.get("loan_amount") is not None:
            data["loan_amount"] = str(data["loan_amount"])

        if data.get("property_value") is not None:
            data["property_value"] = str(data["property_value"])

        filtered = {
            k: v
            for k, v in data.items()
            if k in LoanDetails.model_fields
        }

        return LoanDetails(**filtered)

    except Exception as e:
        raise RuntimeError(f"Loan extraction failed: {e}")

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
def llm_risk_score(client, details: LoanDetails, pdf_text: str) -> RiskScore:
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
                "Ask for lender NOC and Letter of Satisfaction.",
                "Re-check a fresh CERSAI report after clearance.",
                "Proceed only after an advocate confirms charge removal and clear title."
            ],
            risk_factor_breakdown={
                "charge_status": f"CRITICAL: {norm_status}",
                "buyer_rule": "Active charge => DO_NOT_BUY",
            },
        )

    prompt = f"""
# ROLE

You are a Senior Property Due Diligence Consultant, Banking Risk Analyst, and Real Estate Legal Advisor.

# CONTEXT

You are evaluating a CERSAI Search Report on behalf of a prospective property buyer.

Use ONLY the extracted information and document evidence provided.

Do NOT assume or invent facts.

# OBJECTIVE

Estimate the BUYER RISK associated with purchasing this property.

Risk Scale:

0 = Completely Safe

100 = Extremely Risky / Do Not Buy

# RISK EVALUATION FRAMEWORK

Evaluate the following:

1. Registration Status
2. Charge Status
3. Number of Charges
4. Security Interest
5. Land Type
6. Loan-to-Value (LTV)
7. Occupancy
8. Title Disputes

# BUYER DECISION RULES

Highest Priority
- Active Charge
- Registration Status = Not Satisfied
- Title Disputes

Moderate Priority
- Multiple Charges
- Industrial Land
- High LTV
- Tenant Occupied

Lower Priority
- Residential Land
- Satisfied Charges
- Owner Occupied

# IMPORTANT RULES

• Never penalize missing information.
• Missing information ≠ Risk.
• Use ONLY available evidence.
• Do NOT infer hidden facts.

If Registration Status = "Satisfied"
→ Registration Risk should normally be between 0 and 20.

If Charge Status = "Satisfied"
→ Security Risk should normally be between 0 and 20.

If Charge Status = "Not Satisfied"
→ Overall Risk should be extremely high.

If Title Disputes = true
→ Title Risk should be between 90 and 100.

If Number of Charges = 0
→ Charges Risk should be close to 0.

If Multiple Charges exist
→ Increase Charges Risk proportionally.

# EXTRACTED PROPERTY DETAILS

Debtor Name:
{details.debtor_name}

Loan Amount:
{details.loan_amount}

Land Type:
{details.land_type}

Mortgaged Property:
{details.mortgaged_property}

Security Details:
{details.security_details}

Registration Status:
{details.registration_status}

Charge Status:
{details.charge_status}

Number of Charges:
{details.no_of_charges}

Property Value:
{details.property_value}

LTV Ratio:
{details.ltv_ratio}

Occupancy:
{details.occupancy_type}

Title Disputes:
{details.title_disputes}

# DOCUMENT EVIDENCE

\"\"\"{pdf_text[:3500]}\"\"\"

# OUTPUT FORMAT

Return ONLY valid JSON.

{{
    "overall_risk_score": 0,
    "risk_level": "SAFE_TO_BUY",

    "land_type_risk": 0,
    "security_risk": 0,
    "registration_risk": 0,
    "ltv_risk": 0,
    "cersai_charges_risk": 0,
    "title_quality_risk": 0,
    "occupancy_risk": 0,

    "key_findings": [
        "...",
        "...",
        "..."
    ],

    "recommendations": [
        "...",
        "...",
        "..."
    ],

    "risk_factor_breakdown": {{}}
}}

# FINAL VALIDATION

Before returning:

- Every score must be between 0 and 100.
- Overall Risk must be consistent with individual risks.
- Risk Level must match Overall Risk.
- Findings must be supported by evidence.
- Recommendations must be practical.
- Return ONLY valid JSON.
""".strip()

    data = _claude_json(client, RISK_MODEL, prompt)

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


def create_bankloan_evidence_screenshot(
    pdf_path,
    output_path,
    dpi=220
):
    """
    Capture the page containing the CERSAI charge details.
    """

    keywords = [
        "charge",
        "satisfied",
        "not satisfied",
        "debtor",
        "secured creditor",
        "registration",
        "security interest",
        "property",
        "loan"
    ]

    doc = fitz.open(pdf_path)

    best_page = 0
    best_score = -1

    for page_no in range(len(doc)):

        text = doc[page_no].get_text().lower()

        score = sum(
            1
            for k in keywords
            if k in text
        )

        if score > best_score:
            best_score = score
            best_page = page_no

    page = doc.load_page(best_page)

    pix = page.get_pixmap(dpi=dpi)

    img = Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples
    )

    img.save(output_path)

    doc.close()

def create_bankloan_evidence_screenshot(
    pdf_path,
    output_path,
    dpi=220
):
    """
    Capture the page containing the CERSAI charge details.
    """

    keywords = [
        "charge",
        "satisfied",
        "not satisfied",
        "debtor",
        "secured creditor",
        "registration",
        "security interest",
        "property",
        "loan"
    ]

    doc = fitz.open(pdf_path)

    best_page = 0
    best_score = -1

    for page_no in range(len(doc)):

        text = doc[page_no].get_text().lower()

        score = sum(
            1
            for k in keywords
            if k in text
        )

        if score > best_score:
            best_score = score
            best_page = page_no

    page = doc.load_page(best_page)

    pix = page.get_pixmap(dpi=dpi)

    img = Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples
    )

    img.save(output_path)

    doc.close()
# =========================
# MAIN WRAPPER
# =========================
def print_qwen_extraction_debug(
    loan_details: LoanDetails,
    screenshot_path: Optional[str] = None
):
    print("\n" + "=" * 90)
    print("🔍 QWEN EXTRACTION RESULT — BANK LOAN / CERSAI")
    print("=" * 90)

    print("\n🤖 QWEN MODEL:")
    print(f"   {EXTRACTION_MODEL}")

    print("\n📦 EXTRACTED DATA:")
    print(json.dumps(
        loan_details.model_dump(),
        indent=2,
        ensure_ascii=False
    ))

    if screenshot_path:
        print("\n🖼️ EVIDENCE SCREENSHOT:")
        print(f"   {screenshot_path}")

    print("=" * 90 + "\n")

#def run_bankloan(pdf_path: str, out_path: str = DEFAULT_OUT, session_id: str = None, screenshot_dir: str = None) -> Dict[str, Any]:
#    load_dotenv()
#    api_key = _load_env_key()
def run_bankloan(
    pdf_path: str,
    out_path: str = DEFAULT_OUT,
    session_id: str = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:

    load_dotenv()

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Capture screenshot for report
    if screenshot_dir and session_id:

        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        screenshot_path = os.path.join(
            screenshot_dir,
            f"bankloan_result_{session_id}.png"
        )

        try:

            create_bankloan_evidence_screenshot(
                pdf_path,
                screenshot_path
            )

            print(
                f"Saved BANKLOAN evidence screenshot → {screenshot_path}"
            )

        except Exception as e:

            print(
                f"Failed to save BANKLOAN screenshot: {e}"
            )

    pdf_text = extract_pdf_text(pdf_path)
 #   client = Anthropic(api_key=api_key)
    try:
        # ============================================================
        # QWEN EXTRACTION
        # ============================================================
        loan_details = analyze_loan_with_qwen(pdf_text)

        # ============================================================
        # DEBUG: PRINT EXACTLY WHAT QWEN EXTRACTED
        # ============================================================
        print_qwen_extraction_debug(
            loan_details=loan_details,
            screenshot_path=(
                screenshot_path
                if screenshot_dir and session_id
                else None
            )
        )

        # ============================================================
        # SCORING
        # ============================================================
 #       det = deterministic_score(loan_details)
#      llm = llm_risk_score(client, loan_details, pdf_text)
#        final = blend_scores(det, llm)

    except Exception as e:
        return {
            "document_type": "BANK_LOAN",
            "status": "FAILED",
            "models": {
                "extract": EXTRACTION_MODEL,
                "risk": RISK_MODEL,
            },
            "input": {
                "pdf_path": str(pdf_path),
            },
            "loan_details": None,
            "risk": {
                "overall_risk_score": None,
                "risk_level": None,
            },
            "error": str(e),
        }

    result = {
        "document_type": "BANK_LOAN",
        "status": "QWEN_EXTRACTION_SUCCESS",
        "models": {
            "extract": EXTRACTION_MODEL,
            "risk": RISK_MODEL,
        },
        "input": {
            "pdf_path": str(pdf_path),
        },
        "loan_details": loan_details.model_dump(),
       # "risk": final.model_dump(),
    }

    _ensure_dirs(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 90)
    print("✅ QWEN EXTRACTION TEST COMPLETED")
    print("=" * 90)
    print(f"JSON saved: {out_path}")

    if screenshot_path:
        print(f"Screenshot: {screenshot_path}")

    print("=" * 90)

    return result

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--pdf",
        required=True,
        help="Path to CERSAI PDF"
    )

    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output JSON path"
    )

    ap.add_argument(
        "--session-id",
        default="debug",
        help="Session ID for screenshot"
    )

    ap.add_argument(
        "--screenshot-dir",
        default="screenshots",
        help="Directory for evidence screenshot"
    )

    args = ap.parse_args()

    res = run_bankloan(
        args.pdf,
        args.out,
        session_id=args.session_id,
        screenshot_dir=args.screenshot_dir
    )

    print("\n" + "=" * 90)
    print("BANK LOAN QWEN EXTRACTION RESULT")
    print("=" * 90)

    print(json.dumps(
        res,
        indent=2,
        ensure_ascii=False
    ))
if __name__ == "__main__":
    main()