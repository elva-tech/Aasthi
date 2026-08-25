import os
import json
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic
from dotenv import load_dotenv
from google import genai
from google import genai
import pytesseract
import fitz
from PIL import Image
import ollama

load_dotenv()

# Native Ollama client.
# Qwen2.5-VL is a vision model, so PDF pages are rendered as images
# and passed directly to the model.
EXTRACTION_MODEL = os.getenv("QWEN_VISION_MODEL", "qwen2.5vl:7b")
RISK_MODEL = "claude-opus-4-7"
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


OC_SCHEMA = {
    "document_type": None,
    "issuing_authority": None,
    "oc_number": None,
    "issue_date": None,
    "project_name": None,
    "property_address": None,
    "builder_or_owner": None,
    "sanction_plan_reference": None,
    "site_area": None,
    "builtup_area": None,
    "buildings": [],
    "residential_units": None,
    "villas_sanctioned": None,
    "villas_covered": None,
    "excluded_units": [],
    "usage_type": None,
    "fire_clearances": [],
    "structural_clearances": [],
    "electrical_clearances": [],
    "lift_clearances": [],
    "stp_clearances": [],
    "kspcb_clearances": [],
    "fire_conditions": [],
    "structural_conditions": [],
    "basement_conditions": [],
    "water_environment_conditions": [],
    "maintenance_conditions": [],
    "deviations": [],
    "legal_restrictions": [],
    "conditions": [],
    "validity": None,
    "confidence_notes": "",
}

LIST_KEYS = [
    "buildings",
    "excluded_units",
    "fire_clearances",
    "structural_clearances",
    "electrical_clearances",
    "lift_clearances",
    "stp_clearances",
    "kspcb_clearances",
    "fire_conditions",
    "structural_conditions",
    "basement_conditions",
    "water_environment_conditions",
    "maintenance_conditions",
    "deviations",
    "legal_restrictions",
    "conditions",
]

SCALAR_KEYS = [
    k for k in OC_SCHEMA
    if k not in LIST_KEYS and k != "confidence_notes"
]


def parse_json_robust(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Qwen returned an empty response")

    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Qwen returned invalid JSON: {e}\nRAW RESPONSE:\n{text[:5000]}"
                )
        raise ValueError(
            "Qwen did not return a JSON object.\n"
            f"RAW RESPONSE:\n{text[:500]}"
        )


def render_page_to_image(
    page: fitz.Page,
    page_no: int,
    dpi: int = 180,
    max_dimension: int = 2200,
) -> str:
    """
    Render ONE PDF page to a temporary JPEG image.

    The image file is passed directly to Qwen2.5-VL through Ollama.
    No PDF text extraction or Tesseract OCR is used for Qwen extraction.
    """
    pix = page.get_pixmap(dpi=dpi, alpha=False)

    img = Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples,
    )

    # Keep scanned pages manageable for the local vision model.
    scale = min(1.0, max_dimension / max(img.width, img.height))

    if scale < 1.0:
        img = img.resize(
            (
                int(img.width * scale),
                int(img.height * scale),
            ),
            Image.Resampling.LANCZOS,
        )

    image_path = os.path.join(
        os.getcwd(),
        f"_oc_qwen_page_{page_no}.jpg",
    )

    img.save(
        image_path,
        format="JPEG",
        quality=90,
        optimize=True,
    )

    return image_path

def page_extraction_prompt(page_no: int, total_pages: int) -> str:
    return f"""
You are extracting data from page {page_no} of {total_pages}
of an Occupancy Certificate.

Read the PAGE IMAGE directly.

Extract ONLY information visibly present on this page.

Do not guess.
Do not infer.
Do not calculate.
Do not summarize.
Do not use outside knowledge.

Return ONLY valid JSON.

Use EXACTLY these keys:

{{
  "document_type": null,
  "issuing_authority": null,
  "oc_number": null,
  "issue_date": null,
  "project_name": null,
  "property_address": null,
  "builder_or_owner": null,
  "sanction_plan_reference": null,
  "site_area": null,
  "builtup_area": null,
  "buildings": [],
  "residential_units": null,
  "villas_sanctioned": null,
  "villas_covered": null,
  "excluded_units": [],
  "usage_type": null,
  "fire_clearances": [],
  "structural_clearances": [],
  "electrical_clearances": [],
  "lift_clearances": [],
  "stp_clearances": [],
  "kspcb_clearances": [],
  "fire_conditions": [],
  "structural_conditions": [],
  "basement_conditions": [],
  "water_environment_conditions": [],
  "maintenance_conditions": [],
  "deviations": [],
  "legal_restrictions": [],
  "conditions": [],
  "validity": null,
  "confidence_notes": ""
}}

For information not visible on THIS page:
use null or [].

Preserve names, numbers, dates and measurements exactly as visible.

For conditions and deviations, preserve the actual text visible on the page.
"""

def qwen_extract_oc_page(
    page: fitz.Page,
    page_no: int,
    total_pages: int,
    dpi: int = 180,
) -> Dict[str, Any]:
    """
    Render the PDF page to an image and send the IMAGE DIRECTLY
    to Qwen2.5-VL through the native Ollama Python API.
    """
    image_path = render_page_to_image(
        page=page,
        page_no=page_no,
        dpi=dpi,
    )

    try:
        response = ollama.chat(
            model=EXTRACTION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": page_extraction_prompt(
                        page_no,
                        total_pages,
                    ),
                    "images": [image_path],
                }
            ],
            options={
                "num_ctx": 8192,
                "temperature": 0,
            },
            format="json",
        )

        raw = response["message"]["content"]

        result = parse_json_robust(raw)

        missing = [k for k in OC_SCHEMA if k not in result]

        if missing:
            raise RuntimeError(
                f"Qwen page {page_no} returned missing keys: {missing}"
            )

        # Keep only the expected schema.
        result = {
            k: result.get(k)
            for k in OC_SCHEMA
        }

        return result

    finally:
        # Delete temporary page image after Qwen has processed it.
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception:
            pass

def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _item_key(item: Any) -> str:
    try:
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(item)


def merge_oc_page_results(page_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge page-level Qwen results without inventing values.

    Scalar fields: keep the first explicit value and record later conflicts.
    List fields: append unique page-level values.
    """
    merged = json.loads(json.dumps(OC_SCHEMA))
    conflicts = []

    for page_info in page_results:

        page_result = page_info.get(
            "data",
            {}
        )

        for key in LIST_KEYS:
            values = page_result.get(key) or []
            if not isinstance(values, list):
                values = [values]

            for value in values:
                if not _is_present(value):
                    continue

                existing_keys = {_item_key(x) for x in merged[key]}
                if _item_key(value) not in existing_keys:
                    merged[key].append(value)

        for key in SCALAR_KEYS:
            value = page_result.get(key)
            if not _is_present(value):
                continue

            if not _is_present(merged[key]):
                merged[key] = value
            elif _item_key(merged[key]) != _item_key(value):
                conflicts.append(
                    f"{key}: multiple explicit page values found "
                    f"({merged[key]!r} vs {value!r})"
                )

        note = page_result.get("confidence_notes")
        if note:
            merged["confidence_notes"] = (
                (merged["confidence_notes"] + "\n") if merged["confidence_notes"] else ""
            ) + str(note)

    if conflicts:
        merged["confidence_notes"] += (
            "\nScalar conflicts preserved by keeping the first explicit value: "
            + " | ".join(conflicts[:20])
        )

    return merged
def find_qwen_page_numbers(pdf_path: str) -> List[int]:
    """
    Select only the pages that should be sent to Qwen.

    Always:
        - Page 1
        - Page 2

    Then:
        - Find the page containing the OC conditions heading.
        - Send that complete page.
        - Continue sending complete pages while numbered conditions
          continue.
    """

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    selected = []

    # ---------------------------------------------------------
    # 1. ALWAYS include first two pages
    # ---------------------------------------------------------
    if total_pages >= 1:
        selected.append(0)

    if total_pages >= 2:
        selected.append(1)

    condition_start = None

    # ---------------------------------------------------------
    # 2. Find condition heading from page 3 onward
    # ---------------------------------------------------------
    for page_index in range(2, total_pages):

        try:
            text = (doc[page_index].get_text("text") or "").lower()

            # If PDF has no text, use OCR ONLY for locating
            # the relevant condition page.
            if not text.strip():
                pix = doc[page_index].get_pixmap(
                    dpi=150,
                    alpha=False
                )

                img = Image.frombytes(
                    "RGB",
                    (pix.width, pix.height),
                    pix.samples
                )

                text = (
                    pytesseract.image_to_string(img)
                    or ""
                ).lower()

            # Normalize OCR text.
            normalized = " ".join(text.split())

            # Main heading.
            heading_found = (
                "occupancy certificate is issued" in normalized
                and "following conditions" in normalized
            )

            # OCR may break/change the sentence.
            alternative_found = (
                "subject to the following conditions" in normalized
                or (
                    "subject to" in normalized
                    and "conditions" in normalized
                    and "occupancy certificate" in normalized
                )
            )

            if heading_found or alternative_found:
                condition_start = page_index

                print(
                    f"[OC] Condition section found on page "
                    f"{page_index + 1}"
                )

                break

        except Exception as e:
            print(
                f"[OC] Could not inspect page "
                f"{page_index + 1}: {e}"
            )

    # ---------------------------------------------------------
    # 3. If condition heading was found,
    #    include full condition pages.
    # ---------------------------------------------------------
    if condition_start is not None:

        selected.append(condition_start)

        for page_index in range(
            condition_start + 1,
            total_pages
        ):

            try:
                text = (
                    doc[page_index].get_text("text")
                    or ""
                ).lower()

                if not text.strip():
                    pix = doc[page_index].get_pixmap(
                        dpi=150,
                        alpha=False
                    )

                    img = Image.frombytes(
                        "RGB",
                        (pix.width, pix.height),
                        pix.samples
                    )

                    text = (
                        pytesseract.image_to_string(img)
                        or ""
                    ).lower()

                normalized = " ".join(text.split())

                # Look for numbered conditions.
                numbered_condition = bool(
                    re.search(
                        r"\b(?:condition\s*)?\d{1,2}\s*[\.\):\-]",
                        normalized,
                        re.IGNORECASE
                    )
                )

                # Continuation indicators.
                continuation = any(
                    keyword in normalized
                    for keyword in [
                        "condition",
                        "conditions",
                        "subject to",
                        "shall be",
                        "shall maintain",
                        "shall ensure",
                        "occupancy certificate",
                        "liable to be withdrawn",
                        "withdrawn"
                    ]
                )

                if numbered_condition or continuation:
                    selected.append(page_index)

                    print(
                        f"[OC] Condition continuation found "
                        f"on page {page_index + 1}"
                    )

                else:
                    # Condition section has ended.
                    break

            except Exception as e:
                print(
                    f"[OC] Could not inspect condition page "
                    f"{page_index + 1}: {e}"
                )
                break

    doc.close()

    # Remove duplicates and keep page order.
    selected = sorted(set(selected))

    print(
        "[OC] Pages selected for Qwen: "
        + ", ".join(str(p + 1) for p in selected)
    )

    return selected

def qwen_extract_oc_from_pdf(
    pdf_path: str,
    dpi: int = 180,
    page_numbers=None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        raise RuntimeError("PDF contains no pages")

    # ---------------------------------------------------------
    # Select only relevant pages.
    #
    # Default:
    #   Page 1
    #   Page 2
    #   Condition heading page
    #   Condition continuation pages
    # ---------------------------------------------------------
    if page_numbers is not None:
        selected_pages = [
            p for p in page_numbers
            if 0 <= p < total_pages
        ]
    else:
        selected_pages = find_qwen_page_numbers(
            pdf_path
        )

    page_results = []

    try:

        for page_index in selected_pages:

            page_no = page_index + 1
            page = doc.load_page(page_index)

            try:

                print(
                    f"\n[OC] Sending page "
                    f"{page_no}/{total_pages} to Qwen Vision..."
                )

                # IMPORTANT:
                # The ENTIRE PDF page is rendered as an image.
                page_result = qwen_extract_oc_page(
                    page=page,
                    page_no=page_no,
                    total_pages=total_pages,
                    dpi=dpi,
                )

                # Keep the page number together with Qwen's result
                page_results.append({
                    "page_number": page_no,
                    "data": page_result,
                })


            except Exception as e:

                print(
                    f"[ERROR] Qwen failed on page "
                    f"{page_no}/{total_pages}: {e}"
                )

                page_results.append({
                "page_number": page_no,
                "data": {
                    **json.loads(
                        json.dumps(OC_SCHEMA)
                    ),
                    "confidence_notes":
                        f"Qwen extraction failed on page {page_no}: {e}",
                },
            })

    finally:
        doc.close()

    merged = merge_oc_page_results(
        page_results
    )

    return merged, page_results

def ocr_pdf_to_text_selected(pdf_path: str, page_numbers=None, dpi: int = 220) -> str:
    """
    Retained only as a fallback/debug helper.
    OC extraction no longer depends on this function.
    """
    doc = fitz.open(pdf_path)
    out = []

    if page_numbers is None:
        page_numbers = range(len(doc))

    for p in page_numbers:
        if p < 0 or p >= len(doc):
            continue

        pix = doc[p].get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        txt = (pytesseract.image_to_string(img) or "").strip()

        if txt:
            out.append(f"\n--- OCR PAGE {p + 1} ---\n{txt}")

    doc.close()
    return "\n".join(out).strip()


def get_claude_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    return Anthropic(api_key=key)

def claude_llm_risk_assessment(
    client,
    oc_json: Dict[str, Any]
) -> Dict[str, Any]:

    risk_prompt = f"""
# ROLE

You are a Senior Building Compliance Consultant,
Occupancy Certificate Auditor,
and Property Due Diligence Expert.

# CONTEXT

A prospective property buyer wants to determine whether this
Occupancy Certificate indicates legal,
regulatory,
or structural risk.

Assess ONLY the supplied Occupancy Certificate information.

Do NOT invent facts.

# OBJECTIVE

Estimate Property Safety Score.

Safety Scale

100 = Extremely Safe

0 = Extremely Unsafe

The application converts this internally into:

Risk Score = 100 − Safety Score

# EVALUATION FRAMEWORK

Evaluate:

1. Statutory Compliance

• Valid OC
• Issuing Authority
• Approval References

2. Building Deviations

• Unauthorized construction
• Deviations
• Exceptions

3. Fire & Life Safety

• Fire clearance
• Emergency systems

4. Structural Compliance

• Structural observations
• Building stability

5. Utilities & Environment

• Drainage
• STP
• Rainwater Harvesting
• Waste Management

6. Conditions

• Restrictions
• Pending requirements
• Mandatory compliance

7. Overall Buyer Risk

# DECISION GUIDELINES

Highest Safety

• Valid OC
• No deviations
• Required clearances available
• No restrictive conditions

Moderate Safety

• Minor conditions
• Minor observations
• Limited missing information

Lowest Safety

• Major deviations
• Compliance failures
• Missing statutory clearances
• Serious restrictions

# IMPORTANT RULES

Never invent information.

Missing information lowers confidence,
not automatically the Safety Score.

Use ONLY supplied data.

Every risk must reference supplied evidence.

Recommendations must be practical.

# OCCUPANCY DATA

{json.dumps(oc_json, indent=2)}

# OUTPUT

Return ONLY valid JSON.

{{
    "risk_summary":"",
    "risks":[
        {{
            "category":"",
            "severity":"LOW|MODERATE|HIGH|CRITICAL",
            "issue":"",
            "impact":"",
            "reasoning":""
        }}
    ],
    "recommended_actions":[
        "...",
        "..."
    ],
    "overall_risk_level":"Low|Moderate|High|Critical",
    "suggested_score_out_of_100":0
}}

# FINAL VALIDATION

✓ Score between 0 and 100.

✓ Overall risk matches score.

✓ Every risk references supplied data.

✓ No invented information.

✓ Return ONLY valid JSON.
""".strip()

    response = client.messages.create(
        model=RISK_MODEL,
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": risk_prompt
            }
        ]
    )

    raw = ""

    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text

    raw = raw.strip()

    print("\n" + "=" * 70)
    print("RAW CLAUDE RESPONSE")
    print("=" * 70)
    print(raw)
    print("=" * 70)

    if not raw:
        raise ValueError("Claude returned an empty response")

    result = parse_json_robust(raw)

    if not isinstance(result, dict):
        raise ValueError(
            f"Claude response is not a JSON object: {type(result)}"
        )

    print("\n" + "=" * 70)
    print("PARSED CLAUDE RESULT")
    print("=" * 70)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 70)

    if "suggested_score_out_of_100" not in result:
        raise ValueError(
            "Claude JSON is missing "
            "'suggested_score_out_of_100'"
        )

    score = result["suggested_score_out_of_100"]

    if not isinstance(score, (int, float)):
        raise ValueError(
            f"Invalid Claude safety score: {score}"
        )

    result["suggested_score_out_of_100"] = max(
        0,
        min(100, float(score))
    )

    return result
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
    return {
        "issuing_authority": oc_json.get("issuing_authority"),
        "oc_number": oc_json.get("oc_number"),
        "issue_date": oc_json.get("issue_date"),
        "project_name": oc_json.get("project_name"),
        "property_address": oc_json.get("property_address"),
        "builder_or_owner": oc_json.get("builder_or_owner"),
        "sanction_plan_reference": oc_json.get("sanction_plan_reference"),
        "site_area": oc_json.get("site_area"),
        "builtup_area": oc_json.get("builtup_area"),
        "buildings": oc_json.get("buildings"),
        "residential_units": oc_json.get("residential_units"),
        "villas_sanctioned": oc_json.get("villas_sanctioned"),
        "villas_covered": oc_json.get("villas_covered"),
        "excluded_units": oc_json.get("excluded_units"),
        "usage_type": oc_json.get("usage_type"),

        "fire_clearances": oc_json.get("fire_clearances"),
        "structural_clearances": oc_json.get("structural_clearances"),
        "electrical_clearances": oc_json.get("electrical_clearances"),
        "lift_clearances": oc_json.get("lift_clearances"),
        "stp_clearances": oc_json.get("stp_clearances"),
        "kspcb_clearances": oc_json.get("kspcb_clearances"),

        "fire_conditions": oc_json.get("fire_conditions"),
        "structural_conditions": oc_json.get("structural_conditions"),
        "basement_conditions": oc_json.get("basement_conditions"),
        "water_environment_conditions": oc_json.get("water_environment_conditions"),
        "maintenance_conditions": oc_json.get("maintenance_conditions"),

        "deviations": oc_json.get("deviations"),
        "legal_restrictions": oc_json.get("legal_restrictions"),

        "conditions": oc_json.get("conditions"),

        "validity": oc_json.get("validity"),
        "confidence_notes": oc_json.get("confidence_notes")
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

def save_oc_screenshots(
    pdf_path,
    screenshot_dir,
    session_id,
    page_results,
    dpi=180,
):
    """
    Save OC pages that Qwen actually extracted meaningful information from.

    Screenshots are saved only for pages processed successfully by Qwen
    and containing meaningful extracted data.

    Output:
        oc_result_<number>_<session_id>.png
    """

    os.makedirs(
        screenshot_dir,
        exist_ok=True
    )

    doc = fitz.open(pdf_path)

    saved = []

    try:

        selected_pages = []

        for page_info in page_results:

            page_no = page_info.get(
                "page_number"
            )

            data = page_info.get(
                "data",
                {}
            )

            if not page_no:
                continue

            if not isinstance(data, dict):
                continue

            # ------------------------------------------------
            # Check whether Qwen actually extracted
            # meaningful information from this page.
            # ------------------------------------------------

            meaningful = False

            for key, value in data.items():

                # confidence_notes alone should not make
                # a page meaningful
                if key == "confidence_notes":
                    continue

                if value is None:
                    continue

                if value == "":
                    continue

                if value == []:
                    continue

                meaningful = True
                break

            if meaningful:
                selected_pages.append(
                    int(page_no)
                )

        # Remove duplicate page numbers
        selected_pages = list(
            dict.fromkeys(
                selected_pages
            )
        )

        print(
            f"[OC] Qwen selected "
            f"{len(selected_pages)} page(s) "
            f"for evidence screenshots:"
        )

        for p in selected_pages:
            print(
                f"    Page {p}"
            )

        # ------------------------------------------------
        # Save selected pages
        # ------------------------------------------------

        for idx, page_no in enumerate(
            selected_pages,
            start=1
        ):

            page_index = page_no - 1

            if (
                page_index < 0
                or page_index >= len(doc)
            ):
                continue

            page = doc.load_page(
                page_index
            )

            pix = page.get_pixmap(
                dpi=dpi,
                alpha=False
            )

            img = Image.frombytes(
                "RGB",
                (
                    pix.width,
                    pix.height
                ),
                pix.samples
            )

            output_path = os.path.join(
                screenshot_dir,
                f"oc_result_{idx}_{session_id}.png"
            )

            img.save(
                output_path,
                format="PNG"
            )

            saved.append(
                output_path
            )

            print(
                f"[OC] Saved Qwen evidence screenshot "
                f"for page {page_no}: "
                f"{output_path}"
            )

    finally:

        doc.close()

    return saved


def run_oc_wrapper_compact(
    pdf_path: str,
    tesseract_cmd: Optional[str] = None,
    page_numbers=None,  # retained for compatibility; ALL pages are now processed
    dpi: int = 180,
    user_inputs: Optional[Dict[str, Any]] = None,
    unknown_policy: str = "conservative",
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
            "rule_risk_score": None,
            "llm_suggested_score": None,
            "llm_risk_score": None,
            "blended_score": None,
            "blended_risk_score": None,
            "overall_risk_level": None
        },
        "reasons": {
            "rule_deductions": [],
            "llm_risk_summary": None,
            "top_llm_risks": []
        },
        "errors": {
            "ocr": None,
            "extraction": None,
            "llm_risk": None
        }
    }

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found at: {pdf_path}")


    # ------------------------------------------------------------
    # 2. QWEN VISION EXTRACTION
    #
    # IMPORTANT:
    # We intentionally DO NOT run:
    #     Tesseract -> OCR text -> qwen3:8b
    #
    # The uploaded OC is a scanned/image PDF.
    # Every page goes directly to a vision-capable Qwen model.
    # ------------------------------------------------------------
    try:
        oc_json, page_results = qwen_extract_oc_from_pdf(
            pdf_path=pdf_path,
            dpi=dpi,
        )
        # ------------------------------------------------------------
# SAVE OC SCREENSHOTS BASED ON QWEN PAGE RESULTS
# ------------------------------------------------------------
        if screenshot_dir and session_id:
            try:
                save_oc_screenshots(
                    pdf_path=pdf_path,
                    screenshot_dir=screenshot_dir,
                    session_id=session_id,
                    page_results=page_results,
                    dpi=dpi,
                )
            except Exception as e:
                print(
                    f"DEBUG: Failed to save OC screenshots: {e}"
                )
        print("\n" + "=" * 70)
        print("QWEN FINAL MERGED OC DATA")
        print("=" * 70)
        print(json.dumps(oc_json, indent=2, ensure_ascii=False))
        print("=" * 70 + "\n")

    except Exception as e:
        out["errors"]["extraction"] = str(e)
        print(f"[ERROR] Qwen OC vision extraction failed: {e}")
        return out

    out["important_data"] = compact_oc_summary(oc_json)

    # Keep extraction-only mode as requested/currently used.
# ------------------------------------------------------------
# 3. PYTHON RULE-BASED RISK SCORE
# ------------------------------------------------------------
    try:
        rule_score, rule_deductions = compute_risk_score(
            oc_json,
            user_inputs=user_inputs,
            unknown_policy=unknown_policy
        )

        out["scores"]["rule_score"] = rule_score
        out["scores"]["rule_risk_score"] = risk_score_from_safety(rule_score)

        out["reasons"]["rule_deductions"] = rule_deductions

        print("\n" + "=" * 70)
        print("PYTHON RISK SCORE")
        print("=" * 70)
        print(f"Safety Score : {rule_score}/100")
        print(f"Risk Score   : {out['scores']['rule_risk_score']}/100")
        print("=" * 70)

    except Exception as e:
        out["errors"]["llm_risk"] = f"Python scoring error: {e}"
        print(f"[ERROR] Python risk scoring failed: {e}")

    # ------------------------------------------------------------
    # 4. LLM RISK ASSESSMENT
    # ------------------------------------------------------------
    try:
        risk_client = get_claude_client()

        llm_risk = claude_llm_risk_assessment(
            risk_client,
            oc_json
        )

        # DEBUG: show exactly what Gemini returned
        print("\n" + "=" * 70)
        print("RAW GEMINI RISK RESULT")
        print("=" * 70)
        print(json.dumps(llm_risk, indent=2, ensure_ascii=False))
        print("=" * 70)

        # Extract Gemini safety score
        llm_score = llm_risk.get("suggested_score_out_of_100")

        if llm_score is None:
            raise ValueError(
                "Gemini response does not contain "
                "'suggested_score_out_of_100'"
            )

        llm_score = int(llm_score)
        llm_score = max(0, min(100, llm_score))

        out["scores"]["llm_suggested_score"] = llm_score

        # Convert Safety -> Risk
        out["scores"]["llm_risk_score"] = risk_score_from_safety(
            llm_score
        )

        out["scores"]["overall_risk_level"] = (
            llm_risk.get("overall_risk_level")
        )

        out["reasons"]["llm_risk_summary"] = (
            llm_risk.get("risk_summary")
        )

        risks = llm_risk.get("risks") or []

        out["reasons"]["top_llm_risks"] = [
            {
                "severity": r.get("severity"),
                "category": r.get("category"),
                "issue": r.get("issue")
            }
            for r in risks[:6]
        ]

        print("\n" + "=" * 70)
        print("LLM RISK SCORE")
        print("=" * 70)
        print(f"LLM Safety Score : {llm_score}")
        print(
            f"LLM Risk Score   : "
            f"{out['scores']['llm_risk_score']}"
        )
        print("=" * 70)

    except Exception as e:
        out["errors"]["llm_risk"] = str(e)
        print(f"[ERROR] LLM risk assessment failed: {e}")
    # ------------------------------------------------------------
    # 5. 70/30 BLENDED SCORE
    # ------------------------------------------------------------
    try:
        rule_score = out["scores"]["rule_score"]
        llm_score = out["scores"]["llm_suggested_score"]

        if rule_score is None or llm_score is None:
            raise ValueError(
                f"Cannot blend scores: "
                f"rule_score={rule_score}, "
                f"llm_score={llm_score}"
            )

        blended_score = blend_scores(
            rule_score=rule_score,
            llm_score=llm_score,
            rule_weight=blend_rule_weight
        )

        out["scores"]["blended_score"] = blended_score

        out["scores"]["blended_risk_score"] = (
            risk_score_from_safety(blended_score)
        )

        risk = out["scores"]["blended_risk_score"]

        if risk >= 70:
            out["scores"]["overall_risk_level"] = "High"
        elif risk >= 40:
            out["scores"]["overall_risk_level"] = "Moderate"
        else:
            out["scores"]["overall_risk_level"] = "Low"

        print("\n" + "=" * 70)
        print("FINAL 70/30 RISK SCORE")
        print("=" * 70)
        print(f"Python Safety Score : {rule_score}")
        print(f"LLM Safety Score    : {llm_score}")
        print(f"Blended Safety      : {blended_score}")
        print(
            f"Final Risk Score    : "
            f"{out['scores']['blended_risk_score']}"
        )
        print(
            f"Risk Level          : "
            f"{out['scores']['overall_risk_level']}"
        )
        print("=" * 70)

    except Exception as e:
        out["errors"]["llm_risk"] = f"Blending error: {e}"
        print(f"[ERROR] Score blending failed: {e}")

    return out
# ============================================================
# OPTIONAL CLI ENTRY
# ============================================================
if __name__ == "__main__":

    PDF_PATH = r"D:\aasthiv2\Aasthi\wrappercode\input\oc\OCPLHC.pdf"

    result = run_oc_wrapper_compact(
        pdf_path=PDF_PATH,
        dpi=180,
        blend_rule_weight=0.7
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str
        )
    )