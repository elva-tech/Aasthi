#!/usr/bin/env python3
# bbmp_propertytax_wrapper.py

import base64
import mimetypes
import os
import re
import json
import pandas as pd
import numpy as np
from PIL import Image
from anthropic import Anthropic
def _safe_json_load(text: str) -> dict:
    text = text.strip()

    text = re.sub(
        r"^\s*```json\s*",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"^\s*```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```\s*$",
        "",
        text
    )

    return json.loads(text.strip())

def claude_score_bbmp_excel_stable(facts: dict) -> dict:

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    client = Anthropic(api_key=api_key)
    prompt = build_bbmp_llm_prompt_from_excel_facts(facts)
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    text = resp.content[0].text.strip()

    return json.loads(text)

def property_tax_risk_engine(facts):

    total_score = 0
    breakdown = []

    # ===================================================
    # 1. PROPERTY IDENTIFICATION (20)
    # ===================================================

    points = 0
    obs = []

    if facts.get("sas_application_number"):
        points += 5

    if facts.get("new_application_number"):
        points += 5

    if facts.get("khata_number"):
        points += 5

    if facts.get("property_number"):
        points += 5

    obs.append("Property identifiers verified")

    breakdown.append({
        "category": "Property Identification",
        "points": points,
        "max_points": 20,
        "observations": obs
    })

    total_score += points

    # ===================================================
    # 2. OWNERSHIP VERIFICATION (20)
    # ===================================================

    points = 0
    obs = []

    owner = str(
        facts.get("owner_name", "")
    ).strip()

    if owner:
        points = 20
        obs.append(f"Owner detected: {owner}")
    else:
        obs.append("Owner missing")

    breakdown.append({
        "category": "Ownership Verification",
        "points": points,
        "max_points": 20,
        "observations": obs
    })

    total_score += points

    # ===================================================
    # 3. TAX COMPLIANCE (25)
    # ===================================================

    points = 0
    obs = []

    if facts.get("latest_year_paid"):
        points += 20
        obs.append("Latest year paid")

    if not facts.get("expired_challans", False):
        points += 5
        obs.append("No expired challans")

    breakdown.append({
        "category": "Tax Compliance",
        "points": points,
        "max_points": 25,
        "observations": obs
    })

    total_score += points

    # ===================================================
    # 4. USAGE & PROPERTY TYPE (10)
    # ===================================================

    points = 0
    obs = []

    usage = str(
        facts.get("usage", "")
    ).upper()

    nature = str(
        facts.get("nature_of_property", "")
    ).upper()

    if usage:
        points += 5

    if nature:
        points += 5

    obs.append(f"Usage: {usage}")
    obs.append(f"Nature: {nature}")

    breakdown.append({
        "category": "Usage & Property Type",
        "points": points,
        "max_points": 10,
        "observations": obs
    })

    total_score += points

    # ===================================================
    # 5. ADDRESS COMPLETENESS (10)
    # ===================================================

    address_fields = [
        "zone",
        "ward",
        "door_number",
        "locality",
        "pin_code"
    ]

    present = sum(
        1 for f in address_fields
        if facts.get(f)
    )

    points = round(
        (present / len(address_fields)) * 10
    )

    breakdown.append({
        "category": "Address Completeness",
        "points": points,
        "max_points": 10,
        "observations": [
            f"{present}/5 address fields present"
        ]
    })

    total_score += points

    # ===================================================
    # 6. CONSTRUCTION & OCCUPANCY (10)
    # ===================================================

    points = 0
    obs = []

    if facts.get("construction_year"):
        points += 5

    if (
        facts.get("self_occupied_area") is not None
        or
        facts.get("tenanted_area") is not None
    ):
        points += 5

    obs.append(
        f"Construction Year: {facts.get('construction_year')}"
    )

    breakdown.append({
        "category": "Construction & Occupancy",
        "points": points,
        "max_points": 10,
        "observations": obs
    })

    total_score += points

    # ===================================================
    # 7. AREA CONSISTENCY (5)
    # ===================================================

    points = 0

    builtup = facts.get("builtup_area")
    plinth = facts.get("plinth_area")

    if (
        builtup
        and
        plinth
    ):

        diff = abs(
            float(builtup)
            -
            float(plinth)
        )

        if diff <= 50:
            points = 5
        elif diff <= 200:
            points = 3

    breakdown.append({
        "category": "Area Consistency",
        "points": points,
        "max_points": 5,
        "observations": [
            f"Builtup={builtup}",
            f"Plinth={plinth}"
        ]
    })

    total_score += points

    # ===================================================
    # FINAL RISK
    # ===================================================

    risk_score = 100 - total_score

    if risk_score <= 15:
        risk_level = "LOW"

    elif risk_score <= 30:
        risk_level = "MEDIUM-LOW"

    elif risk_score <= 45:
        risk_level = "MEDIUM"

    else:
        risk_level = "HIGH"

    return {
        "safety_score": total_score,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "breakdown": breakdown
    }


# ============================================================
# ✅ GEMINI: “MORE FREEDOM” PROMPT + SCORE
# ============================================================

def build_bbmp_llm_prompt_from_excel_facts(facts: dict) -> str:

    payload = {
        "owner_name": facts.get("owner_name"),
        "khata_number": facts.get("khata_number"),
        "property_number": facts.get("property_number"),
        "sas_application_number": facts.get("sas_application_number"),
        "new_application_number": facts.get("new_application_number"),
        "zone": facts.get("zone"),
        "ward": facts.get("ward"),
        "usage": facts.get("usage"),
        "nature_of_property": facts.get("nature_of_property"),
        "door_number": facts.get("door_number"),
        "locality": facts.get("locality"),
        "pin_code": facts.get("pin_code"),
        "builtup_area": facts.get("builtup_area"),
        "plinth_area": facts.get("plinth_area"),
        "construction_year": facts.get("construction_year"),
        "self_occupied_area": facts.get("self_occupied_area"),
        "tenanted_area": facts.get("tenanted_area"),
        "latest_year_paid": facts.get("latest_year_paid"),
        "expired_challans": facts.get("expired_challans")
    }

    return f"""
# ROLE

You are a Senior BBMP Property Tax Auditor, Municipal Compliance Officer,
and Property Due Diligence Expert specializing in Karnataka real estate verification.

# CONTEXT

A property buyer wants to verify whether the BBMP Property Tax information
indicates a legally compliant and low-risk property.

Evaluate ONLY the supplied JSON facts.

Do NOT assume or infer any information.

# OBJECTIVE

Assess the municipal compliance and assign a Safety Score.

Safety Score:

100 = Excellent / Very Safe

0 = Very Poor / High Risk

# EVALUATION FRAMEWORK

Evaluate the following categories.

1. Property Identification (20)

- SAS Application Number
- New Application Number
- Khata Number
- Property Number

2. Ownership Verification (20)

- Owner Name

3. Tax Compliance (25)

- Latest Tax Paid
- Expired Challans

4. Usage & Property Type (10)

- Usage
- Nature of Property

5. Address Completeness (10)

- Zone
- Ward
- Door Number
- Locality
- PIN Code

6. Construction & Occupancy (10)

- Construction Year
- Occupancy Information

7. Area Consistency (5)

- Built-up Area
- Plinth Area

# SCORING GUIDELINES

Property Identification

All identifiers available → Excellent

Few identifiers missing → Moderate reduction

Most identifiers missing → Significant reduction

Ownership

Owner present → High confidence

Missing owner → Lower confidence

Tax Compliance

Latest year paid

No expired challans

Highest weight.

Usage

Usage available

Nature available

Address

More complete address = higher confidence.

Construction

Construction year

Occupancy details

Area

If Built-up Area and Plinth Area are reasonably consistent,
Area Consistency should be TRUE.

If values differ substantially,
Area Consistency should be FALSE.

# IMPORTANT RULES

• Never invent facts.

• Never estimate missing values.

• Missing information reduces confidence,
NOT automatically the score.

• Use ONLY supplied JSON.

• Reasons must reference available evidence.

• Keep reasons concise.

# RISK LEVELS

85–100  = LOW

70–84   = MEDIUM-LOW

55–69   = MEDIUM

0–54    = HIGH

# CONFIDENCE

0.90–1.00

Most fields present.

0.60–0.89

Moderate information available.

0.30–0.59

Sparse information.

Below 0.30

Very limited information.

# OUTPUT

Return ONLY valid JSON.

{{
    "score":0,

    "risk_level":"",

    "flags":{{

        "property_identified":false,

        "ownership_verified":false,

        "tax_compliant":false,

        "usage_verified":false,

        "address_complete":false,

        "construction_info_available":false,

        "area_consistent":false

    }},

    "reasons":[

        "...",
        "...",
        "..."

    ],

    "confidence":0.0

}}

# FINAL VALIDATION

Before returning:

✓ Score between 0 and 100.

✓ Risk level matches score.

✓ Flags agree with supplied facts.

✓ Confidence matches completeness of information.

✓ Reasons supported by facts.

✓ Return ONLY valid JSON.

FACTS

{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()
# ============================================================
# ✅ BLEND SCORE: 70% PYTHON + 30% LLM
# ============================================================

def blend_scores(python_score: int, llm_score: int, w_python: float = 0.7) -> int:
    w_llm = 1.0 - w_python
    final = (w_python * float(python_score)) + (w_llm * float(llm_score))
    return int(round(max(0.0, min(100.0, final))))

from openai import OpenAI


qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

def extract_property_facts_from_image(image_path):

    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/png"

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    response = qwen_client.chat.completions.create(
        model="qwen2.5vl:7b",
        messages=[
            {
                "role": "system",
                "content": "You are an information extraction engine. Return ONLY valid JSON."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
Analyze this BBMP Property Tax screenshot.

Extract ONLY information that is explicitly visible in this screenshot.

Return ONLY valid JSON.

{
  "owner_name": null,
  "khata_number": null,
  "property_number": null,
  "sas_application_number": null,
  "new_application_number": null,
  "zone": null,
  "ward": null,
  "usage": null,
  "nature_of_property": null,
  "door_number": null,
  "locality": null,
  "pin_code": null,
  "builtup_area": null,
  "plinth_area": null,
  "construction_year": null,
  "self_occupied_area": null,
  "tenanted_area": null,
  "latest_year_paid": null,
  "expired_challans": null
}

IMPORTANT EXTRACTION RULES:

1. Extract ONLY values that are actually visible in this screenshot.

2. Do NOT guess, infer, calculate, or invent values.

3. If a field is not visible in this screenshot, return null.

4. Ignore empty fields.

5. Ignore UI placeholders such as:
   - "--Select--"
   - "--Select"
   - "Select"
   - "Please Select"

6. For radio buttons, extract the option that is visibly SELECTED.

7. For dropdowns, extract the currently SELECTED value only.
   Do not extract unselected dropdown options.

8. "usage" must come specifically from the BBMP "Usage" section.
   Valid examples include:
   - Residential
   - Non Residential
   - Both

9. "nature_of_property" must come specifically from the
   "Nature of Property" section.

10. Do NOT confuse "Nature of Property" with:
    - Usage Details Category
    - Sub Category
    - Sub Group
    - Construction Category

11. "builtup_area" must come specifically from:
    "Built up Area (in Sft)"

12. "plinth_area" must come specifically from:
    "Plinth Area (in Sft)"

13. "construction_year" must come from the
    "Year of Construction" field.

14. "self_occupied_area" must come from the
    "Self Occupied" field in Usage Details.

15. "tenanted_area" must come from the
    "Tenanted" field in Usage Details.

16. Preserve the values as shown in the screenshot.

17. Do not use information from another screenshot or assume information
    from another page.

18. If the field is visible but has no value, return null.

19. Return ONLY valid JSON. Do not include explanations or markdown.

FINAL CHECK BEFORE RETURNING:

- Do not return "--Select--" for any field.
- Do not confuse Usage with Nature of Property.
- Do not confuse Nature of Property with Construction Category.
- Extract Built up Area if visible.
- Extract Plinth Area if visible.
- Extract selected radio/dropdown values only.
- Missing information must be null.
"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
                        }
                    }
                ]
            }
        ],
        temperature=0
    )

    text = response.choices[0].message.content.strip()

    return _safe_json_load(text)

def extract_property_facts_from_images(image_paths):

    merged = {}

    for image_path in image_paths:

        print("\n" + "=" * 90)
        print(f"🔍 QWEN ANALYZING: {os.path.basename(image_path)}")
        print("=" * 90)

        facts = extract_property_facts_from_image(image_path)

        print("\n📦 QWEN EXTRACTED DATA:")
        print(json.dumps(
            facts,
            indent=2,
            ensure_ascii=False
        ))

        print("=" * 90)

        for key, value in facts.items():

            if value is None:
                continue

            if isinstance(value, str) and value.strip() == "":
                continue

            if isinstance(value, (list, dict)) and len(value) == 0:
                continue

            merged[key] = value

    print("\n" + "=" * 90)
    print("📦 FINAL MERGED QWEN DATA")
    print("=" * 90)

    print(json.dumps(
        merged,
        indent=2,
        ensure_ascii=False
    ))

    print("=" * 90)

    return merged
# ============================================================
# ✅ WRAPPER (FINAL)
# ============================================================


def create_bbmp_evidence_screenshot(
    image_paths,
    output_path
):
    """
    Merge BBMP screenshots into one evidence image.
    """

    images = []

    for path in image_paths:

        if not os.path.exists(path):
            continue

        img = Image.open(path).convert("RGB")

        images.append(img)

    if not images:
        return

    width = max(img.width for img in images)

    height = sum(img.height for img in images)

    canvas = Image.new(
        "RGB",
        (width, height),
        "white"
    )

    y = 0

    for img in images:

        canvas.paste(img, (0, y))

        y += img.height

    canvas.save(output_path)

def run_bbmp_propertytax_wrapper(
    image_paths: list,
    run_llm_score: bool = True,
    session_id: str = None,
    screenshot_dir: str = None
) -> dict:

    # ==========================================
    # EXTRACT FACTS FROM SCREENSHOTS
    # ==========================================
# ==========================================
# SAVE SCREENSHOT
# ==========================================

    if screenshot_dir and session_id:

        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        screenshot_path = os.path.join(
            screenshot_dir,
            f"bbmp_result_{session_id}.png"
        )

        try:

            create_bbmp_evidence_screenshot(
                image_paths,
                screenshot_path
            )

            print(
                f"Saved BBMP evidence screenshot → {screenshot_path}"
            )

        except Exception as e:

            print(
                f"Failed to save BBMP screenshot: {e}"
            )
    try:

        facts = extract_property_facts_from_images(
            image_paths
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to extract BBMP property facts: {e}"
        )

    # ==========================================
    # PYTHON RISK ENGINE
    # ==========================================

    risk_result = property_tax_risk_engine(
        facts
    )

    py_score = risk_result["safety_score"]

    py_risk = risk_result["risk_score"]

    py_level = risk_result["risk_level"]

    report = risk_result["breakdown"]

    # ==========================================
    # BASE OUTPUT
    # ==========================================

    out = {

        "document_type": "BBMP_PROPERTY_TAX",

        "image_count": len(image_paths),
        "images": image_paths,
        "facts": facts,
        "python": {

            "score": py_score,

            "risk_score": py_risk,

            "risk_level": py_level,

            "breakdown": report
        },

        "claude": {

            "enabled": bool(run_llm_score),

            "output": None,

            "error": None
        },

        "final": None
    }

    # ==========================================
    # GEMINI SCORING
    # ==========================================

    if run_llm_score:

        try:

            llm_out = claude_score_bbmp_excel_stable(
                facts
            )

            out["claude"]["output"] = llm_out

            llm_score = int(
                llm_out.get("score", 0)
            )

            llm_score = max(
                0,
                min(100, llm_score)
            )

            llm_risk = (
                100 - llm_score
            )

            out["claude"]["output"]["risk_score"] = (
                llm_risk
            )

            final_score = blend_scores(
                py_score,
                llm_score,
                w_python=0.7
            )

            final_risk = (
                100 - final_score
            )

            if final_risk <= 15:

                final_level = "LOW"

            elif final_risk <= 30:

                final_level = "MEDIUM-LOW"

            elif final_risk <= 45:

                final_level = "MEDIUM"

            else:

                final_level = "HIGH"

            out["final"] = {

                "score": final_score,

                "risk_score": final_risk,

                "risk_level": final_level,

                "weights": {

                    "python": 0.7,

                    "llm": 0.3
                },

                "components": {

                    "python_score": py_score,

                    "python_risk_score": py_risk,

                    "llm_score": llm_score,

                    "llm_risk_score": llm_risk
                }
            }

        except Exception as e:

            out["claude"]["error"] = str(e)

            out["final"] = {

                "score": py_score,

                "risk_score": py_risk,

                "risk_level": py_level,

                "weights": {

                    "python": 1.0,

                    "llm": 0.0
                },

                "components": {

                    "python_score": py_score,

                    "python_risk_score": py_risk,

                    "llm_score": None,

                    "llm_risk_score": None
                }
            }

    else:

        out["final"] = {

            "score": py_score,

            "risk_score": py_risk,

            "risk_level": py_level,

            "weights": {

                "python": 1.0,

                "llm": 0.0
            },

            "components": {

                "python_score": py_score,

                "python_risk_score": py_risk,

                "llm_score": None,

                "llm_risk_score": None
            }
        }

    return out
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="BBMP screenshot/image paths"
    )

    parser.add_argument(
        "--session-id",
        default="debug"
    )

    parser.add_argument(
        "--screenshot-dir",
        default="screenshots"
    )

    args = parser.parse_args()

    result = run_bbmp_propertytax_wrapper(
        image_paths=args.images,
        run_llm_score=False,
        session_id=args.session_id,
        screenshot_dir=args.screenshot_dir
    )

    print("\n" + "=" * 90)
    print("BBMP PROPERTY TAX — QWEN EXTRACTION RESULT")
    print("=" * 90)

    print(json.dumps(
        result,
        indent=2,
        ensure_ascii=False
    ))
