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
  GEMINI_REPORT_KEY_2=...
  GEMINI_REPORT_KEY_3=...
  GEMINI_REPORT_KEY_4=...

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
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

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


def get_screenshot_for_check(check_title: str, input_json_path: str, verbose: bool = False,
                             session_id: str = None, screenshot_dir: str = None) -> Optional[str]:
    """
    Look for a screenshot matching the check title.
    Uses an explicit mapping from check title keywords to screenshot filename prefixes.
    Returns the MOST RECENT matching screenshot.
    """
    # Explicit mapping: keywords in check title -> screenshot file prefix
    TITLE_TO_PREFIX = {
        "ec": "landeed_result",
        "encumbrance": "landeed_result",
        "bescom": "bescom_result",
        "electricity": "bescom_result",
        "water": "water_result",
        "waterbill": "water_result",
        "water bill": "water_result",
        "khata": "khata_result",
        "bbmp khata": "khata_result",
        "noc": "noc_result",
        "no objection": "noc_result",
        "oc": "oc_result",
        "occupancy": "oc_result",
        "parking": "parking_result",
        "landeed": "landeed_result",
        "bbmp": "bbmp_result",
        "property tax": "bbmp_result",
    }

    title_lower = check_title.lower()
    prefix = None
    for keyword, p in TITLE_TO_PREFIX.items():
        if keyword in title_lower:
            prefix = p
            break

    if not prefix:
        # Fallback: slugify title and use as prefix
        prefix = re.sub(r"[^a-z0-9]+", "_", title_lower).strip("_") + "_result"

    if verbose:
        print(f"[DEBUG] Screenshot lookup: title='{check_title}' -> prefix='{prefix}'")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Build the list of directories to search, including the explicit screenshot_dir if provided
    screenshots_dirs = []
    if screenshot_dir and os.path.isdir(screenshot_dir):
        screenshots_dirs.append(screenshot_dir)
    screenshots_dirs += [
        os.path.join(base_dir, "screenshots"),
        os.path.join(base_dir, "backend", "screenshots"),
        os.path.join(base_dir, "riskwrapper", "screenshots"),
    ]

    # Try extracting session_id from JSON filename if not passed explicitly
    if not session_id:
        json_name = os.path.basename(input_json_path)
        m = re.search(r"(\d{13}|\d{8}_\d{6})", json_name)
        if m:
            session_id = m.group(1)
        if verbose:
            print(f"[DEBUG] Found session_id {session_id} from JSON path")

    candidates = []
    for sdir in screenshots_dirs:
        if not os.path.exists(sdir):
            continue
        for fname in os.listdir(sdir):
            low = fname.lower()
            if not low.endswith(".png"):
                continue
            if not low.startswith(prefix.lower()):
                continue
            full_path = os.path.join(sdir, fname)
            mtime = os.path.getmtime(full_path)
            # Prefer session-id match
            priority = 1 if (session_id and session_id in low) else 0
            candidates.append((priority, mtime, full_path))

    if not candidates:
        if verbose:
            print(f"[DEBUG] No screenshot found for prefix='{prefix}'")
        return None

    # Sort: prefer session-id match first, then newest file
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = candidates[0][2]
    if verbose:
        print(f"[INFO] Using screenshot: {best}")
    return best


# =============================================================================
# API key handling (multi-key fallback)
# =============================================================================
def get_all_api_keys() -> List[str]:
    """
    Read Gemini keys from both backend/.env and riskwrapper/.env.
    Tried sequentially in this order.
    """
    # Load riskwrapper env additionally so we have access to all those keys
    rw_env = os.path.join(os.path.dirname(__file__), "..", "riskwrapper", ".env")
    if os.path.exists(rw_env):
        load_dotenv(rw_env)
        
    keys = [
        os.getenv("GEMINI_REPORT_KEY_1"),
        os.getenv("GEMINI_REPORT_KEY_2"),
        os.getenv("GEMINI_REPORT_KEY_3"),
        os.getenv("GEMINI_REPORT_KEY_4"),
        os.getenv("GEMINI_BESCOM"),
        os.getenv("GEMINI_EXTRACTION_KEY"),
        os.getenv("GEMINI_RISK_KEY"),
        os.getenv("GEMINI_API_KEY_EXTRACT"),
        os.getenv("GEMINI_API_KEY_RISK"),
        os.getenv("GEMINI_EXTRACT_KEY"),
        os.getenv("GEMINI_SCORE_KEY"),
        os.getenv("GEMINI_API_KEY3"),
        os.getenv("GEMINI_BYLAW"),
        os.getenv("GEMINI_BUILDER_API_KEY"),
        os.getenv("GEMINI_EC_KEY"),
        os.getenv("GEMINI_Bank_Extract"),
        os.getenv("GEMINI_BANK_RISK"),
        os.getenv("GEMINI_KHATA_KEY"),
        # Backward-compatible fallbacks:
        os.getenv("GEMINI_REPORT_KEY"),
        os.getenv("GEMINI_API_KEY"),
    ]
    return [k for k in keys if k and str(k).strip()]


def gemini_enabled() -> bool:
    return len(get_all_api_keys()) > 0


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


def gemini_call_json(prompt: str, verbose: bool = False, tag: str = "") -> Optional[Dict[str, Any]]:
    """
    Calls Gemini using KEY1->KEY2->KEY3->KEY4 fallback.
    If one key is exhausted or fails, tries the next.
    """
    keys = get_all_api_keys()
    if not keys:
        if verbose:
            print("[LLM] No Gemini keys found in environment.")
        return None

    try:
        from google import genai  # pip install google-genai
    except Exception:
        if verbose:
            print("[LLM] google-genai not installed. Run: pip install google-genai")
        return None

    # Try each key sequentially
    last_err = None
    for idx, api_key in enumerate(keys, start=1):
        try:
            if verbose:
                print(f"[LLM] Using Gemini key #{idx} for {tag}")

            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = (resp.text or "").strip()

            obj = _extract_json_anywhere(text)
            if obj is not None:
                return obj

            if verbose:
                print(f"[LLM] Key #{idx} returned no valid JSON. Trying next key...")

        except Exception as e:
            last_err = e
            if verbose:
                print(f"[LLM] Key #{idx} failed: {e}")
            continue

    if verbose and last_err:
        print(f"[LLM] All Gemini keys failed. Last error: {last_err}")

    return None


def llm_reason_all(module_name: str, payload: Dict[str, Any], risk_score: Optional[float], findings: str = "", verbose: bool = False) -> Optional[Dict[str, Any]]:
    # ✅ Check for PRE-STRUCTURED schema (user's preferred format)
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
You are writing for a home buyer (non-technical). Produce a clear explanation for this check.

Rules:
- Do NOT invent facts. Use only the JSON.
- Write in simple English.
- Mention: 0 is best, higher score = higher risk.
- If score is null, say "Score not available" and focus on findings.
- Keep it short and user-friendly.

Output MUST be strict JSON with keys:
- explanation_bullets: list of 3 to 8 short sentences
- conclusion: 1 to 2 sentences
- suggested_actions: list of 2 to 5 actionable steps

Module: {module_name}
Risk score (0-100, higher worse): {risk_score}

JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
    obj = gemini_call_json(prompt, verbose=verbose, tag=module_name)
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
    m = module.lower()

    # Prioritize fatal errors or missing input.
    if payload.get("error") or get(payload, "errors.ocr") or payload.get("status") in ("FAILED", "MISSING_INPUT"):
        return None, "error_fallback"

    if m in ("bescom", "water"):
        return clamp(first_number(payload.get("risk_score"))), "risk_score"

    if m == "oc":
        return clamp(first_number(get(payload, "scores.blended_risk_score"))), "scores.blended_risk_score"

    if m == "bankloan":
        return clamp(first_number(get(payload, "risk.overall_risk_score"))), "risk.overall_risk_score"

    if m == "khata":
        for p in ("ai_analysis.final_risk_score", "rule_based_risk.risk_score", "final_assessment.final_risk_score"):
            sc = clamp(first_number(get(payload, p)))
            if sc is not None:
                return sc, p

    if m == "parking":
        for p in (
            "combined_risk_score_0_100_higher_is_riskier",
            "combined_risk_score",
            "deterministic_risk_score_0_100_higher_is_riskier",
            "llm_risk_score_stable_0_100_higher_is_riskier",
        ):
            sc = clamp(first_number(payload.get(p)))
            if sc is not None:
                return sc, p

    if m == "builder":
        sc = clamp(first_number(get(payload, "final.score")))
        if sc is not None:
            return sc, "final.score"
        sc = clamp(first_number(get(payload, "rule_based.risk_score")))
        if sc is not None:
            return sc, "rule_based.risk_score"
        sc = clamp(first_number(payload.get("score")))
        if sc is not None:
            return sc, "score"

    for p in (
        "risk_score",
        "final_risk_score",
        "overall_risk_score",
        "final.risk_score",
        "executive_summary.risk_score",
        "project_scores.final.risk_avg",
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
    # ✅ Fix: If merged report was passed, use the merged 'checks' array
    # instead of just the 'risk_engine' subset.
    if "risk_engine" in results and "checks" not in results:
        if verbose:
            print("[INFO] No global 'checks' found. Falling back to 'risk_engine' key.")
        results = results["risk_engine"]

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=14))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#6B7280")))
    styles.add(ParagraphStyle(name="Label", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#111827")))
    styles.add(ParagraphStyle(name="CardTitle", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#111827")))

    if verbose:
        print(f"[INFO] LLM enabled? {gemini_enabled()}")
        print("[INFO] Gemini keys detected:", len(get_all_api_keys()))

    if not gemini_enabled():
        raise RuntimeError(
            "Gemini API key not found. Set one of:\n"
            "  GEMINI_REPORT_KEY_1..4 (recommended)\n"
            "  or GEMINI_REPORT_KEY / GEMINI_API_KEY / GOOGLE_API_KEY"
        )

    extracted: Dict[str, Dict[str, Any]] = {}
    summary_rows: List[Tuple[str, Optional[float], str]] = []
    risk_vals: List[Optional[float]] = []

    # Build uniform chunks out of raw dictionaries if the unified 'checks' array wasn't passed 
    # (e.g., when run directly via pipeline.py)
    checks = results.get("checks")
    if not checks:
        checks = []
        for k, v in results.items():
            if isinstance(v, dict):
                checks.append({
                    "title": k.upper(),
                    "original_module": k,
                    "extracted_data": v
                })

    for check in checks:
        title = check.get("title", "Verification Check")
        orig_module = check.get("original_module", title)
        extracted_data = check.get("extracted_data")

        if extracted_data:
            payload = extracted_data
            risk, _src = extract_risk_score(orig_module, payload)
        else:
            payload = check
            # ✅ Standardized: 'score' is now Risk Score (higher is worst)
            sc = check.get("score")
            try:
                risk = float(sc) if sc is not None else None
            except Exception:
                risk = None

        # Re-check if we can get findings for LLM summary
        findings = check.get("findings", "")
        extracted[title] = {"payload": payload, "risk": risk, "findings": findings}
        # ✅ Store the check dictionary so we can access title/category in summary
        summary_rows.append((check, risk, risk_level(risk)))
        risk_vals.append(risk)

        if verbose:
            print(f"[SCORE] {title} ({orig_module}): risk={risk}")

    # Sort by risk score descending (highest risk first)
    summary_rows_sorted = sorted(summary_rows, key=lambda x: (x[1] if x[1] is not None else -1), reverse=True)

    overall = safe_avg(risk_vals)
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
    story: List[Any] = []
    
    _add_overview_section(story, summary_rows, results, styles, overall, overall_lvl)

    # COVER (User-focused, no legend, no JSON talk)
    story.append(Spacer(1, 0.7 * cm))
    story.append(Paragraph("🏠 Property Due Diligence Risk Report", styles["H1"]))
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
                "CoverBadge", parent=styles["Body"], fontName="Helvetica-Bold",
                fontSize=12, textColor=overall_fg, alignment=1
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
    story.append(Spacer(1, 0.35 * cm))

    info_card = Table(
        [
            [Paragraph("📌 <b>How to use this report</b>", styles["CardTitle"])],
            [Paragraph(
                "• Each check has a <b>risk score (0–100)</b>: <b>0 is best</b>, higher means higher risk.<br/>"
                "• Start with items marked <b>🚨 High Risk</b> and finish the suggested actions before paying or signing.<br/>"
                "• If any High Risk item is unresolved, consult a property lawyer before proceeding.",
                styles["Body"]
            )],
            [Paragraph(f"🕒 <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Small"])],
        ],
        colWidths=[16.4 * cm]
    )
    info_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#D1D5DB")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(info_card)

    # ✅ Legend removed intentionally
    story.append(PageBreak())

    # SUMMARY (with Category column)
    story.append(Paragraph("📊 All checks summary", styles["H2"]))
    story.append(Paragraph("Scan the top rows first (higher score = higher risk).", styles["Small"]))
    story.append(Spacer(1, 6))

    table_data = [["", "Check", "Score", "Meter", "Level"]]
    for check_obj, risk, lvl in summary_rows_sorted:
        title = check_obj.get("title", "Check")
        table_data.append([
            risk_emoji(risk),
            title,
            ("%.1f" % risk) if risk is not None else "N/A",
            pct_bar(risk),
            lvl,
        ])

    # Adjust widths for 5 columns: [Emoji, Title, Score, Meter, Level]
    t = Table(table_data, colWidths=[1.0 * cm, 6.2 * cm, 2.0 * cm, 3.2 * cm, 4.0 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1220")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 1), (0, -1), "CENTER"), # Emoji
        ("ALIGN", (2, 1), (2, -1), "CENTER"), # Score
        ("ALIGN", (4, 1), (4, -1), "CENTER"), # Level
        # Styles from the removed summary_card wrapper
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#D1D5DB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]
    for i, (_, risk, _) in enumerate(summary_rows_sorted, start=1):
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), risk_tint(risk)))

    t.setStyle(TableStyle(style_cmds))

    story.append(t)
    story.append(PageBreak())

    # DETAIL PAGES
    card_width = 16.4 * cm

    for check_obj, risk, lvl in summary_rows_sorted:
        title = check_obj.get("title", "Check")
        payload = extracted[title]["payload"]
        risk = extracted[title]["risk"]

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

        story.append(Paragraph("📈 Risk meter", styles["Label"]))
        story.append(Spacer(1, 4))
        story.append(RiskBar(width=card_width, height=0.55 * cm, risk=risk))
        story.append(Spacer(1, 10))

        findings = extracted[title].get("findings", "")
        llm_obj = llm_reason_all(title, payload, risk, findings=findings, verbose=verbose)

        if llm_obj:
            bullets = [_trim_sentence(x, 170) for x in (llm_obj.get("explanation_bullets") or [])[:6]]
            actions = [_trim_sentence(x, 150) for x in (llm_obj.get("suggested_actions") or [])[:5]]
            conclusion = _trim_sentence(llm_obj.get("conclusion", ""), 240)

            expl_items = [ListItem(Paragraph(f"✅ {clean_text(x)}", styles["Body"]), leftIndent=0) for x in bullets]
            expl_list = ListFlowable(expl_items, bulletType="bullet", leftIndent=14)

            if actions:
                act_items = [ListItem(Paragraph(f"👉 {clean_text(x)}", styles["Body"]), leftIndent=0) for x in actions]
                act_list = ListFlowable(act_items, bulletType="bullet", leftIndent=14)
            else:
                act_list = Paragraph("—", styles["Body"])

            concl_para = Paragraph(f"🧾 <b>Conclusion:</b> {clean_text(conclusion)}", styles["Body"])

            story.append(make_card("🧠 Explanation", [expl_list], width=card_width, max_height=8.2 * cm, title_style=styles["CardTitle"]))
            story.append(Spacer(1, 10))
            story.append(make_card("🛠️ Suggested actions", [act_list], width=card_width, max_height=6.2 * cm, title_style=styles["CardTitle"]))
            story.append(Spacer(1, 10))
            story.append(make_card("💡 Summary", [concl_para], width=card_width, max_height=3.6 * cm, title_style=styles["CardTitle"]))
        else:
            story.append(make_card(
                "🧠 Explanation",
                [
                    Paragraph("LLM explanation could not be generated (API error or invalid response).", styles["Body"]),
                    Paragraph("🛠️ Try re-running with --verbose and confirm GEMINI_REPORT_KEY_1..4 are set in .env.", styles["Body"]),
                ],
                width=card_width,
                max_height=8.0 * cm,
                title_style=styles["CardTitle"]
            ))

        # 📸 Screenshot Section
        screenshot_path = get_screenshot_for_check(title, input_json_path, verbose=verbose,
                                                    session_id=session_id, screenshot_dir=screenshot_dir)
        if screenshot_path and os.path.exists(screenshot_path):
            if verbose:
                print(f"[INFO] Embedding screenshot: {screenshot_path}")
            
            story.append(Spacer(1, 10))
            story.append(Paragraph("📸 Evidence / Screenshot", styles["Label"]))
            story.append(Spacer(1, 6))
            
            try:
                img = Image(screenshot_path)
                # Aspect ratio scaling
                img_w, img_h = img.drawWidth, img.drawHeight
                aspect = img_h / float(img_w)
                
                final_w = card_width
                final_h = final_w * aspect
                
                # If too tall for the page, scale down
                max_page_h = 10.0 * cm
                if final_h > max_page_h:
                    final_h = max_page_h
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
    print(f"✅ PDF created: {out_pdf}")


if __name__ == "__main__":
    main()
