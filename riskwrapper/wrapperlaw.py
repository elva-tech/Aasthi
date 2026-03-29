# bylaws_wrapper.py
"""
Bylaws Risk Wrapper (Gemini 2.5 Flash + google.genai)
Safety score = low risk (0..100, higher is safer)
Also outputs: risk_score = 100 - safety_score (higher is riskier)
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple, Optional


# -----------------------------
# 1) Extraction schema prompt
# -----------------------------
EXTRACTION_PROMPT = """Return STRICT JSON ONLY. No markdown. No explanation.

You are an information extraction engine.
Extract facts ONLY from the provided text. Do not guess.
Use true/false; if not found, use false.
For any field that is “present”, set true only if the text explicitly indicates it.

Schema: AssociationComplianceExtract with these keys:
property{city,state}
formation{entity_type,is_registered,registration_number_present,registration_date_present}
declaration_deed{dod_present,dod_registered,dod_date_present}
bylaws{bylaws_present,bylaws_registered_or_filed,mentions_kaoa_act_or_rules,core_sections_present{membership,governance_committee,meetings_quorum_voting,maintenance_charges,funds_audit_accounts,penalties_dispute_resolution,amendment_process}}
governance{agm_required,agm_frequency_yearly,elections_defined,minutes_and_records_access}
financials{audit_required,audit_frequency_yearly,corpus_or_sinking_fund_mentioned,collection_enforcement_defined}
property_compliance{insurance_mentioned,fire_safety_compliance_mentioned,common_areas_transfer_mentioned,litigation_or_disputes_mentioned}
confidence (0 to 1)
notes (array of strings)
"""


# --------------------------------------------------------
# 2) Robust JSON extraction (handles fences & extra text)
# --------------------------------------------------------
def extract_json_object(raw: str) -> Dict[str, Any]:
    """
    Extract first JSON object from a string.
    Handles code fences and leading/trailing text.
    Raises ValueError if no JSON object found.
    """
    cleaned = (raw or "").strip()

    # Strip common code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object start '{' found in LLM output.")

    brace_count = 0
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                candidate = cleaned[start: i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise ValueError(f"JSON decode failed: {e}") from e

    raise ValueError("Could not find a complete JSON object in LLM output.")


# -----------------------------
# 3) Scoring
# -----------------------------
def bool_score(flag: bool, pts: int) -> int:
    return pts if bool(flag) else 0


def compute_association_risk_score(extract: Dict[str, Any]) -> Tuple[int, str, Dict[str, Any]]:
    """
    Score out of 100. High score = low risk (safer).
    Returns: (total_score, risk_level, breakdown)
    """

    def g(path: List[str], default=False):
        cur: Any = extract
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    # Dimension 1: Legal formation & registration (25)
    legal = 0
    legal += bool_score(g(["formation", "is_registered"]), 10)
    legal += bool_score(g(["formation", "registration_number_present"]), 7)
    legal += bool_score(g(["formation", "registration_date_present"]), 3)
    legal += bool_score(g(["declaration_deed", "dod_present"]), 2)
    legal += bool_score(g(["declaration_deed", "dod_registered"]), 3)
    legal = min(25, legal)

    # Dimension 2: Bye-laws quality & coverage (15)
    bylaws = 0
    bylaws += bool_score(g(["bylaws", "bylaws_present"]), 4)
    bylaws += bool_score(g(["bylaws", "bylaws_registered_or_filed"]), 3)
    bylaws += bool_score(g(["bylaws", "mentions_kaoa_act_or_rules"]), 2)

    core = g(["bylaws", "core_sections_present"], default={})
    if not isinstance(core, dict):
        core = {}

    core_checks = [
        "membership",
        "governance_committee",
        "meetings_quorum_voting",
        "maintenance_charges",
        "funds_audit_accounts",
        "penalties_dispute_resolution",
        "amendment_process",
    ]
    core_true = sum(1 for k in core_checks if core.get(k) is True)
    bylaws += round(6 * (core_true / len(core_checks)))  # 0..6
    bylaws = min(15, bylaws)

    # Dimension 3: Governance & transparency (15)
    gov = 0
    gov += bool_score(g(["governance", "agm_required"]), 3)
    gov += bool_score(g(["governance", "agm_frequency_yearly"]), 4)
    gov += bool_score(g(["governance", "elections_defined"]), 4)
    gov += bool_score(g(["governance", "minutes_and_records_access"]), 4)
    gov = min(15, gov)

    # Dimension 4: Financial discipline (20)
    fin = 0
    fin += bool_score(g(["financials", "audit_required"]), 6)
    fin += bool_score(g(["financials", "audit_frequency_yearly"]), 6)
    fin += bool_score(g(["financials", "corpus_or_sinking_fund_mentioned"]), 4)
    fin += bool_score(g(["financials", "collection_enforcement_defined"]), 4)
    fin = min(20, fin)

    # Dimension 5: Property compliance health (10)
    comp = 0
    comp += bool_score(g(["property_compliance", "insurance_mentioned"]), 3)
    comp += bool_score(g(["property_compliance", "fire_safety_compliance_mentioned"]), 2)
    comp += bool_score(g(["property_compliance", "common_areas_transfer_mentioned"]), 3)
    disputes = g(["property_compliance", "litigation_or_disputes_mentioned"])
    comp += 2 if disputes is False else 0
    comp = min(10, comp)

    # Dimension 6: Evidence confidence (15)
    conf = g(["confidence"], default=0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    confidence_pts = round(15 * conf)

    total = legal + bylaws + gov + fin + comp + confidence_pts
    total = max(0, min(100, total))

    if total >= 85:
        level = "LOW"
    elif total >= 70:
        level = "MEDIUM-LOW"
    elif total >= 55:
        level = "MEDIUM"
    elif total >= 40:
        level = "HIGH"
    else:
        level = "VERY HIGH"

    breakdown = {
        "dimension_scores": {
            "legal_formation_registration": {"score": legal, "max": 25},
            "bylaws_coverage_quality": {"score": bylaws, "max": 15},
            "governance_transparency": {"score": gov, "max": 15},
            "financial_discipline": {"score": fin, "max": 20},
            "property_compliance": {"score": comp, "max": 10},
            "evidence_confidence": {"score": confidence_pts, "max": 15},
        },
        "notes": extract.get("notes", []),
    }

    return total, level, breakdown


# -----------------------------
# ✅ NEW: Risk score helper
# -----------------------------
def risk_score_from_safety(score: Any) -> Optional[int]:
    """
    Convert safety score (higher safer) to risk score (higher riskier):
    risk_score = 100 - safety_score
    """
    try:
        s = int(float(score))
    except Exception:
        return None
    s = max(0, min(100, s))
    return 100 - s


# -----------------------------
# 5) Gemini 2.5 Flash call (NEW SDK)
# -----------------------------
def call_gemini(prompt: str, text: str) -> str:
    """
    Gemini 2.5 Flash using NEW google.genai SDK
    pip install google-genai
    Requires env var: GEMINI_BYLAW
    """
    api_key = os.getenv("GEMINI_BYLAW")
    if not api_key:
        raise RuntimeError("Missing GEMINI_BYLAW environment variable.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError("Install: pip install google-genai") from e

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt + "\n\n---DOCUMENT TEXT---\n\n" + text,
        config=types.GenerateContentConfig(
            temperature=0,
            top_p=0.1,
            max_output_tokens=4096,
        ),
    )

    return response.text or ""


# -----------------------------
# IO helpers
# -----------------------------
def read_input_text(path: Optional[str]) -> str:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


# ============================================================
# WRAPPER (NEW)
# ============================================================
def run_bylaws_wrapper(
    text: Optional[str] = None,
    input_path: Optional[str] = None,
    extracted_json_path: Optional[str] = None,
    out_prefix: str = "assoc_extract",
    save_artifacts: bool = False
) -> Dict[str, Any]:
    """
    Wrapper:
    - If extracted_json_path is provided: skip Gemini, score that JSON.
    - Else: read text (from text or input_path), call Gemini, parse JSON, score.

    Returns:
    {
      "document_type": "BYLAWS",
      "raw_output": str | None,
      "extract": dict,
      "score": int,                 # safety score (higher safer)
      "risk_score": int,            # ✅ 100 - score (higher riskier)
      "risk_level": str,
      "breakdown": dict,
      "artifacts": { ...paths... } | None
    }
    """
    artifacts = None

    # Case 1: user already has extracted JSON
    if extracted_json_path:
        extract = load_json(extracted_json_path)
        score, level, breakdown = compute_association_risk_score(extract)
        return {
            "document_type": "BYLAWS",
            "raw_output": None,
            "extract": extract,
            "score": score,
            "risk_score": risk_score_from_safety(score),  # ✅
            "risk_level": level,
            "breakdown": breakdown,
            "artifacts": None
        }

    # Case 2: need to run Gemini extraction
    if text is None:
        text = read_input_text(input_path).strip()
    else:
        text = (text or "").strip()

    if not text:
        raise ValueError("No input text provided. Provide text=... or input_path=...")

    raw = call_gemini(EXTRACTION_PROMPT, text)

    if save_artifacts:
        raw_path = f"{out_prefix}.raw.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw)
    else:
        raw_path = None

    extract = extract_json_object(raw)

    if save_artifacts:
        json_path = f"{out_prefix}.json"
        save_json(json_path, extract)
    else:
        json_path = None

    score, level, breakdown = compute_association_risk_score(extract)
    risk_score = risk_score_from_safety(score)  # ✅

    if save_artifacts:
        breakdown_path = f"{out_prefix}.score.json"
        save_json(
            breakdown_path,
            {"score": score, "risk_score": risk_score, "risk_level": level, **breakdown}
        )
        artifacts = {
            "raw_output_path": raw_path,
            "extract_json_path": json_path,
            "score_json_path": breakdown_path
        }

    return {
        "document_type": "BYLAWS",
        "raw_output": raw,
        "extract": extract,
        "score": score,             # safety
        "risk_score": risk_score,   # ✅ 100 - safety
        "risk_level": level,
        "breakdown": breakdown,
        "artifacts": artifacts
    }


# -----------------------------
# OPTIONAL CLI ENTRY
# -----------------------------
if __name__ == "__main__":
    # Minimal CLI-like behavior without argparse
    # (kept optional; wrapper is the main entry now)
    sample_path = None
    out = run_bylaws_wrapper(input_path=sample_path, save_artifacts=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
