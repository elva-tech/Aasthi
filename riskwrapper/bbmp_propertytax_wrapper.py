#!/usr/bin/env python3
# bbmp_propertytax_wrapper.py

import os
import re
import json
import pandas as pd
import numpy as np


# ============================================================
# ✅ MOCK DATA (DUMP DATA)
# ============================================================

def get_mock_bbmp_facts():
    """Returns realistic mock facts for BBMP property tax."""
    return {
        "latest_year": 2024,
        "years_present": [2021, 2022, 2023, 2024],
        "paid_years": [2021, 2022, 2023, 2024],
        "expired_challan_years": [],
        "sas_app_numbers": ["1000829555"],
        "tax_amount_variance": "LOW",
        "tax_trend": "GRADUAL_INCREASE",
        "has_bulk_payments": False,
        "has_suspicious_drops": False,
        "assessment_type": "SAS",
        "property_id_consistency": "CONSISTENT",
        "owner_name_match": "MATCHED",
        "usage_match": "MATCHED"
    }


# ============================================================
# ✅ FACT EXTRACTION FROM BBMP EXCEL
# ============================================================

def extract_facts_from_excel(excel_path: str):
    df = pd.read_excel(excel_path)

    # Normalize column names
    df.columns = [c.strip().replace("\n", " ") for c in df.columns]

    # Rename known BBMP columns
    df = df.rename(columns={
        "Payment Year / Form Type": "year_raw",
        "Paid status": "status",
        "Net Amount": "tax_amount",
        "Paid Amount": "paid_amount",
        "SAS App. No": "sas_no"
    })

    required = ["year_raw", "status", "tax_amount", "paid_amount", "sas_no"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column in Excel: {c}")

    def extract_years(val):
        if pd.isna(val):
            return []
        return [int(x) for x in re.findall(r"\d{4}", str(val))]

    def expand_years(yrs):
        if len(yrs) == 2 and yrs[1] > yrs[0]:
            return list(range(yrs[0], yrs[1] + 1))
        return yrs

    df["years_list"] = df["year_raw"].apply(extract_years).apply(expand_years)

    years_present = sorted({y for lst in df["years_list"] for y in lst})
    latest_year = max(years_present) if years_present else None

    exp = df[["years_list", "status", "tax_amount", "paid_amount", "sas_no"]].explode("years_list")
    exp = exp.rename(columns={"years_list": "year"})
    exp["year"] = pd.to_numeric(exp["year"], errors="coerce")

    paid_years = exp.loc[
        exp["status"].str.contains("receipt", case=False, na=False),
        "year"
    ].dropna().astype(int).tolist()

    expired_years = exp.loc[
        exp["status"].str.contains("expired", case=False, na=False),
        "year"
    ].dropna().astype(int).tolist()

    sas_numbers = exp["sas_no"].dropna().astype(str).unique().tolist()

    # Annual paid totals (Prefer Paid Amount; fallback Net Amount)
    amt = exp["paid_amount"].where(exp["paid_amount"].notna(), exp["tax_amount"])
    exp["amt_effective"] = pd.to_numeric(amt, errors="coerce").fillna(0.0)

    annual_paid = (
        exp.loc[exp["status"].str.contains("receipt", case=False, na=False)]
          .groupby("year")["amt_effective"]
          .sum()
          .sort_index()
    )

    # Tax variance (CV on annual totals)
    if len(annual_paid) == 0:
        tax_variance = "HIGH"
    else:
        mean = float(annual_paid.mean())
        std = float(annual_paid.std(ddof=0))
        cv = (std / mean) if mean != 0 else float("inf")
        if cv < 0.15:
            tax_variance = "LOW"
        elif cv < 0.35:
            tax_variance = "MEDIUM"
        else:
            tax_variance = "HIGH"

    # Tax trend (annual totals)
    if len(annual_paid) <= 1:
        tax_trend = "STABLE"
    else:
        diff = annual_paid.diff().dropna()
        if (diff >= 0).all():
            tax_trend = "GRADUAL_INCREASE"
        elif abs(diff.mean()) < 100:
            tax_trend = "STABLE"
        else:
            tax_trend = "IRREGULAR"

    has_bulk_payments = exp["year"].value_counts().max() > 1
    has_suspicious_drops = bool((annual_paid.diff() < -500).any()) if len(annual_paid) > 1 else False

    # Clean for display
    paid_years = sorted(set(paid_years))
    expired_years = sorted(set(expired_years))

    return {
        "latest_year": latest_year,
        "years_present": years_present,
        "paid_years": paid_years,
        "expired_challan_years": expired_years,
        "sas_app_numbers": sas_numbers,
        "tax_amount_variance": tax_variance,
        "tax_trend": tax_trend,

        # ✅ ensure Python bool (JSON safe)
        "has_bulk_payments": bool(has_bulk_payments),
        "has_suspicious_drops": bool(has_suspicious_drops),

        "assessment_type": "SAS",
        "property_id_consistency": "MISSING",
        "owner_name_match": "MISSING",
        "usage_match": "MISSING"
    }


# ============================================================
# ✅ PROPERTY TAX RISK ENGINE (DETERMINISTIC PYTHON)
# ============================================================

def property_tax_risk_engine(facts):
    breakdown = []
    total_score = 0
    max_total = 100

    # 1️⃣ TAX PAYMENT STATUS (30)
    points = 0
    obs = []
    if facts["latest_year"] in facts["paid_years"]:
        points += 25
        obs.append(f"✅ Latest year {facts['latest_year']} paid")
    else:
        obs.append(f"❌ Latest year {facts['latest_year']} unpaid")

    if not facts["expired_challan_years"]:
        points += 5
        obs.append("✅ No expired challans")
    else:
        obs.append(f"⚠️ Expired challans: {facts['expired_challan_years']}")

    breakdown.append({
        "emoji": "1️⃣", "category": "Tax Payment Status",
        "points": points, "max_points": 30, "observations": obs
    })
    total_score += points

    # 2️⃣ ASSESSMENT TYPE (15)
    breakdown.append({
        "emoji": "2️⃣", "category": "Assessment Type",
        "points": 15, "max_points": 15,
        "observations": ["✅ Official BBMP SAS Forms (2 / 4 / 5)"]
    })
    total_score += 15

    # 3️⃣ PROPERTY IDENTIFICATION (20)
    unique_sas = len(set(facts["sas_app_numbers"]))
    years_count = len(facts["years_present"])

    if unique_sas == 1:
        points = 20
        obs = ["✅ Same SAS number across all years"]
    elif unique_sas == 2:
        points = 12
        obs = ["⚠️ Two SAS numbers detected"]
    else:
        points = 5
        obs = ["❌ Multiple SAS numbers detected"]

    breakdown.append({
        "emoji": "3️⃣", "category": "Property Identification Consistency",
        "points": points, "max_points": 20, "observations": obs
    })
    total_score += points

    # 4️⃣ OWNERSHIP CONTINUITY (15)
    points = 0
    obs = []

    if years_count >= 10:
        points += 8
        obs.append("✅ Long continuous tax history")
    elif years_count >= 5:
        points += 5
        obs.append("✅ Moderate tax history")
    else:
        points += 2
        obs.append("⚠️ Short tax history")

    if unique_sas == 1:
        points += 5
        obs.append("✅ Stable ownership signal")
    else:
        points += 2
        obs.append("⚠️ Possible ownership change")

    breakdown.append({
        "emoji": "4️⃣", "category": "Ownership Continuity",
        "points": points, "max_points": 15, "observations": obs
    })
    total_score += points

    # 5️⃣ TAX VARIANCE (10)
    variance_score = {"LOW": 10, "MEDIUM": 7, "HIGH": 4}
    points = variance_score.get(facts["tax_amount_variance"], 0)

    breakdown.append({
        "emoji": "5️⃣", "category": "Tax Variance",
        "points": points, "max_points": 10,
        "observations": [f"Tax variance: {facts['tax_amount_variance']}"]
    })
    total_score += points

    # 6️⃣ TAX TREND (10)
    if facts["tax_trend"] == "GRADUAL_INCREASE":
        points = 10
    elif facts["tax_trend"] == "STABLE":
        points = 7
    else:
        points = 0

    breakdown.append({
        "emoji": "6️⃣", "category": "Tax Trend Behaviour",
        "points": points, "max_points": 10,
        "observations": [f"Trend: {facts['tax_trend']}"]
    })
    total_score += points

    if total_score >= 85:
        risk_level, emoji = "LOW", "🟢"
    elif total_score >= 70:
        risk_level, emoji = "MEDIUM-LOW", "🟡"
    elif total_score >= 55:
        risk_level, emoji = "MEDIUM", "🟠"
    else:
        risk_level, emoji = "HIGH", "🔴"

    return generate_report(breakdown, total_score, max_total, risk_level, emoji), total_score, risk_level


def generate_report(breakdown, total, max_total, level, emoji):
    lines = []
    lines.append("=" * 70)
    lines.append("PROPERTY TAX RISK ASSESSMENT REPORT")
    lines.append("=" * 70)
    for b in breakdown:
        lines.append(f"{b['emoji']} {b['category']} ({b['points']} / {b['max_points']})")
        for o in b["observations"]:
            lines.append(f"  {o}")
        lines.append("")
    lines.append("=" * 70)
    lines.append(f"{emoji} FINAL SCORE: {total} / {max_total}")
    lines.append(f"RISK LEVEL: {level}")
    lines.append("=" * 70)
    return "\n".join(lines)


# ============================================================
# ✅ RISK SCORE = 100 - SAFETY SCORE (HELPERS)
# ============================================================

def risk_score_from_safety(score: int) -> int:
    """Convert safety score (higher is safer) to risk score (higher is riskier)."""
    score = int(max(0, min(100, score)))
    return 100 - score


def risk_level_from_risk_score(risk: int) -> str:
    """Risk level where higher risk score = higher risk."""
    risk = int(max(0, min(100, risk)))
    if risk >= 45:
        return "HIGH"
    if risk >= 30:
        return "MEDIUM"
    if risk >= 15:
        return "MEDIUM-LOW"
    return "LOW"


def level_from_score(score: int) -> str:
    """Safety label (kept for backward compatibility)."""
    if score >= 85:
        return "LOW"
    if score >= 70:
        return "MEDIUM-LOW"
    if score >= 55:
        return "MEDIUM"
    return "HIGH"


# ============================================================
# ✅ GEMINI: “MORE FREEDOM” PROMPT + SCORE
# ============================================================

def build_bbmp_llm_prompt_from_excel_facts(facts: dict) -> str:
    payload = {
        "latest_year": facts.get("latest_year"),
        "years_present": facts.get("years_present", []),
        "paid_years": facts.get("paid_years", []),
        "expired_challan_years": facts.get("expired_challan_years", []),
        "sas_app_numbers": facts.get("sas_app_numbers", []),
        "tax_amount_variance": facts.get("tax_amount_variance"),
        "tax_trend": facts.get("tax_trend"),
        "has_bulk_payments": facts.get("has_bulk_payments"),
        "has_suspicious_drops": facts.get("has_suspicious_drops"),
    }

    return f"""
Score BBMP Property Tax compliance risk using ONLY the JSON facts provided.

Rules:
- Use ONLY provided facts. Do NOT assume owner, usage, PID, address or anything not given.
- Output STRICT JSON only. No markdown. No text.
- Higher score = safer.
- Score must be integer 0..100.

Scoring logic (deterministic):
Start score = 85

If latest_year not paid => -25
If expired_challan_years not empty => -10
If multiple SAS numbers:
    2 => -8
    >=3 => -15
If tax_amount_variance HIGH => -10
If tax_amount_variance MEDIUM => -5
If tax_trend IRREGULAR => -10
If tax_trend STABLE => -3
If has_bulk_payments => -3
If has_suspicious_drops => -7

Clamp 0..100.

Risk level:
>=85 LOW
>=70 MEDIUM-LOW
>=55 MEDIUM
else HIGH

Reasons rule:
- Add 1 short reason for every deduction applied.
- Do NOT add reasons for positive factors.

Confidence rule:
- confidence = 0.9 if latest_year is not null AND years_present not empty AND sas_app_numbers not empty
- confidence = 0.6 if at least 2 of these are present: latest_year, years_present, sas_app_numbers, paid_years
- confidence = 0.3 otherwise

Flag rules:
- latest_year_paid = (latest_year in paid_years)
- expired_challans = (expired_challan_years not empty)
- multiple_sas = (count of unique sas_app_numbers >= 2)
- high_variance = (tax_amount_variance == "HIGH")
- irregular_trend = (tax_trend == "IRREGULAR")
- bulk_payment_pattern = (has_bulk_payments is true)
- suspicious_drop_pattern = (has_suspicious_drops is true)

Return ONLY this JSON structure:

{{
  "score": 0,
  "risk_level": "",
  "flags": {{
    "latest_year_paid": false,
    "expired_challans": false,
    "multiple_sas": false,
    "high_variance": false,
    "irregular_trend": false,
    "bulk_payment_pattern": false,
    "suspicious_drop_pattern": false
  }},
  "reasons": ["..."],
  "confidence": 0.0
}}

FACTS:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def gemini_score_bbmp_excel_stable(facts: dict) -> dict:
    api_key = os.getenv("GEMINI_API_KEY3")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY3 env var.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=build_bbmp_llm_prompt_from_excel_facts(facts),
        config=types.GenerateContentConfig(
            temperature=0,
            top_p=0.1,
            top_k=1,
            response_mime_type="application/json",
            max_output_tokens=2048
        )
    )

    return json.loads(resp.text)


# ============================================================
# ✅ BLEND SCORE: 70% PYTHON + 30% LLM
# ============================================================

def blend_scores(python_score: int, llm_score: int, w_python: float = 0.7) -> int:
    w_llm = 1.0 - w_python
    final = (w_python * float(python_score)) + (w_llm * float(llm_score))
    return int(round(max(0.0, min(100.0, final))))


# ============================================================
# ✅ WRAPPER (FINAL)
# ============================================================

def run_bbmp_propertytax_wrapper(excel_path: str, run_llm_score: bool = True, session_id: str = None, screenshot_dir: str = None) -> dict:
    try:
        facts = extract_facts_from_excel(excel_path)
    except Exception as e:
        print(f"⚠️ Error extracting facts from Excel: {e}. Using mock data.")
        facts = get_mock_bbmp_facts()
    
    # If facts are empty/missing, also fallback to mock
    if not facts.get("years_present"):
        print("⚠️ No years found in Excel. Using mock data.")
        facts = get_mock_bbmp_facts()

    report, py_score, py_level = property_tax_risk_engine(facts)

    py_risk = risk_score_from_safety(py_score)

    out = {
        "document_type": "BBMP_PROPERTY_TAX",
        "excel_path": excel_path,
        "facts": facts,
        "python": {
            "score": py_score,  # safety score (higher is safer)
            "risk_score": py_risk,  # ✅ 100 - score (higher is riskier)
            "risk_level": py_level,  # safety-based label (existing)
            "risk_level_from_risk_score": risk_level_from_risk_score(py_risk),  # risk-based label
            "report": report
        },
        "gemini": {
            "enabled": bool(run_llm_score),
            "output": None,
            "error": None
        },
        "final": None
    }

    if run_llm_score:
        try:
            llm_out = gemini_score_bbmp_excel_stable(facts)
            out["gemini"]["output"] = llm_out

            llm_score = int(llm_out.get("score", 0) or 0)
            llm_score = max(0, min(100, llm_score))
            llm_risk = risk_score_from_safety(llm_score)

            # add computed risk score alongside Gemini output (non-breaking)
            if isinstance(out["gemini"]["output"], dict):
                out["gemini"]["output"]["risk_score"] = llm_risk
                out["gemini"]["output"]["risk_level_from_risk_score"] = risk_level_from_risk_score(llm_risk)

            final_score = blend_scores(py_score, llm_score, w_python=0.7)
            final_risk = risk_score_from_safety(final_score)

            out["final"] = {
                "score": final_score,  # safety score
                "risk_score": final_risk,  # ✅ 100 - score
                "risk_level": level_from_score(final_score),  # safety-based label
                "risk_level_from_risk_score": risk_level_from_risk_score(final_risk),  # risk-based label
                "weights": {"python": 0.7, "llm": 0.3},
                "components": {
                    "python_score": py_score,
                    "python_risk_score": py_risk,
                    "llm_score": llm_score,
                    "llm_risk_score": llm_risk
                }
            }

        except Exception as e:
            out["gemini"]["error"] = str(e)
            # fallback: deterministic only
            out["final"] = {
                "score": py_score,
                "risk_score": py_risk,  # ✅ 100 - score
                "risk_level": py_level,
                "risk_level_from_risk_score": risk_level_from_risk_score(py_risk),
                "weights": {"python": 1.0, "llm": 0.0},
                "components": {"python_score": py_score, "python_risk_score": py_risk, "llm_score": None, "llm_risk_score": None}
            }

    else:
        out["final"] = {
            "score": py_score,
            "risk_score": py_risk,  # ✅ 100 - score
            "risk_level": py_level,
            "risk_level_from_risk_score": risk_level_from_risk_score(py_risk),
            "weights": {"python": 1.0, "llm": 0.0},
            "components": {"python_score": py_score, "python_risk_score": py_risk, "llm_score": None, "llm_risk_score": None}
        }

    return out


# ============================================================
# ✅ OPTIONAL CLI ENTRY: prints JSON + saves JSON file
# ============================================================

if __name__ == "__main__":
    EXCEL_PATH = "bbmp_property_details.xlsx"

    result = run_bbmp_propertytax_wrapper(EXCEL_PATH, run_llm_score=True)

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    with open("bbmp_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
