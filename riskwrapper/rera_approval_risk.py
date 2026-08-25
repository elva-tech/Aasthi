#!/usr/bin/env python3
"""
# ARCHITECTURE:
# Claude is the ONLY external analysis API.
# There are NO separate BDA/BUDA/TUDA API endpoints.
# Python performs deterministic risk scoring after Claude analysis.
#
# NO BDA / BUDA / TUDA AUTHORITY API

Aasthi - RERA / BDA / BUDA / TUDA Approval Risk Scoring

Architecture:
    RERA extracted JSON
          |
          v
    Python project extraction
          |
          v
    Claude API analysis
          |
          v
    Evidence-based authority assessment
          |
          v
    Python deterministic risk scoring
          |
          v
    Final JSON report

IMPORTANT:
- No BDA API.
- No BUDA API.
- No TUDA API.
- No AUTHORITY_API_TIMEOUT.
- Only ANTHROPIC_API_KEY is used.
- Claude analyzes evidence; Python calculates the final score.
- Claude must NOT invent an approval or approval number.
- "Approving Authority: BDA" alone does NOT mean independent BDA
  approval is verified.

Install:
    pip install anthropic

Windows CMD:
    set ANTHROPIC_API_KEY=YOUR_CLAUDE_API_KEY

PowerShell:
    $env:ANTHROPIC_API_KEY="YOUR_CLAUDE_API_KEY"

Run:
    python rera_approval_risk.py "D:\\aasthiv2\\Aasthi\\wrappercode\\input\\additional detail\\Prestige_Lakeside_Habitat_rera_details.json"

Optional:
    python rera_approval_risk.py input.json --output output.json

Environment:
    ANTHROPIC_MODEL=claude-opus-4-7
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from anthropic import Anthropic
from google import genai

# ============================================================
# CLAUDE CONFIGURATION
# ============================================================

ANTHROPIC_API_KEY = os.getenv(
    "ANTHROPIC_API_KEY",
    ""
).strip()

ANTHROPIC_MODEL = os.getenv(
    "ANTHROPIC_MODEL",
    "claude-opus-4-7"
).strip()


# ============================================================
# HELPERS
# ============================================================

def clean(value: Any) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def normalize(value: Any) -> str:
    value = clean(value).lower()
    value = value.replace("&", "and")

    return re.sub(
        r"[^a-z0-9]+",
        "",
        value
    )


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Input JSON file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(
            "Input JSON root must be an object."
        )

    return data


def save_json(
    path: Path,
    data: Dict[str, Any]
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def extract_json_from_text(
    text: str
) -> Dict[str, Any]:

    text = text.strip()

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:
        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        candidate = text[
            start:end + 1
        ]

        data = json.loads(candidate)

        if isinstance(data, dict):
            return data

    raise ValueError(
        "Claude response did not contain valid JSON."
    )


# ============================================================
# RERA PROJECT EXTRACTION
# ============================================================

def extract_project_data(
    rera_data: Dict[str, Any]
) -> Dict[str, str]:

    registration = rera_data.get(
        "registration",
        {}
    )

    project_details = rera_data.get(
        "project_details",
        {}
    )

    if not isinstance(
        registration,
        dict
    ):
        registration = {}

    if not isinstance(
        project_details,
        dict
    ):
        project_details = {}

    return {

        "project_name": clean(
            project_details.get(
                "project_name"
            )
            or registration.get(
                "project_name"
            )
        ),

        "registration_number": clean(
            registration.get(
                "registration_number"
            )
        ),

        "acknowledgement_number": clean(
            registration.get(
                "acknowledgement_number"
            )
        ),

        "project_status": clean(
            project_details.get(
                "project_status"
            )
        ),

        "project_type": clean(
            project_details.get(
                "project_type"
            )
        ),

        "project_description": clean(
            project_details.get(
                "project_description"
            )
        ),

        "project_start_date": clean(
            project_details.get(
                "project_start_date"
            )
        ),

        "proposed_project_completion_date": clean(
            project_details.get(
                "proposed_project_completion_date"
            )
        ),

        "project_address": clean(
            project_details.get(
                "project_address"
            )
        ),

        "district": clean(
            project_details.get(
                "district"
            )
        ),

        "taluk": clean(
            project_details.get(
                "taluk"
            )
        ),

        "approving_authority": clean(
            project_details.get(
                "approving_authority"
            )
        ),

        "total_area_of_land_sq_m": clean(
            project_details.get(
                "total_area_of_land_sq_m"
            )
        ),

        "total_covered_area_sq_m": clean(
            project_details.get(
                "total_covered_area_sq_m"
            )
        ),

        "total_open_area_sq_m": clean(
            project_details.get(
                "total_open_area_sq_m"
            )
        ),

        "estimated_cost_of_construction_inr": clean(
            project_details.get(
                "estimated_cost_of_construction_inr"
            )
        ),

        "cost_of_land_inr": clean(
            project_details.get(
                "cost_of_land_inr"
            )
        ),

        "total_project_cost_inr": clean(
            project_details.get(
                "total_project_cost_inr"
            )
        ),

        "no_of_garage_for_sale": clean(
            project_details.get(
                "no_of_garage_for_sale"
            )
        ),

        "area_of_garage_for_sale_sq_m": clean(
            project_details.get(
                "area_of_garage_for_sale_sq_m"
            )
        ),

        "no_of_parking_for_sale": clean(
            project_details.get(
                "no_of_parking_for_sale"
            )
        ),

        "area_of_parking_for_sale_sq_m": clean(
            project_details.get(
                "area_of_parking_for_sale_sq_m"
            )
        ),
    }


# ============================================================
# AUTHORITY IDENTIFICATION
# ============================================================

def identify_authority(
    approving_authority: str
) -> Optional[str]:

    text = normalize(
        approving_authority
    )

    if (
        "bda" in text
        or "bangaloredevelopmentauthority" in text
        or "bengalurudevelopmentauthority" in text
    ):
        return "BDA"

    if (
        "buda" in text
        or "belgaumurbandevelopmentauthority" in text
        or "belagaviurbandevelopmentauthority" in text
    ):
        return "BUDA"

    if (
        "tuda" in text
        or "tumakuruurbandevelopmentauthority" in text
        or "tumkururbandevelopmentauthority" in text
    ):
        return "TUDA"

    return None


# ============================================================
# CLAUDE PROMPT
# ============================================================

AUTHORITY_VERIFICATION_SYSTEM_PROMPT = """
You are the document-analysis component of Aasthi, a property
due-diligence system for Karnataka property transactions.

Your task is to analyze ONLY the supplied Karnataka RERA project JSON
and assess the approval/authority information contained in that data.

The authority may be:
- BDA - Bangalore Development Authority
- BUDA - Belagavi Urban Development Authority
- TUDA - Tumakuru Urban Development Authority
- another planning/development authority.

CRITICAL RULES:

1. Use ONLY information present in the supplied input.
2. Do NOT use general knowledge to invent an approval.
3. Do NOT assume that because an authority is listed in the RERA
   record, the project is independently approved by that authority.
4. Clearly distinguish:
   - authority listed in RERA
   - actual approval evidence present
   - approval reference/number present
   - approval document present
   - approval status
5. If the record only says:
      "Approving Authority: BDA - Bangalore Development Authority"
   then authority_listed_in_rera must be true, but
   independent_approval_verified must be false unless actual approval
   evidence is also present.
6. Search the COMPLETE supplied JSON, including:
   - registration
   - project_details
   - development_details
   - external_development_work
   - project_bank_escrow
   - project_architects
   - structural_engineers
   - project_contractors
   - uploaded/enquired document information if present
   - raw page text if present
7. Do NOT treat these as authority approval numbers unless the input
   explicitly identifies them as such:
   - RERA registration number
   - acknowledgement number
   - PAN
   - bank account number
   - architect registration number
   - structural engineer licence number
8. A valid authority approval may be represented by an explicit
   approval/order/layout/building-plan/sanction/licence reference
   or an explicitly named approval document.
9. If evidence is ambiguous, return PARTIALLY_VERIFIED.
10. If authority is merely listed but there is no approval evidence,
    return UNVERIFIED.
11. If explicit evidence says rejected/revoked/cancelled/suspended/
    expired, return FAILED.
12. Calculate an independent RISK score from 0 to 100.
13. 0 = no risk, 100 = very high risk.
14. Base the risk score ONLY on the supplied RERA project information
    and authority-verification evidence.
15. Do not use the Python rule score to calculate your risk_score.
16. Return ONLY valid JSON. No markdown. No code fences.

Return exactly:

{
  "authority": "",
  "authority_listed_in_rera": false,
  "verification_status": "VERIFIED|PARTIALLY_VERIFIED|UNVERIFIED|FAILED",

  "approval_found": false,
  "independent_approval_verified": false,

  "approval_status": "",
  "approval_number": "",
  "approval_document": "",

  "project_name": "",
  "project_name_match": null,

  "project_address": "",
  "location_match": null,

  "evidence": [],
  "missing_information": [],
  "risk_observations": [],
  "risk_score": 0,
  "confidence": 0.0
}

FIELD RULES:

authority:
    Exact authority identified from supplied data.

authority_listed_in_rera:
    true only when an approving authority is explicitly present.

verification_status:
    VERIFIED:
        Explicit approval evidence and sufficient identifying information
        are present.

    PARTIALLY_VERIFIED:
        Some approval information exists but evidence is incomplete or
        ambiguous.

    UNVERIFIED:
        Authority may be listed but independent approval evidence is
        absent.

    FAILED:
        Explicit evidence indicates adverse approval status.

approval_found:
    true only if an actual approval record or explicit approval evidence
    is found.

independent_approval_verified:
    true only when supplied data contains actual evidence supporting
    approval by the authority.

approval_status:
    Exact status if explicitly available.

approval_number:
    Authority approval/order/layout/building-plan reference only.
    Never use the RERA registration number.

approval_document:
    Explicit approval document name if available.

project_name_match:
    Compare approval project name with RERA project name.
    Use null if comparison is not possible.

location_match:
    Compare approval/project location if sufficient information exists.
    Use null if comparison is not possible.

evidence:
    Short factual statements based only on supplied data.

missing_information:
    Information needed for stronger verification.

risk_observations:
    Factual observations relevant to due diligence.

confidence:
    Number between 0.0 and 1.0.
"""


def build_authority_prompt(
    authority: str,
    project: Dict[str, str],
    rera_data: Dict[str, Any]
) -> str:

    return f"""
Analyze the following Karnataka RERA project for {authority}
approval verification.

TARGET AUTHORITY:
{authority}

EXTRACTED PROJECT INFORMATION:
{json.dumps(project, indent=2, ensure_ascii=False)}

COMPLETE RERA JSON:
{json.dumps(rera_data, indent=2, ensure_ascii=False)}

Determine whether the supplied RERA data contains actual evidence
supporting approval by {authority}.

Do not assume approval merely because {authority} is listed as the
approving authority.

Do not invent an approval number.

Do not use the RERA registration number as the authority approval
number.

If no actual authority approval evidence is present, return
UNVERIFIED.

Return ONLY the required JSON.
"""


# ============================================================
# CLAUDE CALL
# ============================================================

def call_authority_claude(
    authority: str,
    project: Dict[str, str],
    rera_data: Dict[str, Any]
) -> Dict[str, Any]:

    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured."
        )

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is not installed. "
            "Run: pip install anthropic"
        ) from exc

    client = Anthropic(
        api_key=ANTHROPIC_API_KEY
    )

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=AUTHORITY_VERIFICATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_authority_prompt(
                    authority,
                    project,
                    rera_data
                )
            }
        ]
    )

    text_parts = []

    for block in response.content:
        if getattr(
            block,
            "type",
            None
        ) == "text":
            text_parts.append(
                block.text
            )

    response_text = "\n".join(
        text_parts
    ).strip()

    if not response_text:
        raise RuntimeError(
            "Claude returned an empty response."
        )

    result = extract_json_from_text(
        response_text
    )

    return validate_claude_result(
        result
    )


# ============================================================
# CLAUDE RESULT VALIDATION
# ============================================================

def validate_claude_result(
    result: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(
        result,
        dict
    ):
        raise ValueError(
            "LLM result is not an object."
        )

    bool_fields = [
        "authority_listed_in_rera",
        "approval_found",
        "independent_approval_verified",
    ]

    for field in bool_fields:
        if not isinstance(
            result.get(field),
            bool
        ):
            result[field] = bool(
                result.get(field)
            )

    nullable_bool_fields = [
        "project_name_match",
        "location_match",
    ]

    for field in nullable_bool_fields:
        value = result.get(field)

        if value not in (
            True,
            False,
            None
        ):
            result[field] = None

    for field in [
        "evidence",
        "missing_information",
        "risk_observations",
    ]:

        if not isinstance(
            result.get(field),
            list
        ):
            result[field] = []

    # --------------------------------------------------------
    # LLM RISK SCORE
    # Gemini/Claude must return a numeric score from 0-100
    # --------------------------------------------------------

    try:
        risk_score = float(
            result.get(
                "risk_score",
                0
            )
        )
    except (
        TypeError,
        ValueError
    ):
        risk_score = 0.0

    result["risk_score"] = max(
        0.0,
        min(
            100.0,
            risk_score
        )
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    try:
        confidence = float(
            result.get(
                "confidence",
                0
            )
        )
    except (
        TypeError,
        ValueError
    ):
        confidence = 0.0

    result["confidence"] = max(
        0.0,
        min(
            1.0,
            confidence
        )
    )

    # --------------------------------------------------------
    # TEXT FIELDS
    # --------------------------------------------------------

    result["authority"] = clean(
        result.get(
            "authority"
        )
    )

    result["verification_status"] = clean(
        result.get(
            "verification_status"
        )
    ).upper()

    result["approval_status"] = clean(
        result.get(
            "approval_status"
        )
    )

    result["approval_number"] = clean(
        result.get(
            "approval_number"
        )
    )

    result["approval_document"] = clean(
        result.get(
            "approval_document"
        )
    )

    return result


# ============================================================
# PYTHON RULES
# ============================================================

def rule_rera_registration(
    project: Dict[str, str]
) -> Dict[str, Any]:

    if project[
        "registration_number"
    ]:

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 20,
            "message":
                "RERA registration number is present."
        }

    return {
        "status": "FAIL",
        "risk": 20,
        "max_risk": 20,
        "message":
            "RERA registration number is missing."
    }


def rule_rera_format(
    project: Dict[str, str]
) -> Dict[str, Any]:

    number = project[
        "registration_number"
    ]

    if not number:

        return {
            "status": "NOT_CHECKED",
            "risk": 0,
            "max_risk": 5,
            "message":
                "No RERA registration number to validate."
        }

    upper = number.upper()

    if (
        "RERA" in upper
        and "KA" in upper
    ):

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 5,
            "message":
                "Registration number has a recognizable Karnataka RERA format."
        }

    return {
        "status": "WARNING",
        "risk": 5,
        "max_risk": 5,
        "message":
            "Registration number is present but its Karnataka RERA "
            "format could not be recognized."
    }


def rule_project_name(
    project: Dict[str, str]
) -> Dict[str, Any]:

    if project[
        "project_name"
    ]:

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 5,
            "message":
                "Project name is present."
        }

    return {
        "status": "FAIL",
        "risk": 5,
        "max_risk": 5,
        "message":
            "Project name is missing."
    }


def rule_project_status(
    project: Dict[str, str]
) -> Dict[str, Any]:

    status = normalize(
        project[
            "project_status"
        ]
    )

    adverse = {
        "revoked",
        "revocation",
        "cancelled",
        "canceled",
        "suspended",
        "rejected",
        "withdrawn",
        "expired",
    }

    normal = {
        "registered",
        "approved",
        "ongoing",
        "completed",
        "active",
        "underconstruction",
    }

    if status in adverse:

        return {
            "status": "FAIL",
            "risk": 15,
            "max_risk": 15,
            "message":
                f"Adverse project status: "
                f"{project['project_status']}."
        }

    if status in normal:

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 15,
            "message":
                f"Project status is "
                f"{project['project_status']}."
        }

    return {
        "status": "UNKNOWN",
        "risk": 7,
        "max_risk": 15,
        "message":
            "Project status is missing or could not be classified."
    }


def rule_location(
    project: Dict[str, str]
) -> Dict[str, Any]:

    address = bool(
        project[
            "project_address"
        ]
    )

    district = bool(
        project[
            "district"
        ]
    )

    taluk = bool(
        project[
            "taluk"
        ]
    )

    count = sum([
        address,
        district,
        taluk
    ])

    if count == 3:

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 5,
            "message":
                "Project address, district and taluk are present."
        }

    if count > 0:

        return {
            "status": "PARTIAL",
            "risk": 3,
            "max_risk": 5,
            "message":
                "Some project location information is present."
        }

    return {
        "status": "FAIL",
        "risk": 5,
        "max_risk": 5,
        "message":
            "Project location information is missing."
    }


def rule_approving_authority(
    project: Dict[str, str]
) -> Dict[str, Any]:

    authority_text = project[
        "approving_authority"
    ]

    if not authority_text:

        return {
            "status": "FAIL",
            "risk": 15,
            "max_risk": 15,
            "authority": None,
            "message":
                "Approving authority is missing."
        }

    authority = identify_authority(
        authority_text
    )

    if authority:

        return {
            "status": "IDENTIFIED",
            "risk": 0,
            "max_risk": 15,
            "authority": authority,
            "message":
                f"{authority} is listed as the approving authority."
        }

    return {
        "status": "UNKNOWN",
        "risk": 7,
        "max_risk": 15,
        "authority": None,
        "message":
            f"Approving authority '{authority_text}' could not "
            "be mapped to BDA, BUDA or TUDA."
    }


def rule_authority_claude(
    claude_result: Dict[str, Any]
) -> Dict[str, Any]:

    status = claude_result.get(
        "verification_status",
        "UNVERIFIED"
    )

    approval_found = claude_result.get(
        "approval_found"
    )

    independently_verified = claude_result.get(
        "independent_approval_verified"
    )

    project_match = claude_result.get(
        "project_name_match"
    )

    location_match = claude_result.get(
        "location_match"
    )

    # Explicit adverse result.
    if status == "FAILED":

        return {
            "status": "FAILED",
            "risk": 30,
            "max_risk": 30,
            "message":
                "Claude found explicit adverse approval evidence.",
            "evidence":
                claude_result.get(
                    "evidence",
                    []
                )
        }

    # Fully verified.
    if (
        status == "VERIFIED"
        and approval_found is True
        and independently_verified is True
    ):

        risk = 0

        if project_match is False:
            risk += 10

        if location_match is False:
            risk += 10

        return {
            "status": "VERIFIED",
            "risk": min(
                risk,
                30
            ),
            "max_risk": 30,
            "message":
                "Actual authority approval evidence was identified.",
            "evidence":
                claude_result.get(
                    "evidence",
                    []
                )
        }

    # Approval evidence exists but verification is incomplete.
    if (
        status == "PARTIALLY_VERIFIED"
        or approval_found is True
    ):

        risk = 15

        if project_match is False:
            risk += 5

        if location_match is False:
            risk += 5

        return {
            "status": "PARTIALLY_VERIFIED",
            "risk": min(
                risk,
                30
            ),
            "max_risk": 30,
            "message":
                "Some authority approval information exists, "
                "but independent verification is incomplete.",
            "evidence":
                claude_result.get(
                    "evidence",
                    []
                )
        }

    # Authority listed but no approval evidence.
    return {
        "status": "UNVERIFIED",
        "risk": 20,
        "max_risk": 30,
        "message":
            "Authority is listed, but independent approval evidence "
            "was not found in the supplied RERA data.",
        "evidence":
            claude_result.get(
                "evidence",
                []
            )
    }


def rule_claude_consistency(
    claude_result: Dict[str, Any]
) -> Dict[str, Any]:

    observations = claude_result.get(
        "risk_observations",
        []
    )

    if not observations:

        return {
            "status": "PASS",
            "risk": 0,
            "max_risk": 5,
            "message":
                "No additional authority/project risk observations "
                "were identified."
        }

    return {
        "status": "WARNING",
        "risk": 5,
        "max_risk": 5,
        "message":
            "Claude identified additional due-diligence observations.",
        "observations":
            observations
    }


# ============================================================
# FINAL SCORE
# ============================================================

def calculate_risk(
    project: Dict[str, str],
    claude_result: Dict[str, Any]
) -> Dict[str, Any]:

    checks = {

        "rera_registration":
            rule_rera_registration(
                project
            ),

        "rera_registration_format":
            rule_rera_format(
                project
            ),

        "project_name":
            rule_project_name(
                project
            ),

        "project_status":
            rule_project_status(
                project
            ),

        "location":
            rule_location(
                project
            ),

        "approving_authority":
            rule_approving_authority(
                project
            ),

        "authority_approval_verification":
            rule_authority_claude(
                claude_result
            ),

        "claude_consistency":
            rule_claude_consistency(
                claude_result
            ),
    }

    total_risk = sum(
        int(
            check.get(
                "risk",
                0
            )
        )
        for check in checks.values()
    )

    max_risk = sum(
        int(
            check.get(
                "max_risk",
                0
            )
        )
        for check in checks.values()
    )

    risk_score = round(
        (
            total_risk
            /
            max_risk
        ) * 100,
        2
    ) if max_risk else 100.0

    risk_score = max(
        0.0,
        min(
            100.0,
            risk_score
        )
    )

    if risk_score <= 20:
        risk_level = "LOW"
    elif risk_score <= 40:
        risk_level = "MODERATE"
    elif risk_score <= 70:
        risk_level = "HIGH"
    else:
        risk_level = "VERY HIGH"

    risk_reasons = []

    for name, check in checks.items():

        if int(
            check.get(
                "risk",
                0
            )
        ) > 0:

            risk_reasons.append({
                "check": name,
                "risk": check.get(
                    "risk",
                    0
                ),
                "status": check.get(
                    "status"
                ),
                "reason": check.get(
                    "message"
                )
            })

    return {
        "risk": risk_score,
        "risk_level": risk_level,
        "checks": checks,
        "risk_reasons": risk_reasons,
        "total_rule_risk": total_risk,
        "maximum_rule_risk": max_risk,
    }


# ============================================================
# MAIN PIPELINE
# ============================================================

def run(
    input_json: str,
    output_json: Optional[str] = None
) -> Dict[str, Any]:

    input_path = Path(
        input_json
    )

    print("=" * 75)
    print(
        "AASTHI - RERA / BDA / BUDA / TUDA "
        "APPROVAL RISK"
    )
    print("=" * 75)

    # --------------------------------------------------------
    # 1. Load RERA JSON
    # --------------------------------------------------------

    rera_data = load_json(
        input_path
    )

    project = extract_project_data(
        rera_data
    )

    authority = identify_authority(
        project[
            "approving_authority"
        ]
    )

    print(
        f"Input              : {input_path}"
    )

    print(
        f"Project            : "
        f"{project['project_name'] or 'N/A'}"
    )

    print(
        f"RERA Number        : "
        f"{project['registration_number'] or 'N/A'}"
    )

    print(
        f"Status             : "
        f"{project['project_status'] or 'N/A'}"
    )

    print(
        f"District           : "
        f"{project['district'] or 'N/A'}"
    )

    print(
        f"Taluk              : "
        f"{project['taluk'] or 'N/A'}"
    )

    print(
        f"Approving Authority: "
        f"{project['approving_authority'] or 'N/A'}"
    )

    print(
        f"Detected Authority : "
        f"{authority or 'UNKNOWN'}"
    )

    # --------------------------------------------------------
    # 2. Claude authority analysis
    # --------------------------------------------------------

    if authority:

        print()
        print(
            f"Calling Claude for {authority} analysis..."
        )

        try:

            claude_result = call_authority_claude(
                authority=authority,
                project=project,
                rera_data=rera_data
            )

            claude_error = None

            print(
                "Claude analysis: SUCCESS"
            )

        except Exception as exc:

            claude_error = str(
                exc
            )

            print(
                f"Claude analysis: ERROR - {claude_error}"
            )

            # Safe fallback.
            claude_result = {
                "authority":
                    authority,

                "authority_listed_in_rera":
                    True,

                "verification_status":
                    "UNVERIFIED",

                "approval_found":
                    False,

                "independent_approval_verified":
                    False,

                "approval_status":
                    "",

                "approval_number":
                    "",

                "approval_document":
                    "",

                "project_name":
                    project[
                        "project_name"
                    ],

                "project_name_match":
                    None,

                "project_address":
                    project[
                        "project_address"
                    ],

                "location_match":
                    None,

                "evidence":
                    [],

                "missing_information":
                    [
                        "Claude verification failed."
                    ],

                "risk_observations":
                    [
                        "Independent authority approval "
                        "could not be verified."
                    ],

                "confidence":
                    0.0,

                "error":
                    claude_error
            }

    else:

        claude_error = None

        claude_result = {
            "authority":
                project[
                    "approving_authority"
                ],

            "authority_listed_in_rera":
                bool(
                    project[
                        "approving_authority"
                    ]
                ),

            "verification_status":
                "UNVERIFIED",

            "approval_found":
                False,

            "independent_approval_verified":
                False,

            "approval_status":
                "",

            "approval_number":
                "",

            "approval_document":
                "",

            "project_name":
                project[
                    "project_name"
                ],

            "project_name_match":
                None,

            "project_address":
                project[
                    "project_address"
                ],

            "location_match":
                None,

            "evidence":
                [],

            "missing_information":
                [
                    "Supported planning authority "
                    "could not be identified."
                ],

            "risk_observations":
                [
                    "Approving authority is missing or "
                    "not recognized as BDA, BUDA or TUDA."
                ],

            "confidence":
                0.0
        }

    # --------------------------------------------------------
    # 3. Python scoring
    # --------------------------------------------------------

    print()
    print(
        "Applying Python rule-based scoring..."
    )

    risk_result = calculate_risk(
        project,
        claude_result
    )
    # --------------------------------------------------------
    # 3A. LLM + Python weighted final risk
    # --------------------------------------------------------

    rule_risk_score = float(
        risk_result["risk"]
    )

    llm_risk_score = float(
        claude_result.get(
            "risk_score",
            0
        )
    )

    rule_weight = 0.60
    llm_weight = 0.40

    final_risk_score = round(
        (
            rule_risk_score * rule_weight
        )
        +
        (
            llm_risk_score * llm_weight
        ),
        2
    )

    final_risk_score = max(
        0.0,
        min(
            100.0,
            final_risk_score
        )
    )

    if final_risk_score <= 20:
        final_risk_level = "LOW"
    elif final_risk_score <= 40:
        final_risk_level = "MODERATE"
    elif final_risk_score <= 70:
        final_risk_level = "HIGH"
    else:
        final_risk_level = "VERY HIGH"
    # --------------------------------------------------------
    # 4. Final report
    # --------------------------------------------------------

    authority_check = risk_result[
        "checks"
    ][
        "authority_approval_verification"
    ]

    verification_status = (
        authority_check[
            "status"
        ]
    )

    if output_json:

        output_path = Path(
            output_json
        )

    else:

        output_path = (
            input_path.parent
            /
            f"{input_path.stem}_risk.json"
        )

    result = {

        "module":
            "rera_bda_buda_tuda_approval",

        "risk": final_risk_score,

        "risk_level": final_risk_level,

        "score_breakdown": {
            "rule_based_risk_score": rule_risk_score,
            "rule_based_weight": 0.60,

            "llm_risk_score": llm_risk_score,
            "llm_weight": 0.40,

            "final_risk_score": final_risk_score,

            "formula": (
                "(rule_based_risk_score × 0.60) + "
                "(llm_risk_score × 0.40)"
            )
        },

        "verification_status":
            verification_status,

        "project":
            project,

        "authority":
            {

                "detected":
                    authority,

                "rera_approving_authority":
                    project[
                        "approving_authority"
                    ],

                "claude_verification":
                    claude_result,

                "verification_summary":
                    authority_check[
                        "message"
                    ]
            },

        "checks":
            risk_result[
                "checks"
            ],

        "score_breakdown":
            {

                "total_rule_risk":
                    risk_result[
                        "total_rule_risk"
                    ],

                "maximum_rule_risk":
                    risk_result[
                        "maximum_rule_risk"
                    ],

                "risk_percentage":
                    risk_result[
                        "risk"
                    ]
            },

        "risk_reasons":
            risk_result[
                "risk_reasons"
            ],

        "_meta":
            {

                "source":
                    "Karnataka RERA extracted JSON",

                "input_file":
                    str(
                        input_path
                    ),

                "scoring_method":
                    "Claude evidence analysis + "
                    "Python deterministic rules",

                "claude_model":
                    ANTHROPIC_MODEL,

                "authority_apis_used":
                    False,

                "anthropic_api_used":
                    True,

                "claude_error":
                    claude_error,

                "generated_at":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            }
    }

    save_json(
        output_path,
        result
    )

    # --------------------------------------------------------
    # 5. Console output
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print("FINAL RESULT")
    print("=" * 75)

    print(
        f"Risk Score          : "
        f"{result['risk']}/100"
    )

    print(
        f"Risk Level          : "
        f"{result['risk_level']}"
    )

    print(
        f"Authority           : "
        f"{authority or 'UNKNOWN'}"
    )

    print(
        f"Verification        : "
        f"{verification_status}"
    )

    print(
        "Authority APIs      : NOT USED"
    )

    print(
        "Claude API          : USED"
    )

    print(
        f"Output              : "
        f"{output_path}"
    )

    print("=" * 75)

    return result


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Aasthi RERA/BDA/BUDA/TUDA approval "
            "risk scoring using Claude + Python."
        )
    )

    parser.add_argument(
        "input_json",
        help="Path to RERA extracted JSON."
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path."
    )

    args = parser.parse_args()

    run(
        input_json=args.input_json,
        output_json=args.output
    )


if __name__ == "__main__":
    main()