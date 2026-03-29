#!/usr/bin/env python3
"""
ec_wrapper.py  (Wrapper version of ultra-minimal EC fraud detector) — FIXED

Fixes added (your request):
1) De-dup was too aggressive (unique pages were treated as duplicates)
   - Use higher-res aHash (16x16 => 256-bit)
   - Much stricter threshold (default 2)
   - Optional text-similarity confirmation (default ON) to avoid template collisions

2) OCR improved for Kannada + English and rotation issues
   - Try 0/90/180/270 rotations
   - Pick best rotation by avg OCR confidence
   - Stronger preprocessing for scanned docs
   - Uses kan+eng

Exports:
  run_ec_wrapper(
      pdf_path: str,
      export_files: bool = False,
      export_json_path: str = "risk_report.json",
      images_dir: str = "images",
      output_dir: str = "output",
      force: bool = False,
      dpi: int = 300
  ) -> dict

ENV:
  GEMINI_EC_KEY=your_key
  (optional) TESSERACT_CMD=D:\\ocr\\tesseract.exe
"""

import os
import json
import re
import cv2
import pytesseract
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from PIL import Image
from pdf2image import convert_from_path
from difflib import SequenceMatcher
from google import genai


# ================================ DEFAULTS ================================
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_IMAGES_DIR = "images"
DEFAULT_REPORT_NAME = "risk_report.json"

# If tesseract isn't in PATH, set via env var TESSERACT_CMD or change here
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

MODEL_NAME = "models/gemini-2.0-flash-lite"


# ================================ GEMINI =================================
def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_EC_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_EC_KEY or GEMINI_API_KEY environment variable not set")
    return genai.Client(api_key=api_key)


class LLMClient:
    def __init__(self, client: genai.Client):
        self.client = client

    def generate(self, prompt: str) -> str:
        resp = self.client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return resp.text or ""


# ==================== DETERMINISM & CACHING HELPERS ======================
def compute_text_hash(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def compute_pdf_hash(pdf_path: str) -> str:
    try:
        h = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _cache_path(output_dir: str) -> Path:
    return Path(output_dir) / "._ec_report_cache.json"


def load_cached_report(output_dir: str):
    p = _cache_path(output_dir)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cached_report(output_dir: str, input_hash: str, report: dict):
    try:
        payload = {"input_hash": input_hash, "report": report}
        with open(_cache_path(output_dir), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except Exception:
        pass


# ================================ OCR MODULE ==============================
def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 300) -> list[str]:
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        paths = []
        for i, page in enumerate(pages, 1):
            path = str(Path(output_dir) / f"page_{i}.png")
            page.save(path, "PNG")
            paths.append(path)
        return paths
    except Exception:
        return []


def _preprocess_for_ocr(img_bgr):
    """Preprocess for scanned Kannada+English documents."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # upscale helps small glyphs, especially Kannada
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)

    # denoise + adaptive threshold
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )
    return gray


def _ocr_with_conf(gray_img, lang="kan+eng"):
    """
    OCR with avg confidence, so we can pick best rotation.
    """
    config = "--oem 1 --psm 6"
    data = pytesseract.image_to_data(
        gray_img, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )
    words = [w for w in data.get("text", []) if w and w.strip()]
    text = " ".join(words)

    confs = []
    for c in data.get("conf", []):
        try:
            ci = int(float(c))
            if ci >= 0:
                confs.append(ci)
        except Exception:
            pass
    avg_conf = (sum(confs) / len(confs)) if confs else 0.0
    return text, avg_conf


def ocr_image(image_path: str) -> str:
    """
    Try 0/90/180/270 rotations and choose the best by avg OCR confidence.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return ""

        rotations = [
            img,
            cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(img, cv2.ROTATE_180),
            cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ]

        best_text = ""
        best_conf = -1.0

        for rot in rotations:
            gray = _preprocess_for_ocr(rot)
            text, conf = _ocr_with_conf(gray, lang="kan+eng")
            if conf > best_conf:
                best_conf = conf
                best_text = text

        return best_text or ""
    except Exception:
        return ""


# ============================ SAFE PAGE DEDUPE ============================
def _get_image_hash(image_path: str, hash_size: int = 16) -> str | None:
    """
    16x16 aHash => 256-bit, reduces false duplicates for template-heavy pages.
    """
    try:
        img = Image.open(image_path)
        img = img.resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        img = img.convert("L")
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        return "".join("1" if p >= avg else "0" for p in pixels)
    except Exception:
        return None


def remove_duplicate_pages(
    image_paths: list[str],
    threshold: int = 2,               # STRICT: avoid losing unique pages
    require_text_check: bool = True,  # confirm via OCR snippet similarity
) -> tuple[list[str], int]:

    if not image_paths:
        return [], 0

    unique_paths: list[str] = []
    duplicates = 0
    kept: list[dict] = []  # [{"path":..., "hash":..., "text":...}]

    for path in image_paths:
        img_hash = _get_image_hash(path, hash_size=16)
        if not img_hash:
            continue

        snippet = ""
        if require_text_check:
            snippet = (ocr_image(path) or "")[:2000]

        is_dup = False
        for item in kept:
            exp_hash = item["hash"]
            dist = sum(c1 != c2 for c1, c2 in zip(img_hash, exp_hash))

            # If hashes are extremely close, only then consider dedupe
            if dist <= threshold:
                if not require_text_check:
                    is_dup = True
                    break

                prev_text = item.get("text", "") or ""
                if prev_text and snippet:
                    sim = SequenceMatcher(None, prev_text, snippet).ratio()
                    if sim >= 0.95:
                        is_dup = True
                        break
                else:
                    # no reliable text => do NOT dedupe (safer)
                    pass

        if is_dup:
            duplicates += 1
        else:
            kept.append({"path": path, "hash": img_hash, "text": snippet})
            unique_paths.append(path)

    return unique_paths, duplicates


# ==================== TRANSACTION DEDUP (same as your script) =============
def canonical_transaction(tx: dict) -> dict:
    return {
        "transaction_date": tx.get("transaction_date") or "",
        "transaction_type": (tx.get("transaction_type") or "OTHER").upper(),
        "seller_name": (tx.get("seller_name") or "").strip(),
        "buyer_name": (tx.get("buyer_name") or "").strip(),
        "consideration_value": float(tx.get("consideration_value") or 0),
        "registration_number": tx.get("registration_number") or None,
    }


def dedupe_transactions(transactions: list[dict]) -> list[dict]:
    seen_regs = {}
    seen_fp = set()
    unique = []

    for tx in transactions:
        c = canonical_transaction(tx)
        reg = c.get("registration_number")
        if reg:
            if reg in seen_regs:
                continue
            seen_regs[reg] = c
            unique.append(c)
            continue

        fp = json.dumps(c, sort_keys=True)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        unique.append(c)

    def sort_key(t):
        return (
            t.get("transaction_date") or "",
            t.get("registration_number") or "",
            t.get("seller_name") or "",
            t.get("buyer_name") or "",
            t.get("consideration_value") or 0,
        )

    unique.sort(key=sort_key)
    return unique


# ================================ LLM PARSE ===============================
def parse_ec_with_llm(llm: LLMClient, ec_text: str) -> dict:
    if not ec_text or not ec_text.strip():
        return {"transactions": []}

    prompt = f"""Extract ALL property transactions from this OCR-extracted Encumbrance Certificate text.

For each transaction extract:
- transaction_date: Date in YYYY-MM-DD format
- transaction_type: One of SALE, AGREEMENT_TO_SELL, GIFT, MORTGAGE, RELEASE, LEASE, PARTITION, SETTLEMENT, EXCHANGE, POWER_OF_ATTORNEY, WILL, RELINQUISHMENT, or OTHER
- seller_name: Full name of seller/executant
- buyer_name: Full name of buyer/claimant
- consideration_value: Numeric value (extract the number only, no currency symbols)
- registration_number: Document registration number

IMPORTANT:
- Include "AGREEMENT TO SELL" or "AGREEMENT_TO_SELL" as transaction_type when found
- Extract ALL transactions, even if consideration value is very low (like 1.0)
- Include transactions involving minors or guardians
- Be thorough - don't skip any transaction entries

Output MUST be valid JSON with "transactions" array. No explanations, no markdown formatting, just pure JSON.

Example format:
{{"transactions": [{{"transaction_date": "2016-12-06", "transaction_type": "AGREEMENT_TO_SELL", "seller_name": "...", "buyer_name": "...", "consideration_value": 1.0, "registration_number": "INR-1-06640-2016-17"}}]}}

OCR Text:
{ec_text}"""

    response = llm.generate(prompt)

    try:
        match = re.search(r"```json\s*(\{.*\})", response, re.DOTALL)
        if match:
            response = match.group(1)

        start, end = response.find("{"), response.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found")

        parsed = json.loads(response[start: end + 1])
        if "transactions" not in parsed:
            parsed = {"transactions": parsed if isinstance(parsed, list) else []}
        return parsed
    except Exception:
        return {"transactions": []}


# ================================ VALIDATION ==============================
def validate_transactions(transactions):
    if not isinstance(transactions, list):
        return []
    valid = []

    VALID_TYPES = {
        "SALE", "GIFT", "MORTGAGE", "RELEASE", "LEASE", "PARTITION",
        "AGREEMENT_TO_SELL", "AGREEMENT", "SETTLEMENT", "EXCHANGE",
        "POWER_OF_ATTORNEY", "WILL", "RELINQUISHMENT", "OTHER"
    }

    for tx in transactions:
        try:
            if not isinstance(tx, dict):
                continue

            tx_date = str(tx.get("transaction_date", "")).strip()
            if tx_date:
                try:
                    datetime.strptime(tx_date, "%Y-%m-%d")
                except Exception:
                    continue

            seller = str(tx.get("seller_name", "")).strip()
            buyer = str(tx.get("buyer_name", "")).strip()
            if not seller and not buyer:
                continue

            tx_type = str(tx.get("transaction_type", "OTHER")).strip().upper()
            tx_type = tx_type.replace(" ", "_")
            if "AGREEMENT" in tx_type and "SELL" in tx_type:
                tx_type = "AGREEMENT_TO_SELL"
            elif tx_type not in VALID_TYPES:
                tx_type = "OTHER"

            tx["transaction_type"] = tx_type
            tx["consideration_value"] = float(tx.get("consideration_value", 0)) if tx.get("consideration_value") else 0
            tx["registration_number"] = tx.get("registration_number")
            valid.append(tx)
        except Exception:
            continue

    return valid


# ============================ RULE-BASED RISK =============================
def calculate_risk(transactions):
    score, flags = 0, []
    if not transactions:
        return score, flags

    sales = [t for t in transactions if t.get("transaction_type") in ["SALE", "AGREEMENT_TO_SELL"]]

    if len(sales) >= 3:
        score += 30
        flags.append(f"Multiple sales/agreements detected ({len(sales)} transactions)")

    if len(sales) >= 2:
        dated_sales = [s for s in sales if s.get("transaction_date")]
        dated_sales.sort(key=lambda x: x["transaction_date"])
        for i in range(len(dated_sales) - 1):
            try:
                d1 = datetime.strptime(dated_sales[i]["transaction_date"], "%Y-%m-%d")
                d2 = datetime.strptime(dated_sales[i + 1]["transaction_date"], "%Y-%m-%d")
                if 0 < (d2 - d1).days < 365:
                    score += 25
                    flags.append(f"Rapid resale ({(d2 - d1).days} days)")
                    break
            except Exception:
                pass

    sellers = Counter(t.get("seller_name", "").strip() for t in sales if t.get("seller_name"))
    if any(v > 1 for v in sellers.values()):
        score += 20
        repeated = [name for name, count in sellers.items() if count > 1]
        flags.append(f"Repeated seller detected: {repeated[0][:50]}...")

    low_value_count = len([t for t in sales if 0 < float(t.get("consideration_value", 0) or 0) < 100])
    if low_value_count >= 2:
        score += 15
        flags.append(f"Multiple transactions with suspiciously low consideration values ({low_value_count} transactions)")

    minor_keywords = ["minor", "minors", "guardian", "natural guardian"]
    minor_transactions = [
        t for t in transactions
        if any(
            kw in (str(t.get("buyer_name", "")).lower() + " " + str(t.get("seller_name", "")).lower())
            for kw in minor_keywords
        )
    ]
    if minor_transactions:
        score += 10
        flags.append(f"Transactions involving minors detected ({len(minor_transactions)} transactions)")

    return min(score, 100), flags


# ================================ AI RISK ================================
def calculate_ai_risk(llm: LLMClient, transactions, rule_score):
    if not transactions:
        return {
            "ai_risk_score": 0,
            "risk_level": "LOW",
            "risk_indicators": ["No transactions"],
            "pattern_analysis": "Empty set",
            "recommendation": "No action",
            "confidence": "HIGH",
        }

    prompt = f"""Analyze this transaction data for fraud risk (0-100 score):
Transactions: {json.dumps(transactions[:10], indent=2)}
Rule Score: {rule_score}/100
Total: {len(transactions)} trans, {len([t for t in transactions if t.get('transaction_type') == 'SALE'])} sales

Response JSON:
{{"ai_risk_score": <0-100>, "risk_level": "<LOW|MEDIUM|HIGH>", "risk_indicators": [...],
"pattern_analysis": "<text>", "recommendation": "<text>", "confidence": "<HIGH|MEDIUM|LOW>"}}"""

    response = llm.generate(prompt)
    try:
        match = re.search(r"```json\s*(\{.*\})", response, re.DOTALL)
        if match:
            response = match.group(1)
        start, end = response.find("{"), response.rfind("}")
        if start != -1 and end != -1:
            return json.loads(response[start: end + 1])
        return {"ai_risk_score": rule_score, "risk_level": "UNKNOWN", "confidence": "LOW"}
    except Exception:
        return {
            "ai_risk_score": rule_score,
            "risk_level": "UNKNOWN",
            "risk_indicators": [],
            "pattern_analysis": "",
            "recommendation": "",
            "confidence": "LOW",
        }


def _get_action_items(risk_level, recommendation):
    if risk_level == "HIGH":
        return [
            "Escalate to compliance team immediately",
            "Conduct detailed manual review of all transactions",
            "Verify seller and buyer identities",
            "Check for signs of money laundering",
            recommendation or "Recommend legal review",
        ]
    elif risk_level == "MEDIUM":
        return [
            "Flag document for further investigation",
            "Review high-value transactions in detail",
            "Cross-check with official property records",
            recommendation or "Recommend supervisory review",
        ]
    else:
        return [
            "Document appears to have low fraud indicators",
            "Standard processing permitted",
            "Maintain record for audit trail",
        ]


# ================================ QUALITY GATE ==============================
def _extraction_failed_guard(total_pages: int, text_len: int, extracted_tx: int) -> bool:
    """
    True when it's likely extraction failed (scanned/ocr issues) and 0 tx is suspicious.
    """
    if total_pages >= 5 and extracted_tx == 0:
        if text_len < 1500:
            return True
        return True
    return False


# ================================ WRAPPER ================================
def run_ec_wrapper(
    pdf_path: str,
    export_files: bool = False,
    export_json_path: str = DEFAULT_REPORT_NAME,
    images_dir: str = DEFAULT_IMAGES_DIR,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    force: bool = False,
    dpi: int = 300,
    session_id: str = None,
    screenshot_dir: str = None,
    tesseract_cmd: str = None
) -> dict:
    """
    Wrapper entry: returns the full report dict.
    """
    pdf_path = str(pdf_path)
    if not Path(pdf_path).exists():
        return {"document_type": "EC", "error": f"PDF not found: {pdf_path}"}

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    client = _get_client()
    llm = LLMClient(client)

    # cache
    pdf_hash = compute_pdf_hash(pdf_path)
    cached = load_cached_report(output_dir)
    if (not force) and cached and pdf_hash and cached.get("input_hash") == pdf_hash:
        report = cached.get("report", {})
        if export_files:
            with open(Path(output_dir) / export_json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, sort_keys=True)
        return report

    # 1) pdf -> images
    image_paths = pdf_to_images(pdf_path, images_dir, dpi=dpi)
    if not image_paths:
        return {"document_type": "EC", "error": "PDF to image conversion failed"}

    # Save first page as screenshot for report
    if screenshot_dir and session_id and image_paths:
        import shutil
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"ec_result_{session_id}.png")
        shutil.copy(image_paths[0], screenshot_path)
        print(f"DEBUG: Saved EC screenshot to {screenshot_path}")

    # 2) dedup (SAFE MODE)
    unique_paths, duplicate_count = remove_duplicate_pages(
        image_paths,
        threshold=2,
        require_text_check=True
    )

    # 3) OCR with page separators (helps LLM keep structure)
    ec_text_parts = []
    for i, path in enumerate(unique_paths, 1):
        ec_text_parts.append(f"\n\n===== PAGE {i} =====\n")
        ec_text_parts.append(ocr_image(path))
    ec_text = "".join(ec_text_parts).strip()

    # hash for cache
    input_hash = pdf_hash if pdf_hash else compute_text_hash(ec_text)

    # 4) parse transactions via LLM
    llm_output = parse_ec_with_llm(llm, ec_text)
    raw_tx = llm_output.get("transactions", []) if isinstance(llm_output, dict) else []
    extracted_count = len(raw_tx)

    # 5) validate + dedupe
    transactions = validate_transactions(raw_tx)
    transactions = dedupe_transactions(transactions)

    # 6) rule scoring
    rule_score, rule_flags = calculate_risk(transactions)

    # 7) ai scoring
    ai_result = calculate_ai_risk(llm, transactions, rule_score)
    ai_score = int(ai_result.get("ai_risk_score", 0) or 0)

    # combine scores (same logic)
    if ai_score >= 70:
        final_score = int((ai_score * 0.8) + (rule_score * 0.2))
    else:
        final_score = int((ai_score * 0.6) + (rule_score * 0.4))

    if final_score >= 70:
        final_level = "HIGH"
    elif final_score >= 40:
        final_level = "MEDIUM"
    else:
        final_level = "LOW"

    # QUALITY GATE: stop false "LOW 0" when extraction likely failed
    if _extraction_failed_guard(total_pages=len(image_paths), text_len=len(ec_text), extracted_tx=extracted_count):
        final_level = "UNKNOWN"
        final_score = 50
        ai_result = {
            "ai_risk_score": ai_score,
            "risk_level": "UNKNOWN",
            "risk_indicators": ["Extraction likely failed (0 transactions from multi-page EC)"],
            "pattern_analysis": "Extraction quality gate triggered",
            "recommendation": "Rerun with better OCR / check orientation / improve parsing",
            "confidence": "LOW",
        }

    report = {
        "document_type": "EC",
        "report_metadata": {
            "report_type": "EC Fraud Detection Report",
            "generated_date": datetime.now().isoformat(),
            "analysis_system": "EC Multiple Sales LLM Analysis",
            "api_provider": "Google Gemini 2.5 Flash",
        },
        "executive_summary": {
            "risk_level": final_level,
            "risk_score": final_score,
            "confidence": "HIGH" if ai_result.get("confidence") == "HIGH" else "MEDIUM",
            "recommendation": ai_result.get("recommendation", "Manual review recommended"),
            "summary": f"Based on analysis of {len(transactions)} validated transactions, the document shows {final_level} fraud risk.",
        },
        "document_analysis": {
            "total_pages_processed": len(image_paths),
            "unique_pages_after_deduplication": len(unique_paths),
            "duplicate_pages_removed": duplicate_count,
        },
        "transaction_analysis": {
            "total_transactions_extracted": len(raw_tx),
            "valid_transactions": len(transactions),
            "invalid_transactions": max(0, len(raw_tx) - len(transactions)),
            "breakdown_by_type": {
                "sales": len([t for t in transactions if t.get("transaction_type") == "SALE"]),
                "agreements_to_sell": len([t for t in transactions if t.get("transaction_type") == "AGREEMENT_TO_SELL"]),
                "mortgages": len([t for t in transactions if t.get("transaction_type") == "MORTGAGE"]),
                "gifts": len([t for t in transactions if t.get("transaction_type") == "GIFT"]),
                "releases": len([t for t in transactions if t.get("transaction_type") == "RELEASE"]),
                "leases": len([t for t in transactions if t.get("transaction_type") == "LEASE"]),
                "others": len([
                    t for t in transactions
                    if t.get("transaction_type") not in ["SALE", "AGREEMENT_TO_SELL", "MORTGAGE", "GIFT", "RELEASE", "LEASE"]
                ]),
            },
            "total_consideration_value": sum(
                float(t.get("consideration_value", 0) or 0)
                for t in transactions
                if t.get("transaction_type") in ["SALE", "AGREEMENT_TO_SELL"]
            ),
        },
        "rule_based_analysis": {
            "score": rule_score,
            "method": "Pattern Detection (3 rules)",
            "rules": {
                "multiple_sales": "3+ sales: +30 points",
                "rapid_resale": "Sale within 365 days: +25 points",
                "repeated_seller": "Same seller multiple times: +20 points",
            },
            "flags_detected": rule_flags,
        },
        "ai_analysis": {
            "score": ai_score,
            "method": "Google Gemini AI Analysis",
            "risk_level": ai_result.get("risk_level", "UNKNOWN"),
            "confidence": ai_result.get("confidence", "UNKNOWN"),
            "risk_indicators": ai_result.get("risk_indicators", []),
            "pattern_analysis": ai_result.get("pattern_analysis", ""),
            "recommendation": ai_result.get("recommendation", ""),
        },
        "final_assessment": {
            "combined_score": final_score,
            "scoring_methodology": {
                "rule_based_weight": 0.2 if ai_score >= 70 else 0.4,
                "ai_weight": 0.8 if ai_score >= 70 else 0.6,
                "formula": "Final = (AI_Score × 0.8) + (Rule_Score × 0.2) when AI >= 70, else (AI_Score × 0.6) + (Rule_Score × 0.4)",
                "note": "Higher AI weight applied when AI detects high-risk patterns",
            },
            "risk_classification": final_level,
            "risk_range": {"low": "0-39", "medium": "40-69", "high": "70-100"},
            "action_required": "YES" if final_level in ["HIGH", "MEDIUM"] else "NO",
            "next_steps": _get_action_items(final_level if final_level != "UNKNOWN" else "MEDIUM", ai_result.get("recommendation", "")),
        },
        "detailed_findings": {
            "sample_transactions": transactions[:5] if transactions else [],
            "transaction_count": len(transactions),
        },
    }

    # save
    if export_files:
        out_path = Path(output_dir) / export_json_path
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)

    save_cached_report(output_dir, input_hash, report)
    return report


# ================================ OPTIONAL CLI ================================
def main():
    parser = argparse.ArgumentParser(description="EC Fraud Detection Wrapper CLI")
    parser.add_argument("pdf", nargs="?", default="input/ec.pdf", help="Path to EC PDF")
    parser.add_argument("--force", action="store_true", help="Force regeneration ignoring cache")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--images", default=DEFAULT_IMAGES_DIR, help="Images directory")
    parser.add_argument("--export", action="store_true", help="Export JSON report file")
    parser.add_argument("--report", default=DEFAULT_REPORT_NAME, help="Report JSON filename")
    args = parser.parse_args()

    report = run_ec_wrapper(
        pdf_path=args.pdf,
        export_files=args.export,
        export_json_path=args.report,
        images_dir=args.images,
        output_dir=args.out,
        force=args.force,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
