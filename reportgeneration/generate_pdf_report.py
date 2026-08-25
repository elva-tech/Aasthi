#!/usr/bin/env python3
# generate_pdf_report.py
"""
PDF Risk Report Generator (Attractive + emojis + borders + filled space + NO LayoutError)

✅ NO "Score source" shown anywhere
✅ LLM reasoning for ALL modules (no Inputs section)
✅ Cover page is user-focused (no mention of JSON)
✅ Removed Legend from first page
✅ Fixed Summary "Meter" so low/high don't look identical in PDF (ASCII bar)
✅ Supports 4 API keys with automatic fallback if one is exhausted

Install:
  pip install reportlab google-genai python-dotenv

Set keys in .env:
  GEMINI_REPORT_KEY_1=...

Run:
  python generate_pdf_report.py --input output/risk_report_*.json --out output/report.pdf --verbose
"""

import os
import re
import json
import traceback
import math
import argparse
from datetime import datetime
from collections import defaultdict
from turtle import title
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from anthropic import Anthropic
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    ListFlowable,
    ListItem,
    Flowable,
    KeepInFrame,
    Image,
)

# Load .env (keys, etc.)
dotenv_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
load_dotenv(dotenv_path)
load_dotenv()

# =============================================================================
# Helpers
# =============================================================================
def clamp(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    try:
        x = float(x)
    except Exception:
        return None
    return max(0.0, min(100.0, x))


def get(d: Any, path: str) -> Any:
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def first_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    s = str(val)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def risk_level(risk: Optional[float]) -> str:
    if risk is None:
        return "UNKNOWN"
    if risk >= 70:
        return "HIGH RISK"
    if risk >= 40:
        return "MEDIUM RISK"
    return "LOW RISK"


def risk_emoji(risk: Optional[float]) -> str:
    if risk is None:
        return "❔"
    if risk >= 70:
        return "🚨"
    if risk >= 40:
        return "⚠️"
    return "✅"


def clean_text(s: Any) -> str:
    s = "" if s is None else str(s)
    s = s.strip()
    s = re.sub(r"^[^\w]+", "", s).strip()
    s = s.replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _trim_sentence(s: str, max_chars: int = 170) -> str:
    s = clean_text(s)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def safe_avg(vals: List[Optional[float]]) -> Optional[float]:
    v = [x for x in vals if x is not None and not math.isnan(x)]
    if not v:
        return None
    return sum(v) / len(v)

def is_not_applicable(check_obj: Dict[str, Any]) -> bool:
    # If wrapper data exists, this check is applicable
    if check_obj.get("extracted_data"):
        return False

    return str(check_obj.get("status", "")).upper() == "NOT_APPLICABLE"

CHECK_WEIGHTS = {

    "Title Check": 0.14,                         # kaveriecrisk

    "Court Cases": 0.11,                         # ecourtrisk

    "Existing Bank Loans": 0.10,                 # bankloan

    "Khata/Mutation Type Verification": 0.09,   # khata + ekhatarisk

    "Property Tax Paid Receipts": 0.06,          # bbmp_property_tax

    "Electricity Bill": 0.04,                    # bescom

    "Water Bill": 0.04,                          # water

    "Occupancy Certificate": 0.08,               # oc

    "NOCs from Various Departments": 0.07,      # noc

    "Parking Certificate": 0.04,                # parking

    "Association By Laws": 0.03,                # bylaws

    "Municipal Compliance Checks": 0.04,        # ec

    "Builder/Developer Reputation": 0.06,       # builder

    "Registration Check": 0.10,
}

def risk_color(risk: Optional[float]) -> Tuple[Any, Any]:
    if risk is None:
        return (colors.HexColor("#E5E7EB"), colors.black)
    if risk >= 70:
        return (colors.HexColor("#EF4444"), colors.white)
    if risk >= 40:
        return (colors.HexColor("#F59E0B"), colors.black)
    return (colors.HexColor("#22C55E"), colors.white)


def risk_tint(risk: Optional[float]):
    if risk is None:
        return colors.HexColor("#F3F4F6")
    if risk >= 70:
        return colors.HexColor("#FEE2E2")
    if risk >= 40:
        return colors.HexColor("#FEF3C7")
    return colors.HexColor("#DCFCE7")


def score_bar_fill(risk: Optional[float], width: float) -> float:
    if risk is None:
        return 0.0
    r = clamp(risk) or 0.0
    return (r / 100.0) * width


def pct_bar(risk: Optional[float]) -> str:
    """
    PDF-safe meter.
    Avoid ░ because some PDF fonts render it like █ (so low/high look same).
    Use ASCII (# and .) so Low/High look different reliably.
    """
    if risk is None:
        return "N/A"
    blocks = 10
    filled = int(round((clamp(risk) or 0) / 100 * blocks))
    filled = max(0, min(blocks, filled))
    return "#" * filled + "." * (blocks - filled)


def make_card(title: str, body_flowables: List[Any], width: float, max_height: float, title_style: ParagraphStyle):
    content = [Paragraph(title, title_style), Spacer(1, 6)] + body_flowables
    # Old ReportLab signature (positional args)
    kif = KeepInFrame(width, max_height, content, mode="shrink")

    tbl = Table([[kif]], colWidths=[width])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#D1D5DB")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return tbl


from typing import List, Optional
import os
import re


def get_screenshots_for_check(
    module_name: str,
    input_json_path: str,
    verbose: bool = False,
    session_id: str = None,
    screenshot_dir: str = None,
) -> List[str]:
    """
    Return screenshots belonging ONLY to the requested module
    and ONLY to the current session.

    Screenshot rules:
        Court Cases           -> max 3
        Occupancy Certificate -> max 4
        Parking               -> max 4
        By Laws               -> max 2
        EC                    -> max 2
        NOC                   -> max 3
        Others                -> max 1

    IMPORTANT:
        - Matching is based on the actual module name.
        - Old screenshots from previous sessions are NEVER used.
        - No title-based guessing.
        - No random fallback to another screenshot.
    """

    # ------------------------------------------------------------
    # MODULE -> SCREENSHOT PREFIX
    # ------------------------------------------------------------
    MODULE_TO_PREFIX = {
        "oc": "oc_result",
        "noc": "noc_result",
        "parking": "parking_result",
        "bylaws": "bylaws_result",

        # EC Document Check
        "ec": "ec_result",

        # Court Cases
        "ecourtrisk": "court_result",

        "builder": "builder_result",
        "bankloan": "bankloan_result",
        "bescom": "bescom_result",
        "water": "water_result",
        "bbmp_property_tax": "bbmp_result",
        "kaveriecrisk": "kaveri_result",
        "ekhatarisk": "khata_result",
        "rera_approval": "rera_result",
    }

    # ------------------------------------------------------------
    # SCREENSHOT LIMITS
    # ------------------------------------------------------------
    SCREENSHOT_LIMITS = {
        "oc_result": 4,
        "parking_result": 4,
        "ec_result": 2,

        # ALL NOC screenshots from current session
        "noc_result": 3,

        "kaveri_result": 1,
        "khata_result": 1,
        "bankloan_result": 1,
        "bbmp_result": 1,
        "bescom_result": 1,
        "water_result": 1,
    }

    # ------------------------------------------------------------
    # NORMALIZE MODULE NAME
    # ------------------------------------------------------------
    module = str(module_name or "").strip().lower()

    # Handle possible aliases
    module_aliases = {
        "ec document check": "ec",
        "encumbrance certificate": "ec",
        "encumbrance": "ec",

        "court cases": "ecourtrisk",
        "court case": "ecourtrisk",

        "association by laws": "bylaws",
        "association bylaws": "bylaws",
        "by laws": "bylaws",

        "occupancy certificate": "oc",

        "parking certificate": "parking",

        "nocs from various departments": "noc",
        "no objection certificate": "noc",
    }

    module = module_aliases.get(module, module)

    # ------------------------------------------------------------
    # GET PREFIX DIRECTLY FROM MODULE
    # ------------------------------------------------------------
    prefix = MODULE_TO_PREFIX.get(module)

    if not prefix:
        if verbose:
            print(
                f"[DEBUG] No screenshot mapping for module: "
                f"{module_name}"
            )
        return []

    if verbose:
        print(
            f"[DEBUG] Screenshot lookup: "
            f"module={module_name} -> "
            f"normalized={module} -> "
            f"prefix={prefix}"
        )

    # ------------------------------------------------------------
    # BASE DIRECTORY
    # ------------------------------------------------------------
    base_dir = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    # ------------------------------------------------------------
    # SCREENSHOT DIRECTORIES
    # ------------------------------------------------------------

    screenshot_dirs = []

    # Main screenshot directory
    DEFAULT_SCREENSHOT_DIR = (
        r"D:\aasthiv2\Aasthi\riskwrapper\screenshots"
    )

    # Use explicitly supplied directory if provided
    if screenshot_dir:
        screenshot_dirs.append(
            os.path.abspath(screenshot_dir)
        )

    # Always include the required default directory
    screenshot_dirs.append(
        DEFAULT_SCREENSHOT_DIR
    )

    # Remove duplicates
    screenshot_dirs = list(
        dict.fromkeys(
            os.path.abspath(d)
            for d in screenshot_dirs
        )
    )

    if verbose:
        print(
            f"[DEBUG] Screenshot directories: "
            f"{screenshot_dirs}"
        )

    # ------------------------------------------------------------
    # DETERMINE SESSION ID
    # ------------------------------------------------------------
    if not session_id:
        json_name = os.path.basename(
            input_json_path or ""
        )

        # Supports:
        # 20260822_110208
        # 20260822110208
        # 13-digit timestamp
        m = re.search(
            r"(\d{8}_\d{6}|\d{14}|\d{13})",
            json_name
        )

        if m:
            session_id = m.group(1)

    if session_id:
        session_id = str(
            session_id
        ).strip().lower()

    if verbose:
        print(
            f"[DEBUG] Screenshot session: "
            f"{session_id}"
        )

    # ------------------------------------------------------------
    # FIND SCREENSHOTS
    # ------------------------------------------------------------
    candidates = []
    seen_files = set()

    for folder in screenshot_dirs:

        if not os.path.isdir(folder):
            continue

        try:
            filenames = os.listdir(folder)
        except Exception as e:
            if verbose:
                print(
                    f"[DEBUG] Cannot read screenshot folder "
                    f"{folder}: {e}"
                )
            continue

        for fname in filenames:

            low = fname.lower()

            # ----------------------------------------------------
            # IMAGE FILE ONLY
            # ----------------------------------------------------
            if not low.endswith(
                (".png", ".jpg", ".jpeg")
            ):
                continue

            # ----------------------------------------------------
            # MODULE PREFIX MUST MATCH
            #
            # Example:
            # ec -> ec_result
            # parking -> parking_result
            # noc -> noc_result
            # ----------------------------------------------------
            if not low.startswith(
                prefix.lower()
            ):
                continue

            full_path = os.path.abspath(
                os.path.join(
                    folder,
                    fname
                )
            )

            # Prevent duplicate files if directories overlap
            if full_path in seen_files:
                continue

            seen_files.add(full_path)

            # ----------------------------------------------------
            # STRICT SESSION MATCH
            #
            # THIS IS THE IMPORTANT FIX.
            #
            # If current session is:
            # 20260822_110208
            #
            # then:
            #
            # ec_result_20260822_110208.png
            #
            # is accepted.
            #
            # ec_result_20260821_193451.png
            #
            # is rejected.
            # ----------------------------------------------------
            if session_id:

                if session_id not in low:
                    if verbose:
                        print(
                            f"[DEBUG] Ignoring old screenshot: "
                            f"{fname}"
                        )
                    continue

            # ----------------------------------------------------
            # FILE MODIFICATION TIME
            # ----------------------------------------------------
            try:
                modified_time = os.path.getmtime(
                    full_path
                )
            except OSError:
                continue

            candidates.append(
                (
                    modified_time,
                    full_path
                )
            )

    # ------------------------------------------------------------
    # NO CURRENT-SESSION SCREENSHOTS
    # ------------------------------------------------------------
    if not candidates:

        if verbose:
            print(
                f"[DEBUG] No screenshots found for "
                f"module={module} "
                f"prefix={prefix} "
                f"session={session_id}"
            )

        return []

    # ------------------------------------------------------------
    # NEWEST FIRST
    # ------------------------------------------------------------
    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    screenshots = [
        path
        for _, path in candidates
    ]

    # ------------------------------------------------------------
    # SCREENSHOT LIMIT
    # ------------------------------------------------------------
    if prefix not in SCREENSHOT_LIMITS:

        if verbose:
            print(
                f"[DEBUG] No screenshot rule defined "
                f"for prefix={prefix}"
            )

        return []

    limit = SCREENSHOT_LIMITS[
        prefix
    ]

    if limit is None:
        # NOC -> all current-session screenshots
        selected = screenshots
    else:
        selected = screenshots[:limit]

    # ------------------------------------------------------------
    # DEBUG OUTPUT
    # ------------------------------------------------------------
    if verbose:

        print(
            f"[INFO] Selected "
            f"{len(selected)} screenshot(s) "
            f"for module={module}"
        )

        for p in selected:
            print(
                "    ",
                os.path.basename(p)
            )

    return selected

# =============================================================================
# API key handling (multi-key fallback)
def get_claude_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")


def claude_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

# =============================================================================
# Gemini LLM
# =============================================================================
def _extract_json_anywhere(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    end = None
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return None

    blob = text[start:end]
    try:
        return json.loads(blob)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

def claude_call_json(
    prompt: str,
    verbose: bool = False,
    tag: str = ""
):
    if not claude_enabled():
        if verbose:
            print("[Claude] ANTHROPIC_API_KEY not found.")
        return None

    try:
        if verbose:
            print(
                f"[Claude] Using model "
                f"{get_claude_model()} for {tag}"
            )

        response = client.messages.create(
            model=get_claude_model(),
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text = response.content[0].text.strip()

        obj = _extract_json_anywhere(text)

        if obj:
            return obj

        if verbose:
            print(
                "[Claude] Model returned invalid JSON."
            )

    except Exception as e:
        if verbose:
            print(
                f"[Claude] API Error: {e}"
            )

    return None
def llm_reason_all(module_name: str, payload: Dict[str, Any], risk_score: Optional[float], findings: str = "", verbose: bool = False) -> Optional[Dict[str, Any]]:
    # ✅ Check for PRE-STRUCTURED schema (user's preferred format)
    if not claude_enabled():
        return {
            "explanation_bullets": [
                "LLM analysis is disabled.",
                "This report was generated from wrapper results only."
            ],
            "conclusion": "No AI explanation was generated.",
            "suggested_actions": [
                "Review the verification results.",
                "Perform manual verification if required."
            ]
        }
    if isinstance(payload.get("explanation_bullets"), list) and payload.get("conclusion"):
        if verbose:
            print(f"[INFO] Using existing structured schema for {module_name}")
        return {
            "explanation_bullets": payload.get("explanation_bullets")[:8],
            "conclusion": payload.get("conclusion"),
            "suggested_actions": payload.get("suggested_actions", [])[:5]
        }

    # If we have pre-formatted findings (piped), use them!
    if findings and "|" in findings:
        bullets = [x.strip() for x in findings.split("|") if x.strip()]
        if bullets:
            if verbose:
                print(f"[INFO] Using pre-formatted findings for {module_name}")
            return {
                "explanation_bullets": bullets[:8],
                "conclusion": bullets[-1] if bullets else "Verification completed.",
                "suggested_actions": ["Review the detailed findings above.", "Consult with a legal expert if risk score is high."]
            }

    # Skip LLM call if this module failed completely (e.g. missing file)
    if risk_score is None and (payload.get("error") or payload.get("status") in ("FAILED", "MISSING_INPUT")):
        if verbose:
            print(f"[LLM] Skipping {module_name} due to missing input/error.")
        return {
            "explanation_bullets": ["Document was not provided or extraction failed completely."],
            "conclusion": "No analysis could be performed.",
            "suggested_actions": ["Upload the required document to receive a full analysis."]
        }

    prompt = f"""
# ROLE

You are a Senior Property Due Diligence Consultant,
Real Estate Legal Advisor,
and Home Buying Risk Assessment Specialist.

# CONTEXT

A prospective home buyer has completed a property verification report.

Your task is to explain the verification results in simple,
non-technical language.

Use ONLY the supplied JSON.

Never invent facts.

# OBJECTIVE

Explain:

• What was verified

• What was found

• Why it matters

• What the buyer should do next

Risk Score Interpretation

0 = Lowest Risk

100 = Highest Risk

If the score is unavailable,

state:

"Score not available."

and explain only the available findings.

# WRITING STYLE

Write for someone with no legal or technical background.

Keep explanations:

• Short

• Clear

• Practical

Avoid legal jargon.

Avoid speculation.

Do not repeat raw JSON.

# REQUIRED OUTPUT

Return ONLY valid JSON.

{{
  "explanation_bullets":[
    "...",
    "...",
    "..."
  ],

  "conclusion":"...",

  "suggested_actions":[
    "...",
    "..."
  ]
}}

# RULES

Explanation bullets

• 3–8 bullets

• One idea per bullet

• Explain the significance of the findings

Conclusion

• 1–2 short sentences

Suggested Actions

• 2–5 practical recommendations

Only recommend actions supported by the supplied findings.

# MODULE

{module_name}

Risk Score (0–100)

{risk_score}

# SOURCE DATA

{json.dumps(payload, ensure_ascii=False, indent=2)}

# FINAL VALIDATION

✓ Use ONLY supplied data.

✓ No invented facts.

✓ Valid JSON only.
""".strip()
    obj = claude_call_json(prompt, verbose=verbose, tag=module_name)
    if not obj:
        return None

    bullets = obj.get("explanation_bullets")
    concl = obj.get("conclusion")
    acts = obj.get("suggested_actions", [])

    if not isinstance(bullets, list) or not isinstance(concl, str):
        return None

    bullets_clean = [clean_text(x) for x in bullets if clean_text(x)]
    acts_clean = [clean_text(x) for x in acts] if isinstance(acts, list) else []
    acts_clean = [x for x in acts_clean if x]

    if len(bullets_clean) < 2:
        return None

    return {
        "explanation_bullets": bullets_clean[:8],
        "conclusion": clean_text(concl),
        "suggested_actions": acts_clean[:6],
    }


# =============================================================================
# Score extraction (still used internally, but NOT displayed)
# =============================================================================
def extract_risk_score(module: str, payload: Dict[str, Any]) -> Tuple[Optional[float], str]:
    MODULE_ALIASES = {
        "occupancy certificate": "oc",
        "oc": "oc",

        "nocs from various departments": "noc",
        "noc": "noc",

        "parking certificate": "parking",
        "parking": "parking",

        "association by laws": "bylaws",
        "bylaws": "bylaws",

        "existing bank loans": "bankloan",
        "bankloan": "bankloan",

        "ec document check": "ec",
        "ec": "ec",

        "builder/developer reputation": "builder",
        "builder": "builder",

        "court cases": "ecourtrisk",
        "ecourtrisk": "ecourtrisk",

        "property tax paid receipts": "bbmp_property_tax",
        "bbmp_property_tax": "bbmp_property_tax",

        "electricity bill": "bescom",
        "bescom": "bescom",

        "water bill": "water",
        "water": "water",

        "title check": "kaveriecrisk",
        "kaveriecrisk": "kaveriecrisk",

        "khata/mutation type verification": "ekhatarisk",
        "ekhatarisk": "ekhatarisk",

        # ============================================================
        # RERA / BDA / BUDA / TUDA
        # ============================================================
        "registration check":
            "rera_approval",

        "rera/bda/buda/tuda/na registration check":
            "rera_approval",

        "rera approval":
            "rera_approval",

        "rera_approval":
            "rera_approval",

        "rera bda buda tuda approval":
            "rera_approval",

        "rera_bda_buda_tuda_approval":
            "rera_approval",
    }

    m = MODULE_ALIASES.get(str(module).lower().strip(), str(module).lower().strip())

    # Failed module
    if (
        payload.get("error")
        or get(payload, "errors.ocr")
        or payload.get("status") in ("FAILED", "MISSING_INPUT")
    ):
        return None, "error_fallback"
    # ================================================================
    # RERA / BDA / BUDA / TUDA
    # ================================================================

    if m == "rera_approval":

        # Primary field from rera_approval_risk.py
        sc = clamp(
            first_number(payload.get("risk"))
        )

        if sc is not None:
            return sc, "risk"

        # Backup fields in case the RERA module is changed later
        for p in (
            "risk_score",
            "final_risk_score",
            "overall_risk_score",
            "python_risk_score",
            "final.risk_score",
            "risk.overall_risk_score",
        ):
            val = get(payload, p) if "." in p else payload.get(p)

            sc = clamp(first_number(val))

            if sc is not None:
                return sc, p

    # Simple wrappers
    if m == "ecourtrisk":
        sc = clamp(
            first_number(
                get(payload, "overall_court_risk.risk_score")
            )
        )
        if sc is not None:
            return sc, "overall_court_risk.risk_score"

        # Backward-compatible fallback for older eCourt output.
        sc = clamp(first_number(payload.get("risk_score")))
        if sc is not None:
            return sc, "risk_score"

    # Simple wrappers
    if m in ("bescom", "water", "kaveriecrisk"):
        sc = clamp(first_number(payload.get("risk_score")))
        if sc is not None:
            return sc, "risk_score"



    # ------------------------------------------------------------
    # BYLAWS
    # wrapperlaw stores the official Python risk here:
    # python_score.risk_score
    # ------------------------------------------------------------
    if m == "bylaws":
        sc = clamp(
            first_number(
                get(payload, "python_score.risk_score")
            )
        )

        if sc is not None:
            return sc, "python_score.risk_score"

        # fallback for older wrapper format
        sc = clamp(
            first_number(
                payload.get("risk_score")
            )
        )

        if sc is not None:
            return sc, "risk_score"
    # Bank Loan
    if m == "bankloan":
        sc = clamp(first_number(get(payload, "risk.overall_risk_score")))
        if sc is not None:
            return sc, "risk.overall_risk_score"

    # OC
    if m == "oc":
        sc = clamp(first_number(get(payload, "scores.blended_risk_score")))
        if sc is not None:
            return sc, "scores.blended_risk_score"

    # Parking
    if m == "parking":
        sc = clamp(first_number(payload.get("combined_risk_score")))
        if sc is not None:
            return sc, "combined_risk_score"

    # Builder
    if m == "builder":
        sc = clamp(first_number(get(payload, "final.risk_score")))
        if sc is not None:
            return sc, "final.risk_score"

    # BBMP
    if m == "bbmp_property_tax":
        sc = clamp(first_number(get(payload, "final.risk_score")))
        if sc is not None:
            return sc, "final.risk_score"

    # EC
    if m == "ec":
        sc = clamp(first_number(get(payload, "executive_summary.risk_score")))
        if sc is not None:
            return sc, "executive_summary.risk_score"

    # eKhata
    if m == "ekhatarisk":
        sc = clamp(first_number(get(payload, "final_assessment.risk_score")))
        if sc is not None:
            return sc, "final_assessment.risk_score"

    # NOC
    if m == "noc":
        sc = clamp(
            first_number(
                get(payload, "overall_risk_score")
            )
        )

        if sc is not None:
            return sc, "overall_risk_score"

    # Generic fallback
    for p in (
        "risk",
        "risk_score",
        "final_assessment.risk_score",
        "final.risk_score",
        "scores.blended_risk_score",
        "combined_risk_score",
        "risk.overall_risk_score",
        "executive_summary.risk_score",
        "project_scores.final.risk_avg",
        "overall_risk_score",
        "final_risk_score",
    ):
        val = get(payload, p) if "." in p else payload.get(p)
        sc = clamp(first_number(val))
        if sc is not None:
            return sc, p

    return None, "not_found"

# =============================================================================
# Visual Flowables
# =============================================================================
class RiskBar(Flowable):
    def __init__(self, width: float, height: float, risk: Optional[float]):
        super().__init__()
        self.w = width
        self.h = height
        self.risk = risk

    def wrap(self, availWidth, availHeight):
        return self.w, self.h

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.canv.setLineWidth(0.7)
        self.canv.setFillColor(colors.white)
        self.canv.rect(0, 0, self.w, self.h, stroke=1, fill=1)

        pad = 1.5
        track_w = self.w - 2 * pad
        track_h = self.h - 2 * pad

        self.canv.setFillColor(colors.HexColor("#E5E7EB"))
        self.canv.rect(pad, pad, track_w, track_h, stroke=0, fill=1)

        fill_w = score_bar_fill(self.risk, track_w)
        bg, _ = risk_color(self.risk)
        self.canv.setFillColor(bg)
        self.canv.rect(pad, pad, fill_w, track_h, stroke=0, fill=1)

        self.canv.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.canv.setLineWidth(0.4)
        for frac in (0.25, 0.50, 0.75):
            x = pad + track_w * frac
            self.canv.line(x, pad, x, pad + track_h)


# =============================================================================
# Header/footer
# =============================================================================
def header_footer(canvas, doc):
    canvas.saveState()

    canvas.setFillColor(colors.HexColor("#0B1220"))
    canvas.rect(0, A4[1] - 1.7 * cm, A4[0], 1.7 * cm, stroke=0, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawString(2 * cm, A4[1] - 1.08 * cm, "🏠 Property Due Diligence Risk Report")

    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#D1D5DB"))
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.08 * cm, "0 best • higher = higher risk")

    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.setFont("Helvetica", 9)
    canvas.drawString(2 * cm, 1.2 * cm, "Generated by Risk Engine")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")

    canvas.restoreState()


# =============================================================================
# Overview Section (Matches overview.pdf)
# =============================================================================
def _add_overview_section(story, summary_rows, results, styles, overall_score, overall_lvl):
    story.append(Spacer(1, -1.0 * cm)) # Move up a bit
    story.append(Paragraph("Property Verification Report", ParagraphStyle("BigTitle", parent=styles["H1"], alignment=1, fontSize=28, spaceAfter=14)))
    
    report_id = results.get("reportId", datetime.now().strftime("%Y%m%d%H%M%S"))
    gen_date = datetime.now().strftime("%m/%d/%Y")
    
    story.append(Paragraph(f"Report ID: {report_id}", ParagraphStyle("SubText", parent=styles["Small"], alignment=1, fontSize=11)))
    story.append(Paragraph(f"Date Generated: {gen_date}", ParagraphStyle("SubText", parent=styles["Small"], alignment=1, fontSize=11)))
    story.append(Spacer(1, 1.2 * cm))
    
    # EXECUTIVE SUMMARY
    story.append(Paragraph("Executive Summary", styles["H2"]))
    summary_text = results.get("summary", "The property has been verified across multiple government and physical databases. Key risk factors have been assessed based on ownership, legal history, and municipal compliance.")
    story.append(Paragraph(summary_text, styles["Body"]))
    story.append(Spacer(1, 0.6 * cm))
    
    # RISK ASSESSMENT
    story.append(Paragraph("Risk Assessment", styles["H2"]))
    color = "#10B981" # Green
    if overall_lvl == "HIGH": color = "#EF4444" # Red
    elif overall_lvl == "MEDIUM": color = "#F59E0B" # Orange
    
    story.append(Paragraph(f'Risk Level: <font color="{color}"><b>{overall_lvl} ({overall_score:.0f}/100)</b></font>', ParagraphStyle("RiskText", parent=styles["Body"], fontSize=12, leading=16)))
    story.append(Spacer(1, 1.0 * cm))
    
    # ALL CHECKS (Flat list, no categorization headers)
    story.append(Paragraph("Verification Details", styles["H2"]))
    story.append(Spacer(1, 4))
    
    # Sort all checks by score descending to highlight issues
    all_checks_sorted = sorted(summary_rows, key=lambda x: (x[1] if x[1] is not None else -1), reverse=True)

    if not all_checks_sorted:
        story.append(Paragraph("• No checks performed.", styles["Body"]))
    
    for check, risk, lvl in all_checks_sorted:
        title = check.get("title", "Check")
        status_color = "#10B981" # Green
        if lvl == "HIGH": status_color = "#EF4444" # Red
        elif lvl == "MEDIUM": status_color = "#F59E0B" # Orange
        
        # Simple description from findings
        findings = check.get("findings", "Verified successfully.")
        desc = findings.split("|")[0].strip() if "|" in findings else findings
        if not desc: desc = "Verification completed."
            
        p_text = f"• <b>{title}</b> <font color='{status_color}'>[{lvl}]</font><br/><font size='9.5' color='#4B5563'>{desc}</font>"
        story.append(Paragraph(p_text, ParagraphStyle("BulletStyle", parent=styles["Body"], leftIndent=12, spaceAfter=10, leading=13)))
    
    story.append(Spacer(1, 0.5 * cm))
        
    story.append(Paragraph("Auto-generated by Landed AI", ParagraphStyle("FooterText", parent=styles["Small"], alignment=1, textColor=colors.HexColor("#9CA3AF"), spaceBefore=20)))
    story.append(PageBreak())

# =============================================================================
# PDF Builder
# =============================================================================
def build_pdf(results: Dict[str, Any], out_pdf: str, verbose: bool, input_json_path: str = "",
              session_id: str = None, screenshot_dir: str = None):

    # ================================================================
    # READ DYNAMIC EXCLUDED CHECKS
    # ================================================================

    meta = results.get("_meta", {})

    if not isinstance(meta, dict):
        meta = {}

    excluded_checks = set(
        meta.get("excludedChecks", [])
    )

    if verbose:
        print(
            "[PDF] Excluded checks:",
            sorted(excluded_checks)
        )

    # ================================================================
    # IF ONLY risk_engine IS PASSED, USE IT
    # ================================================================

    if "risk_engine" in results and "checks" not in results:

        if verbose:
            print(
                "[INFO] No global checks found. "
                "Falling back to risk_engine."
            )

        risk_engine = results.get(
            "risk_engine",
            {}
        )

        if isinstance(risk_engine, dict):

            # In case risk_engine also contains _meta
            risk_engine_meta = risk_engine.get(
                "_meta",
                {}
            )

            if isinstance(
                risk_engine_meta,
                dict
            ):
                excluded_checks.update(
                    risk_engine_meta.get(
                        "excludedChecks",
                        []
                    )
                )

        results = (
            risk_engine
            if isinstance(risk_engine, dict)
            else {}
        )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=14))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#6B7280")))
    styles.add(ParagraphStyle(name="Label", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#111827")))
    styles.add(ParagraphStyle(name="CardTitle", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#111827")))

    if verbose:
        print(f"[INFO] Claude enabled? {claude_enabled()}")
        print(f"[INFO] Claude model: {get_claude_model()}")

    if not claude_enabled():
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found. Please set ANTHROPIC_API_KEY in your .env file."
        )

    extracted: Dict[str, Dict[str, Any]] = {}
    summary_rows = []
    risk_vals = []

    checks = results.get("checks", [])

    if not isinstance(checks, list):
        checks = []
    # ================================================================
    # REMOVE EXCLUDED CHECKS BEFORE PROCESSING
    # ================================================================

    checks = [
        check
        for check in checks
        if isinstance(check, dict)
        and check.get("title") not in excluded_checks
    ]

    if verbose:
        print(
            "[PDF] Checks after initial exclusion:",
            [
                check.get("title")
                for check in checks
            ]
        )
# ALWAYS add wrapper modules also
    for k, v in results.items():

        if k in ("_meta", "dashboard_checks", "risk_engine", "checks"):
            continue

        if not isinstance(v, dict):
            continue

        title_map = {
            "bbmp_property_tax": "Property Tax Paid Receipts",
            "bescom": "Electricity Bill",
            "water": "Water Bill",
            "khata": "Khata/Mutation Type Verification",
            "oc": "Occupancy Certificate",
            "noc": "NOCs from Various Departments",
            "parking": "Parking Certificate",
            "builder": "Builder/Developer Reputation",
            "ec": "EC Document Check",
            "bankloan": "Existing Bank Loans",
            "bylaws": "Association By Laws",
            "ecourtrisk": "Court Cases",
            "kaveriecrisk": "Title Check",
            "ekhatarisk": "Khata/Mutation Type Verification",
            "rera_approval": "Registration Check",
        }

        title = title_map.get(k, k.upper())

        # ============================================================
        # SKIP EXCLUDED WRAPPER MODULES
        # ============================================================

        if title in excluded_checks:
            if verbose:
                print(
                    f"[PDF] Skipping excluded wrapper: {title}"
                )
            continue

        # avoid duplicates
        # Merge wrapper data into existing dashboard check if present
        existing = next(
            (
                c for c in checks
                if isinstance(c, dict) and c.get("title") == title
            ),
            None,
        )

        if existing:
            existing["original_module"] = k
            existing["extracted_data"] = v

            # Since wrapper returned data, this check is applicable
            existing["status"] = "COMPLETED"

        else:
            checks.append({
                "title": title,
                "original_module": k,
                "extracted_data": v,
                "status": "COMPLETED"
            })
    for check in checks:
        if not isinstance(check, dict):
            continue

        title = check.get("title", "Verification Check")
        orig_module = (
            check.get("original_module")
            or check.get("module")
            or check.get("key")
            or title
        )
        extracted_data = check.get("extracted_data")

        if extracted_data:
            payload = extracted_data
            risk, _src = extract_risk_score(orig_module, payload)
        else:
            payload = check
            try:
                risk = float(check.get("score")) if check.get("score") is not None else None
            except Exception:
                risk = None

        findings = check.get("findings", "")

        extracted[title] = {
            "payload": payload,
            "risk": risk,
            "findings": findings
        }

        summary_rows.append((check, risk, risk_level(risk)))
        risk_vals.append(risk)

        if verbose:
            print(f"[SCORE] {title} ({orig_module}): risk={risk}")

    summary_rows_sorted = sorted(
        summary_rows,
        key=lambda x: (x[1] if x[1] is not None else -1),
        reverse=True
    )

    weighted_sum = 0.0
    weight_total = 0.0

    for check_obj, risk, lvl in summary_rows:
        if is_not_applicable(check_obj):
            continue

        if risk is None:
            continue

        title = check_obj.get("title", "").strip()

        weight = CHECK_WEIGHTS.get(title, 0.03)

        weighted_sum += risk * weight
        weight_total += weight

    overall = (weighted_sum / weight_total) if weight_total > 0 else None
    overall_lvl = risk_level(overall)
    overall_em = risk_emoji(overall)
    overall_bg, overall_fg = risk_color(overall)

    doc = SimpleDocTemplate(
        out_pdf,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=2.3 * cm,
        bottomMargin=2.0 * cm
    )

    story = []

    _add_overview_section(
        story,
        summary_rows,
        results,
        styles,
        overall if overall is not None else 0,
        overall_lvl
    )

    story.append(Spacer(1, 0.7 * cm))
    story.append(Paragraph("Property Due Diligence Risk Report", styles["H1"]))
    story.append(Paragraph(
        "This report helps you spot issues that can delay <b>registration</b>, impact <b>home loans</b>, "
        "or create problems during <b>resale</b>. <b>0 is best</b>. <b>Higher score = higher risk</b>.",
        styles["Body"]
    ))
    story.append(Spacer(1, 0.4 * cm))

    cover_card = Table(
        [[
            Paragraph(f"<b>{overall_em} Overall Risk</b><br/>{('%.1f' % overall) if overall is not None else 'N/A'} / 100", styles["Body"]),
            Paragraph(f"<b>{overall_lvl}</b>", ParagraphStyle(
                "CoverBadge",
                parent=styles["Body"],
                fontName="Helvetica-Bold",
                fontSize=12,
                textColor=overall_fg,
                alignment=1
            ))
        ]],
        colWidths=[11.5 * cm, 4.9 * cm]
    )

    cover_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F8FAFC")),
        ("BACKGROUND", (1, 0), (1, 0), overall_bg),
        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#D1D5DB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))

    story.append(cover_card)
    story.append(PageBreak())

    story.append(Paragraph("All checks summary", styles["H2"]))
    story.append(Paragraph("Scan the top rows first. Higher score means higher risk.", styles["Small"]))
    story.append(Spacer(1, 6))

    table_data = [["", "Check", "Score", "Meter", "Level"]]

    for check_obj, risk, lvl in summary_rows_sorted:
        if is_not_applicable(check_obj):
            display_level = "NOT APPLICABLE"
            display_score = "N/A"
            display_meter = "N/A"
            display_icon = "—"
        else:
            display_level = lvl
            display_score = ("%.1f" % risk) if risk is not None else "N/A"
            display_meter = pct_bar(risk)
            display_icon = risk_emoji(risk)

        table_data.append([
            display_icon,
            check_obj.get("title", "Check"),
            display_score,
            display_meter,
            display_level,
        ])
    t = Table(table_data, colWidths=[1.0 * cm, 6.2 * cm, 2.0 * cm, 3.2 * cm, 4.0 * cm])

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1220")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (4, 1), (4, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]

    for i, (_, risk, _) in enumerate(summary_rows_sorted, start=1):
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), risk_tint(risk)))

    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(PageBreak())

    card_width = 16.4 * cm

    for check_obj, risk, lvl in summary_rows_sorted:
        title = check_obj.get("title", "Check")

        # IMPORTANT:
        # Resolve the module again for THIS check.
        # Do not reuse `orig_module` from the earlier scoring loop,
        # because after that loop it contains the last processed module
        # (typically rera_approval).
        current_orig_module = (
            check_obj.get("original_module")
            or check_obj.get("module")
            or check_obj.get("key")
            or title
        )

        payload = extracted[title]["payload"]
        risk = extracted[title]["risk"]

        if is_not_applicable(check_obj):
            em = "—"
            lvl = "NOT APPLICABLE"
            bg, fg = colors.HexColor("#E5E7EB"), colors.black
        else:
            em = risk_emoji(risk)
            lvl = risk_level(risk)
            bg, fg = risk_color(risk)

        title_tbl = Table(
            [[Paragraph(f"{em}  {title}", ParagraphStyle(
                "ModTitle",
                parent=styles["Body"],
                fontName="Helvetica-Bold",
                fontSize=12,
                textColor=colors.white
            ))]],
            colWidths=[card_width]
        )

        title_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0B1220")),
            ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#0B1220")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))

        story.append(title_tbl)
        story.append(Spacer(1, 8))

        score_card = Table(
            [[
                Paragraph(
                    f"<b>Risk score:</b> {('%.1f' % risk) if risk is not None else 'N/A'} / 100<br/>"
                    f"<b>Risk level:</b> {lvl}",
                    styles["Body"]
                ),
                Paragraph(
                    f"<b>{em} {lvl}</b>",
                    ParagraphStyle(
                        "LvlBadge",
                        parent=styles["Body"],
                        fontName="Helvetica-Bold",
                        fontSize=11,
                        textColor=fg,
                        alignment=1
                    )
                )
            ]],
            colWidths=[11.6 * cm, 4.8 * cm]
        )

        score_card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F8FAFC")),
            ("BACKGROUND", (1, 0), (1, 0), bg),
            ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#D1D5DB")),
            ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5E7EB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))

        story.append(score_card)
        story.append(Spacer(1, 8))

        story.append(Paragraph("Risk meter", styles["Label"]))
        story.append(Spacer(1, 4))
        story.append(RiskBar(width=card_width, height=0.55 * cm, risk=risk))
        story.append(Spacer(1, 10))

        findings = extracted[title].get("findings", "")
        llm_obj = llm_reason_all(title, payload, risk, findings=findings, verbose=verbose)

        if llm_obj:
            bullets = [_trim_sentence(x, 170) for x in (llm_obj.get("explanation_bullets") or [])[:6]]
            actions = [_trim_sentence(x, 150) for x in (llm_obj.get("suggested_actions") or [])[:5]]
            conclusion = _trim_sentence(llm_obj.get("conclusion", ""), 240)

            expl_items = [
                ListItem(Paragraph(clean_text(x), styles["Body"]), leftIndent=0)
                for x in bullets
            ]
            expl_list = ListFlowable(expl_items, bulletType="bullet", leftIndent=14)

            if actions:
                act_items = [
                    ListItem(Paragraph(clean_text(x), styles["Body"]), leftIndent=0)
                    for x in actions
                ]
                act_list = ListFlowable(act_items, bulletType="bullet", leftIndent=14)
            else:
                act_list = Paragraph("—", styles["Body"])

            concl_para = Paragraph(f"<b>Conclusion:</b> {clean_text(conclusion)}", styles["Body"])

            story.append(make_card("Explanation", [expl_list], width=card_width, max_height=8.2 * cm, title_style=styles["CardTitle"]))
            story.append(Spacer(1, 10))
            story.append(make_card("Suggested actions", [act_list], width=card_width, max_height=6.2 * cm, title_style=styles["CardTitle"]))
            story.append(Spacer(1, 10))
            story.append(make_card("Summary", [concl_para], width=card_width, max_height=3.6 * cm, title_style=styles["CardTitle"]))
        else:
            story.append(make_card(
                "Explanation",
                [
                    Paragraph("LLM explanation could not be generated, or the module already contains limited data.", styles["Body"]),
                    Paragraph("Review the score, findings, and evidence screenshot manually.", styles["Body"]),
                ],
                width=card_width,
                max_height=8.0 * cm,
                title_style=styles["CardTitle"]
            ))

        screenshots = get_screenshots_for_check(
            current_orig_module,
            input_json_path,
            verbose=verbose,
            session_id=session_id,
            screenshot_dir=screenshot_dir,
        )

        if screenshots:

            story.append(Spacer(1, 10))
            story.append(Paragraph("Evidence / Screenshots", styles["Label"]))
            story.append(Spacer(1, 6))

            for screenshot_path in screenshots:

                if not os.path.exists(screenshot_path):
                    continue

                try:
                    img = Image(screenshot_path)

                    aspect = img.drawHeight / float(img.drawWidth)

                    final_w = card_width
                    final_h = final_w * aspect

                    if final_h > 10 * cm:
                        final_h = 10 * cm
                        final_w = final_h / aspect

                    img.drawWidth = final_w
                    img.drawHeight = final_h

                    img_card = Table([[img]], colWidths=[card_width])
                    img_card.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]))

                    story.append(img_card)
                    story.append(Spacer(1, 8))

                except Exception as e:
                    print(f"[ERROR] Failed to embed image {screenshot_path}: {e}")

        story.append(PageBreak())

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


# =============================================================================
# CLI
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to combined JSON output (risk_report_*.json)")
    ap.add_argument("--out", default=None, help="Output PDF path. Default: same folder as input.")
    ap.add_argument("--verbose", action="store_true", help="Print debug logs (shows API usage).")
    ap.add_argument("--session-id", default=None, dest="session_id", help="Screenshot session ID from main.py run.")
    ap.add_argument("--screenshot-dir", default=None, dest="screenshot_dir", help="Directory where screenshots were saved.")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        results = json.load(f)

    if not isinstance(results, dict):
        raise ValueError("Input JSON must be a dict of module_name -> module_output")

    # Also read _meta embedded by main.py (overrides CLI args if present)
    meta = results.get("_meta", {})
    session_id = args.session_id or meta.get("session_id")
    screenshot_dir = args.screenshot_dir or meta.get("screenshot_dir")

    out_pdf = args.out
    if not out_pdf:
        base = os.path.splitext(os.path.basename(args.input))[0]
        out_pdf = os.path.join(os.path.dirname(args.input) or ".", f"{base}.pdf")

    build_pdf(results, out_pdf, verbose=args.verbose, input_json_path=args.input,
              session_id=session_id, screenshot_dir=screenshot_dir)
    print(f"PDF created: {out_pdf}")


if __name__ == "__main__":
    main()