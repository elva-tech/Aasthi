#!/usr/bin/env python3
"""
ec_wrapper.py  (EC / Encumbrance Check Wrapper)

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
  ANTHROPIC_API_KEY=your_key
  (optional) TESSERACT_CMD=D:\\ocr\\tesseract.exe
"""

import base64


from PIL import Image
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
from pdf2image import convert_from_path
from difflib import SequenceMatcher
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ================================ DEFAULTS ================================
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_IMAGES_DIR = "images"
DEFAULT_REPORT_NAME = "risk_report.json"

# If tesseract isn't in PATH, set via env var TESSERACT_CMD or change here
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

MODEL_NAME = "claude-opus-4-7"


# ================================ GEMINI =================================

def _get_client() -> Anthropic:

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    return Anthropic(api_key=api_key)

import os

import os
import base64
from openai import OpenAI


# ============================================================
# GEMMA / OLLAMA CLIENT
# ============================================================

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

EXTRACTION_MODEL = "gemma3:4b"
RISK_MODEL = "claude-opus-4-7"


# ============================================================
# IMAGE / DATA EXTRACTION
# ============================================================

class LLMClient:

    def __init__(self):
        self.client = qwen_client

    def generate(
        self,
        prompt: str,
        image_path: str = None
    ) -> str:

        if image_path:

            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(
                    f.read()
                ).decode("utf-8")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an information extraction engine. "
                        "Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url":
                                f"data:image/png;base64,{image_b64}"
                            },
                        },
                    ],
                },
            ]

        else:

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an information extraction engine. "
                        "Return ONLY valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ]

        response = self.client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=messages,
            temperature=0,
            extra_body={
                "options": {
                    "num_ctx": 8192
                }
            },
        )

        return response.choices[0].message.content


# ============================================================
# GEMINI RISK ANALYSIS CLIENT
# ============================================================

# ================================ CLAUDE RISK ANALYSIS CLIENT ================================

class ClaudeClient:

    def __init__(self):
        self.client = _get_client()

    def generate(self, prompt: str) -> str:

        response = self.client.messages.create(
            model=RISK_MODEL,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Anthropic returns content as a list of blocks
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text

        return ""


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


def _ocr_cache_path(output_dir: str) -> Path:
    return Path(output_dir) / "ec_ocr_cache.json"


def load_ocr_cache(output_dir: str, input_hash: str):
    path = _ocr_cache_path(output_dir)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("input_hash") != input_hash:
            return None

        return data.get("pages", [])

    except Exception as e:
        print(f"[OCR CACHE WARNING] Could not load OCR cache: {e}")
        return None


def save_ocr_cache(output_dir: str, input_hash: str, pages):
    path = _ocr_cache_path(output_dir)

    try:
        payload = {
            "input_hash": input_hash,
            "saved_at": datetime.now().isoformat(),
            "pages": pages,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        print(f"[OCR CACHE] Saved → {path}")

    except Exception as e:
        print(f"[OCR CACHE ERROR] Could not save OCR cache: {e}")


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
        import pymupdf

        doc = pymupdf.open(pdf_path)
        paths = []

        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=dpi, alpha=False)

            path = str(Path(output_dir) / f"page_{i}.png")
            pix.save(path)

            paths.append(path)

        doc.close()
        return paths

    except Exception as e:
        print(f"PDF to image conversion error: {e}")
        return []


def _preprocess_for_ocr(img_bgr):
    """
    Enhanced preprocessing for Kannada + English scanned EC documents.
    """

    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Upscale small text
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # Remove noise
    gray = cv2.fastNlMeansDenoising(gray, None, h=15)

    # Improve contrast
    gray = cv2.equalizeHist(gray)

    # Adaptive threshold
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )

    # Remove isolated noise
    gray = cv2.medianBlur(gray, 3)

    return gray


def _ocr_with_conf(gray_img, lang="kan+eng"):

    configs = ["--oem 1 --psm 6", "--oem 1 --psm 11", "--oem 1 --psm 12"]

    best_text = ""
    best_conf = -1

    for cfg in configs:

        data = pytesseract.image_to_data(
            gray_img, lang=lang, config=cfg, output_type=pytesseract.Output.DICT
        )

        words = [w for w in data["text"] if w.strip()]

        text = " ".join(words)

        confs = []

        for c in data["conf"]:
            try:
                c = float(c)
                if c >= 0:
                    confs.append(c)
            except:
                pass

        avg = sum(confs) / len(confs) if confs else 0

        if avg > best_conf:
            best_conf = avg
            best_text = text

    return best_text, best_conf


def ocr_image(image_path: str) -> str:
    """
    OCR scanned EC page.
    Try 0/90/180/270 rotations.
    Prefer Kannada + English when available,
    otherwise fall back to English.
    """

    img = cv2.imread(image_path)

    if img is None:
        print(f"[OCR ERROR] Cannot read image: {image_path}")
        return ""

    rotations = [
        ("0", img),
        ("90CW", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
        ("180", cv2.rotate(img, cv2.ROTATE_180)),
        ("90CCW", cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)),
    ]

    best_text = ""
    best_conf = -1.0

    for rotation_name, rot in rotations:

        gray = _preprocess_for_ocr(rot)

        # First try Kannada + English
        try:
            text, conf = _ocr_with_conf(gray, lang="kan+eng")

            print(
                f"[OCR] rotation={rotation_name}, "
                f"lang=kan+eng, chars={len(text)}, conf={conf:.2f}"
            )

        except Exception as e:

            print(f"[OCR WARNING] kan+eng failed: {e}")

            # Fallback to English
            try:
                text, conf = _ocr_with_conf(gray, lang="eng")

                print(
                    f"[OCR] rotation={rotation_name}, "
                    f"lang=eng, chars={len(text)}, conf={conf:.2f}"
                )

            except Exception as e2:

                print(f"[OCR ERROR] eng also failed: {e2}")

                continue

        if text and conf > best_conf:
            best_conf = conf
            best_text = text

    print(
        f"[OCR BEST] {os.path.basename(image_path)} -> "
        f"{len(best_text)} chars, confidence={best_conf:.2f}"
    )

    return best_text or ""


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
    threshold: int = 2,  # STRICT: avoid losing unique pages
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
def parse_ec_page_with_qwen(
    llm: LLMClient, page_text: str, image_path: str, page_number: int
) -> dict:

    schema = {
        "transactions": [
            {
                "transaction_date": None,
                "transaction_type": None,
                "seller_name": None,
                "buyer_name": None,
                "consideration_value": None,
                "registration_number": None,
            }
        ]
    }

    prompt = f"""
You are extracting data from a Karnataka Encumbrance Certificate (EC).

You are given:
1. The ACTUAL PAGE IMAGE.
2. OCR text from the same page.

The PAGE IMAGE is the primary source.
OCR is only supporting information.

PAGE NUMBER:
{page_number}

OCR TEXT:
{page_text}

Extract ONLY transaction rows that are actually visible in this page's EC table.

The table columns are approximately:

1. Sl. No.
2. Property Description
3. Transaction Date
4. Market Value / Consideration
5. Executant / Seller
6. Claimant / Buyer
7. Document / Registration Number
8. Other registration information

Return ONLY this JSON:

{json.dumps(schema, indent=2)}

STRICT RULES:

- Read the table visually from the image.
- Do NOT rely only on OCR.
- Preserve the relationship between columns.
- Do NOT move text from one column into another.
- Do NOT treat property-description text as a registration number.
- Do NOT treat survey numbers as registration numbers.
- Do NOT invent missing information.
- If a field cannot be read, use null.
- Never guess a number.
- Preserve names as they appear in the document as closely as possible.
- Extract every transaction row visible on this page.
- If the same transaction continues from a previous page, extract only the information actually visible on this page.
- Do NOT create a transaction merely because a page contains repeated table headers.
- Do NOT create duplicate transactions from repeated page content.
- transaction_type must be one of:
  SALE, GIFT, MORTGAGE, RELEASE, LEASE,
  PARTITION, AGREEMENT_TO_SELL, AGREEMENT,
  SETTLEMENT, EXCHANGE, POWER_OF_ATTORNEY,
  WILL, RELINQUISHMENT, OTHER
- consideration_value must be numeric when clearly visible.
- registration_number must contain ONLY the actual document/registration number.
- Return valid JSON only.
"""

    response = llm.generate(prompt, image_path=image_path)

    try:

        match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)

        if match:
            response = match.group(1)

        start = response.find("{")
        end = response.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("No JSON object found")

        parsed = json.loads(response[start : end + 1])

        if not isinstance(parsed, dict):
            return {"transactions": []}

        transactions = parsed.get("transactions", [])

        if not isinstance(transactions, list):
            transactions = []

        return {"transactions": transactions}

    except Exception as e:

        print("=" * 80)
        print(f"QWEN PAGE {page_number} JSON ERROR")
        print(e)
        print("RAW RESPONSE:")
        print(response)
        print("=" * 80)

        return {"transactions": []}


# ================================ VALIDATION ==============================
def validate_transactions(transactions):
    if not isinstance(transactions, list):
        return []
    valid = []

    VALID_TYPES = {
        "SALE",
        "GIFT",
        "MORTGAGE",
        "RELEASE",
        "LEASE",
        "PARTITION",
        "AGREEMENT_TO_SELL",
        "AGREEMENT",
        "SETTLEMENT",
        "EXCHANGE",
        "POWER_OF_ATTORNEY",
        "WILL",
        "RELINQUISHMENT",
        "OTHER",
    }

    for tx in transactions:
        try:
            if not isinstance(tx, dict):
                continue

            tx_date = str(tx.get("transaction_date", "")).strip()

            if tx_date:

                parsed_date = None

                date_formats = [
                    "%Y-%m-%d",
                    "%d-%m-%Y",
                    "%d/%m/%Y",
                    "%d/%b/%Y",
                    "%d/%B/%Y",
                    "%d-%b-%Y",
                    "%d-%B-%Y",
                ]

                for fmt in date_formats:

                    try:
                        parsed_date = datetime.strptime(tx_date, fmt)
                        break

                    except Exception:
                        pass

                if parsed_date:
                    tx_date = parsed_date.strftime("%Y-%m-%d")

                else:
                    # Do not discard the transaction
                    # merely because OCR/Qwen used another
                    # recognizable date representation.
                    tx_date = tx_date
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
            tx["consideration_value"] = (
                float(tx.get("consideration_value", 0))
                if tx.get("consideration_value")
                else 0
            )
            tx["registration_number"] = tx.get("registration_number")
            valid.append(tx)
        except Exception:
            continue

    return valid


# ============================ RULE-BASED RISK =============================
def _parse_tx_date(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d/%b/%Y",
        "%d/%B/%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None


def _ec_transaction_summary(transactions):
    """Create a compact deterministic summary for EC risk analysis."""
    counts = Counter(
        (t.get("transaction_type") or "OTHER").upper() for t in transactions
    )

    sales = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() in {"SALE", "AGREEMENT_TO_SELL"}
    ]
    mortgages = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() == "MORTGAGE"
    ]
    releases = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() in {"RELEASE", "RELINQUISHMENT"}
    ]
    poa = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() == "POWER_OF_ATTORNEY"
    ]

    sellers = Counter(
        str(t.get("seller_name") or "").strip()
        for t in sales
        if str(t.get("seller_name") or "").strip()
    )
    buyers = Counter(
        str(t.get("buyer_name") or "").strip()
        for t in sales
        if str(t.get("buyer_name") or "").strip()
    )

    dated_sales = []
    for tx in sales:
        d = _parse_tx_date(tx.get("transaction_date"))
        if d:
            dated_sales.append((d, tx))
    dated_sales.sort(key=lambda x: x[0])

    rapid_resales = []
    for i in range(len(dated_sales) - 1):
        days = (dated_sales[i + 1][0] - dated_sales[i][0]).days
        if 0 < days < 365:
            rapid_resales.append(
                {
                    "days": days,
                    "earlier_transaction": dated_sales[i][1],
                    "later_transaction": dated_sales[i + 1][1],
                }
            )

    return {
        "total_transactions": len(transactions),
        "breakdown_by_type": dict(counts),
        "sales": len(sales),
        "mortgages": len(mortgages),
        "releases": len(releases),
        "poa_transactions": len(poa),
        "repeated_sellers": [
            {"name": name[:100], "count": count}
            for name, count in sellers.items()
            if count > 1
        ],
        "repeated_buyers": [
            {"name": name[:100], "count": count}
            for name, count in buyers.items()
            if count > 1
        ],
        "rapid_resales": [
            {
                "days": x["days"],
                "earlier_date": x["earlier_transaction"].get("transaction_date"),
                "later_date": x["later_transaction"].get("transaction_date"),
                "earlier_registration": x["earlier_transaction"].get(
                    "registration_number"
                ),
                "later_registration": x["later_transaction"].get("registration_number"),
            }
            for x in rapid_resales
        ],
        "mortgage_transactions": mortgages,
        "release_transactions": releases,
        "poa_transactions_detail": poa,
    }


def _match_mortgages_to_releases(transactions):
    """
    Conservative mortgage/release analysis.

    A release is treated as evidence of discharge when it follows a mortgage.
    We do not invent a one-to-one legal linkage when the EC does not provide it.
    """
    mortgages = []
    releases = []

    for tx in transactions:
        tx_type = (tx.get("transaction_type") or "").upper()
        if tx_type == "MORTGAGE":
            mortgages.append(tx)
        elif tx_type in {"RELEASE", "RELINQUISHMENT"}:
            releases.append(tx)

    dated_mortgages = []
    for tx in mortgages:
        d = _parse_tx_date(tx.get("transaction_date"))
        dated_mortgages.append((d, tx))

    dated_releases = []
    for tx in releases:
        d = _parse_tx_date(tx.get("transaction_date"))
        dated_releases.append((d, tx))

    unresolved = []
    matched = []

    for mortgage_date, mortgage in dated_mortgages:
        later_releases = [
            (d, r)
            for d, r in dated_releases
            if d is not None and (mortgage_date is None or d >= mortgage_date)
        ]

        if later_releases:
            release_date, release = min(later_releases, key=lambda x: x[0])
            matched.append(
                {
                    "mortgage_registration": mortgage.get("registration_number"),
                    "mortgage_date": mortgage.get("transaction_date"),
                    "release_registration": release.get("registration_number"),
                    "release_date": release.get("transaction_date"),
                    "status": "POTENTIALLY_RELEASED",
                }
            )
        else:
            unresolved.append(
                {
                    "mortgage_registration": mortgage.get("registration_number"),
                    "mortgage_date": mortgage.get("transaction_date"),
                    "status": "NO_LATER_RELEASE_FOUND_IN_EC",
                }
            )

    return {
        "mortgages": len(mortgages),
        "releases": len(releases),
        "potentially_released": matched,
        "unresolved_mortgages": unresolved,
    }


def calculate_risk(transactions):
    """
    Rule-based EC/encumbrance risk only.

    IMPORTANT:
    - This is NOT a title-chain score.
    - Ordinary historical sales are not automatically treated as fraud.
    - Mortgage/release, rapid resale, POA and unresolved-encumbrance
      patterns receive more weight.
    """
    if not transactions:
        return 0, ["No EC transactions extracted"]

    score = 0
    flags = []

    sales = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() in {"SALE", "AGREEMENT_TO_SELL"}
    ]

    mortgages = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() == "MORTGAGE"
    ]

    poa = [
        t
        for t in transactions
        if (t.get("transaction_type") or "").upper() == "POWER_OF_ATTORNEY"
    ]

    # Multiple sales are an informational/review indicator, not automatic fraud.
    if len(sales) >= 3:
        score += 10
        flags.append(
            f"Multiple historical sales/agreements detected ({len(sales)}); "
            "review the transaction chain."
        )

    # Rapid resale is a stronger anomaly.
    dated_sales = []
    for tx in sales:
        d = _parse_tx_date(tx.get("transaction_date"))
        if d:
            dated_sales.append((d, tx))
    dated_sales.sort(key=lambda x: x[0])

    for i in range(len(dated_sales) - 1):
        days = (dated_sales[i + 1][0] - dated_sales[i][0]).days
        if 0 < days < 365:
            score += 20
            flags.append(f"Rapid resale detected ({days} days between sales)")
            break

    # Repeated seller is a review indicator, not proof of fraud.
    sellers = Counter(
        str(t.get("seller_name") or "").strip()
        for t in sales
        if str(t.get("seller_name") or "").strip()
    )
    repeated = [name for name, count in sellers.items() if count > 1]
    if repeated:
        score += 10
        flags.append(
            f"Repeated seller detected ({len(repeated)} seller(s)); review history."
        )

    # Multiple mortgages are materially more important.
    if len(mortgages) >= 2:
        score += 20
        flags.append(f"Multiple mortgage transactions detected ({len(mortgages)}).")

    # POA is not inherently fraudulent; flag for document-level verification.
    if poa:
        score += 10
        flags.append(
            f"Power-of-Attorney transaction(s) detected ({len(poa)}); "
            "verify the underlying POA and authority."
        )

    # Suspiciously tiny consideration values.
    low_value_count = sum(
        1 for t in sales if 0 < float(t.get("consideration_value", 0) or 0) < 100
    )
    if low_value_count >= 2:
        score += 15
        flags.append(
            f"Multiple unusually low consideration values detected ({low_value_count})."
        )

    # Missing registration numbers are a review issue, not automatic fraud.
    missing_reg = sum(
        1 for t in transactions if not str(t.get("registration_number") or "").strip()
    )
    if missing_reg:
        flags.append(
            f"{missing_reg} transaction(s) have no readable registration number; "
            "verify against the original EC."
        )

    # Mortgage without a later release is a high-value review indicator.
    enc = _match_mortgages_to_releases(transactions)
    unresolved = enc["unresolved_mortgages"]
    if unresolved:
        score += min(25, 15 + 5 * max(0, len(unresolved) - 1))
        flags.append(
            f"{len(unresolved)} mortgage transaction(s) have no later release/"
            "relinquishment found in the supplied EC."
        )

    return min(score, 100), flags


# ================================ AI RISK ================================
def calculate_ai_risk(llm: ClaudeClient, transactions, rule_score):
    """Claude analysis restricted to EC/encumbrance patterns."""

    summary = _ec_transaction_summary(transactions)
    encumbrance = _match_mortgages_to_releases(transactions)

    # Send a compact, deterministic representation rather than blindly
    # truncating to the first 10 transactions.
    compact_transactions = [
        {
            "date": t.get("transaction_date"),
            "type": t.get("transaction_type"),
            "seller": t.get("seller_name"),
            "buyer": t.get("buyer_name"),
            "consideration": t.get("consideration_value"),
            "registration_number": t.get("registration_number"),
        }
        for t in transactions
    ]

    prompt = f"""
You are an Encumbrance Certificate (EC) risk analyst for an Indian
real-estate buyer.

IMPORTANT SCOPE:
Analyze ONLY the supplied EC transaction/encumbrance information.

Do NOT perform a title-chain opinion.
Do NOT decide whether the seller legally owns the property.
Do NOT treat the EC as proof of clear title.
Title ownership is handled by a separate Title Check module.

Evaluate:
1. Mortgages and whether later releases/relinquishments appear.
2. Potential unresolved encumbrances.
3. Multiple mortgages.
4. Rapid resale.
5. Repeated sellers/buyers.
6. POA transactions requiring verification.
7. Suspicious consideration values.
8. Missing registration numbers.
9. Transaction timeline anomalies.
10. Other observable EC transaction anomalies.

IMPORTANT:
- Multiple ordinary historical sales are NOT automatically high risk.
- A mortgage followed by a release is normally less concerning than an
  apparently unresolved mortgage.
- Missing OCR information is not fraud.
- Never invent a transaction, owner, lender, court case, or legal fact.
- Give reasons only when supported by the supplied data.
- If the EC data is incomplete, say that verification of the original
  document is required.

DETERMINISTIC RULE SCORE:
{rule_score}

EC SUMMARY:
{json.dumps(summary, indent=2, ensure_ascii=False)}

MORTGAGE / RELEASE ANALYSIS:
{json.dumps(encumbrance, indent=2, ensure_ascii=False)}

TRANSACTIONS:
{json.dumps(compact_transactions, indent=2, ensure_ascii=False)}

Return ONLY valid JSON:

{{
  "ai_risk_score": 0,
  "risk_level": "LOW|MEDIUM|HIGH",
  "risk_indicators": [],
  "pattern_analysis": "",
  "recommendation": "",
  "confidence": "HIGH|MEDIUM|LOW"
}}

Risk interpretation:
0-39 = LOW
40-69 = MEDIUM
70-100 = HIGH
""".strip()

    response = llm.generate(prompt)

    try:
        match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
        if match:
            response = match.group(1)

        start_json = response.find("{")
        end_json = response.rfind("}")

        if start_json != -1 and end_json != -1:
            result = json.loads(response[start_json : end_json + 1])

            score = result.get("ai_risk_score")
            try:
                result["ai_risk_score"] = max(0, min(100, int(score)))
            except Exception:
                result["ai_risk_score"] = None

            return result

    except Exception as e:
        print(f"[CLAUDE EC RISK ERROR] {e}")

    return {
        "ai_risk_score": None,
        "risk_level": "UNKNOWN",
        "risk_indicators": [],
        "pattern_analysis": "",
        "recommendation": "Manual EC review recommended because AI analysis failed.",
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
def _extraction_failed_guard(
    total_pages: int, text_len: int, extracted_tx: int
) -> bool:
    """
    Returns True if EC transaction extraction likely failed.
    """

    # Multi-page EC but no transactions extracted
    if total_pages >= 5 and extracted_tx == 0:
        return True

    return False


def create_ec_evidence_screenshot(
    image_paths,
    output_path,
    transactions=None,
    screenshot_dir=None,
    session_id=None
):
    """
    Save exactly 2 screenshots corresponding to
    two actual EC transaction pages.

    Uses Qwen transaction _source_page values.
    """

    if not transactions:
        print(
            "[EC SCREENSHOT] No transactions available."
        )
        return []

    selected_pages = []

    # --------------------------------------------
    # Select 2 UNIQUE transaction source pages
    # --------------------------------------------
    for tx in transactions:

        if not isinstance(tx, dict):
            continue

        page_number = tx.get(
            "_source_page"
        )

        if page_number is None:
            continue

        try:
            page_number = int(
                page_number
            )
        except (TypeError, ValueError):
            continue

        if page_number not in selected_pages:
            selected_pages.append(
                page_number
            )

        if len(selected_pages) == 2:
            break

    if not selected_pages:
        print(
            "[EC SCREENSHOT] "
            "No transaction source pages found."
        )
        return []

    # --------------------------------------------
    # If only one transaction page exists,
    # save only one screenshot rather than
    # pretending there are two transactions.
    # --------------------------------------------
    selected_pages = selected_pages[:2]

    saved = []

    # --------------------------------------------
    # If screenshot_dir is supplied, save
    # individual transaction screenshots
    # --------------------------------------------
    if screenshot_dir and session_id:

        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        for index, page_number in enumerate(
            selected_pages,
            start=1
        ):

            page_index = page_number - 1

            if (
                page_index < 0
                or page_index >= len(image_paths)
            ):
                print(
                    f"[EC SCREENSHOT] Invalid "
                    f"page {page_number}"
                )
                continue

            source_path = image_paths[
                page_index
            ]

            output_file = os.path.join(
                screenshot_dir,
                (
                    f"ec_result_{index}_"
                    f"{session_id}.png"
                )
            )

            try:

                img = Image.open(
                    source_path
                ).convert("RGB")

                img.save(
                    output_file,
                    format="PNG",
                    optimize=True
                )

                saved.append(
                    output_file
                )

                print(
                    f"[EC SCREENSHOT] "
                    f"Transaction {index} "
                    f"→ PDF page {page_number}"
                )

            except Exception as e:

                print(
                    f"[EC SCREENSHOT] Failed "
                    f"page {page_number}: {e}"
                )

    return saved

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
    tesseract_cmd: str = None,
) -> dict:
    """
    Wrapper entry: returns the full report dict.
    """
    pdf_path = str(pdf_path)
    if not Path(pdf_path).exists():
        return {"document_type": "EC", "error": f"PDF not found: {pdf_path}"}

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    qwen = LLMClient()
    # claude = ClaudeClient()
    # cache
    pdf_hash = compute_pdf_hash(pdf_path)
    input_hash = pdf_hash
    cached = load_cached_report(output_dir)
    if (not force) and cached and pdf_hash and cached.get("input_hash") == pdf_hash:
        report = cached.get("report", {})

        # Cache must never prevent creation of the EC evidence screenshots.
        # The report cache predates the screenshot-page metadata, so use the
        # cached evidence_pages when available. If it is not available, fall
        # back to the first two PDF pages so a current-session screenshot is
        # still produced instead of silently skipping it.
        if screenshot_dir and session_id:
            try:
                os.makedirs(screenshot_dir, exist_ok=True)

                cached_pages = report.get("evidence_pages", [])
                if not isinstance(cached_pages, list):
                    cached_pages = []

                image_paths = pdf_to_images(
                    pdf_path,
                    images_dir,
                    dpi=dpi
                )

                if image_paths:
                    selected_pages = []
                    for page in cached_pages:
                        try:
                            page = int(page)
                        except (TypeError, ValueError):
                            continue
                        if 1 <= page <= len(image_paths) and page not in selected_pages:
                            selected_pages.append(page)

                    # Old cache files do not contain evidence_pages.
                    # Do not silently skip screenshots in that case.
                    if not selected_pages:
                        selected_pages = list(range(1, min(2, len(image_paths)) + 1))

                    saved = []
                    for index, page_number in enumerate(selected_pages[:2], start=1):
                        source_path = image_paths[page_number - 1]
                        output_file = os.path.join(
                            screenshot_dir,
                            f"ec_result_{index}_{session_id}.png"
                        )
                        Image.open(source_path).convert("RGB").save(
                            output_file,
                            format="PNG",
                            optimize=True
                        )
                        saved.append(output_file)

                    print(
                        f"[EC SCREENSHOT] Cache hit: saved "
                        f"{len(saved)} screenshot(s)"
                    )
                    for path in saved:
                        print(f"[EC SCREENSHOT] FILE: {path}")

            except Exception as e:
                print(
                    f"[EC SCREENSHOT ERROR] Cache-hit screenshot failed: "
                    f"{type(e).__name__}: {e}"
                )

        if export_files:
            with open(Path(output_dir) / export_json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, sort_keys=True)
        return report

    # 1) pdf -> images
    image_paths = pdf_to_images(pdf_path, images_dir, dpi=dpi)
    if not image_paths:
        return {"document_type": "EC", "error": "PDF to image conversion failed"}

    # ============================================================
    # EC TRANSACTION SCREENSHOTS
    # Exactly 2 transaction pages
    # ============================================================

    # 2) dedup (SAFE MODE)
    unique_paths, duplicate_count = remove_duplicate_pages(
        image_paths, threshold=2, require_text_check=False
    )

    # 3) OCR with page separators (helps LLM keep structure)
    # 3) OCR page-by-page
    ec_text_parts = []
    page_ocr_data = []

    cached_ocr_pages = load_ocr_cache(
        output_dir,
        pdf_hash
    )

    cached_by_page = {}

    if cached_ocr_pages:
        for item in cached_ocr_pages:

            if isinstance(item, dict):

                page_number = item.get("page")

                if page_number:
                    cached_by_page[int(page_number)] = item.get(
                        "text",
                        ""
                    )

        print(
            f"[OCR CACHE] Loaded "
            f"{len(cached_by_page)} cached pages"
        )

    for i, path in enumerate(unique_paths, 1):

        if i in cached_by_page:

            page_text = cached_by_page[i]

            print(
                f"[OCR CACHE] Page {i} reused "
                f"({len(page_text)} characters)"
            )

        else:

            print(
                f"\n[OCR START] Processing page {i}"
            )

            page_text = ocr_image(path)

            print(
                f"[OCR DONE] Page {i}: "
                f"{len(page_text)} characters"
            )

            cached_by_page[i] = page_text

            # Save OCR immediately after this page
            save_ocr_cache(
                output_dir,
                pdf_hash,
                [
                    {
                        "page": page,
                        "text": text
                    }
                    for page, text in sorted(
                        cached_by_page.items()
                    )
                ]
            )

        page_ocr_data.append({
            "page": i,
            "text": page_text
        })

        ec_text_parts.append(
            f"\n\n===== PAGE {i} =====\n"
        )

        ec_text_parts.append(page_text)
    ec_text = "".join(ec_text_parts).strip()
    # ============================================================
    # 4) QWEN PAGE-BY-PAGE VISUAL TRANSACTION EXTRACTION
    # ============================================================

    all_qwen_transactions = []

    for page in page_ocr_data:

        page_number = page["page"]
        page_text = page["text"]
        path = unique_paths[page_number - 1]

        print("\n" + "=" * 90)
        print(f"🔍 QWEN ANALYZING EC PAGE {page_number}")
        print("=" * 90)

        try:

            page_result = parse_ec_page_with_qwen(qwen, page_text, path, page_number)

            page_transactions = page_result.get("transactions", [])

            if not isinstance(page_transactions, list):
                page_transactions = []

            print(
                f"📦 Page {page_number}: "
                f"{len(page_transactions)} transactions extracted"
            )

            print(json.dumps(page_transactions, indent=2, ensure_ascii=False))

            # Add page number for traceability
            for tx in page_transactions:

                if isinstance(tx, dict):
                    tx["_source_page"] = page_number
                    all_qwen_transactions.append(tx)

        except Exception as e:

            print(f"[QWEN ERROR] Page {page_number}: {e}")

    raw_tx = all_qwen_transactions

    extracted_count = len(raw_tx)

    print(f"Transactions extracted: {extracted_count}")
    # ============================================================
    # EC TRANSACTION SCREENSHOTS
    # Save exactly 2 pages identified by Qwen
    # ============================================================

    if screenshot_dir and session_id:

        try:

            screenshot_paths = create_ec_evidence_screenshot(
                # _source_page is numbered against unique_paths below.
                image_paths=unique_paths,
                output_path=None,
                transactions=raw_tx,
                screenshot_dir=screenshot_dir,
                session_id=session_id
            )

            print(
                f"[EC SCREENSHOT] Saved "
                f"{len(screenshot_paths)} "
                f"transaction screenshot(s)"
            )

            for path in screenshot_paths:
                print(
                    f"[EC SCREENSHOT] FILE: {path}"
                )

        except Exception as e:

            print(
                f"[EC SCREENSHOT ERROR] "
                f"{type(e).__name__}: {e}"
            )
    # ================= QUALITY GATE =================
    # ================= QUALITY GATE =================

    if _extraction_failed_guard(
        total_pages=len(image_paths),
        text_len=len(ec_text),
        extracted_tx=extracted_count,
    ):

        print("\n" + "=" * 90)
        print("❌ QWEN EXTRACTION FAILED")
        print("=" * 90)

        return {
            "document_type": "EC",
            "status": "QWEN_EXTRACTION_FAILED",
            "pages": len(image_paths),
            "unique_pages": len(unique_paths),
            "duplicate_pages": duplicate_count,
            "ocr_characters": len(ec_text),
            "transactions": [],
        }

    # 5) validate + dedupe
    transactions = validate_transactions(raw_tx)
    transactions = dedupe_transactions(transactions)

    print("\n" + "=" * 90)
    print("✅ FINAL VALIDATED QWEN TRANSACTIONS")
    print("=" * 90)

    print(json.dumps(transactions, indent=2, ensure_ascii=False))

    print("=" * 90)

    print(f"Raw Qwen transactions: {len(raw_tx)}")

    print(f"Validated transactions: {len(transactions)}")

    # 6) EC-specific rule scoring
    rule_score, rule_flags = calculate_risk(transactions)

    # 7) EC-specific Claude analysis
    ai_result = None
    ai_score = None

    try:
        claude = ClaudeClient()
        ai_result = calculate_ai_risk(claude, transactions, rule_score)
        ai_score = ai_result.get("ai_risk_score")
    except Exception as e:
        print(f"[CLAUDE EC RISK ERROR] {e}")
        ai_result = {
            "ai_risk_score": None,
            "risk_level": "UNKNOWN",
            "risk_indicators": [],
            "pattern_analysis": "",
            "recommendation": "Manual EC review recommended.",
            "confidence": "LOW",
        }

    # 8) Combine scores only when the AI score is available.
    if isinstance(ai_score, int):
        if ai_score >= 70:
            final_score = int(round((ai_score * 0.8) + (rule_score * 0.2)))
            ai_weight = 0.8
            rule_weight = 0.2
        else:
            final_score = int(round((ai_score * 0.6) + (rule_score * 0.4)))
            ai_weight = 0.6
            rule_weight = 0.4
    else:
        final_score = int(rule_score)
        ai_weight = 0.0
        rule_weight = 1.0

    final_score = max(0, min(100, final_score))

    if final_score >= 70:
        final_level = "HIGH"
    elif final_score >= 40:
        final_level = "MEDIUM"
    else:
        final_level = "LOW"

    encumbrance = _match_mortgages_to_releases(transactions)
    summary = _ec_transaction_summary(transactions)

    evidence_pages = []
    for tx in raw_tx:
        if isinstance(tx, dict):
            try:
                page = int(tx.get("_source_page"))
            except (TypeError, ValueError):
                continue
            if page not in evidence_pages:
                evidence_pages.append(page)
            if len(evidence_pages) == 2:
                break

    report = {
        "document_type": "EC",
        "status": "SUCCESS",
        "evidence_pages": evidence_pages,
        "report_metadata": {
            "report_type": "Encumbrance Certificate Risk Report",
            "generated_date": datetime.now().isoformat(),
            "analysis_scope": "EC transactions and encumbrance patterns only",
            "extraction_model": EXTRACTION_MODEL,
            "risk_model": RISK_MODEL,
        },
        "executive_summary": {
            "risk_level": final_level,
            "risk_score": final_score,
            "confidence": ai_result.get("confidence", "LOW"),
            "recommendation": ai_result.get(
                "recommendation", "Manual EC review recommended."
            ),
            "summary": (
                f"Analysis of {len(transactions)} validated EC transactions "
                f"resulted in {final_level} encumbrance/transaction risk."
            ),
        },
        "document_analysis": {
            "total_pages_processed": len(image_paths),
            "unique_pages_after_deduplication": len(unique_paths),
            "duplicate_pages_removed": duplicate_count,
            "ocr_characters": len(ec_text),
        },
        "transaction_analysis": {
            "total_transactions_extracted": len(raw_tx),
            "valid_transactions": len(transactions),
            "invalid_transactions": max(0, len(raw_tx) - len(transactions)),
            "breakdown_by_type": summary["breakdown_by_type"],
            "total_consideration_value": sum(
                float(t.get("consideration_value", 0) or 0)
                for t in transactions
                if (t.get("transaction_type") or "").upper()
                in {"SALE", "AGREEMENT_TO_SELL"}
            ),
        },
        "encumbrance_analysis": {
            "mortgages": encumbrance["mortgages"],
            "releases": encumbrance["releases"],
            "potentially_released_mortgages": encumbrance["potentially_released"],
            "unresolved_mortgages": encumbrance["unresolved_mortgages"],
        },
        "transaction_pattern_analysis": {
            "rapid_resales": summary["rapid_resales"],
            "repeated_sellers": summary["repeated_sellers"],
            "repeated_buyers": summary["repeated_buyers"],
            "poa_transactions": summary["poa_transactions_detail"],
        },
        "rule_based_analysis": {
            "score": rule_score,
            "flags_detected": rule_flags,
            "scope": "EC/encumbrance patterns only",
        },
        "ai_analysis": {
            "score": ai_score,
            "method": "Claude EC-specific analysis",
            "risk_level": ai_result.get("risk_level", "UNKNOWN"),
            "confidence": ai_result.get("confidence", "LOW"),
            "risk_indicators": ai_result.get("risk_indicators", []),
            "pattern_analysis": ai_result.get("pattern_analysis", ""),
            "recommendation": ai_result.get("recommendation", ""),
        },
        "final_assessment": {
            "combined_score": final_score,
            "risk_classification": final_level,
            "scoring_methodology": {
                "rule_based_weight": rule_weight,
                "ai_weight": ai_weight,
                "formula": (
                    "AI >= 70: AI×0.8 + Rule×0.2; "
                    "otherwise AI×0.6 + Rule×0.4; "
                    "if AI unavailable: Rule score only"
                ),
            },
            "action_required": ("YES" if final_level in {"HIGH", "MEDIUM"} else "NO"),
            "next_steps": _get_action_items(
                final_level, ai_result.get("recommendation", "")
            ),
        },
        "detailed_findings": {
            "sample_transactions": transactions[:5],
            "transaction_count": len(transactions),
            "note": (
                "This module analyzes EC/encumbrance information. "
                "It does not provide a standalone legal title opinion."
            ),
        },
    }

    if export_files:
        out_path = Path(output_dir) / export_json_path
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True, ensure_ascii=False)

    save_cached_report(
    output_dir,
    input_hash,
    report
)

    rule_score, rule_flags = calculate_risk(transactions)

    # 7) ai scoring
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
    return {
        "document_type": "EC",
        "status": "QWEN_EXTRACTION_SUCCESS",
        "pages": len(image_paths),
        "transactions": transactions,
    }


# ================================ OPTIONAL CLI ================================
def main():
    parser = argparse.ArgumentParser(description="EC Fraud Detection Wrapper CLI")
    parser.add_argument(
    "pdf",
    nargs="?",
    default=r"D:\aasthiv2\Aasthi\wrappercode\input\kaveriec\download.pdf",
    help="Path to EC PDF"
)
    parser.add_argument(
        "--force", action="store_true", help="Force regeneration ignoring cache"
    )
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--images", default=DEFAULT_IMAGES_DIR, help="Images directory")
    parser.add_argument("--export", action="store_true", help="Export JSON report file")
    parser.add_argument(
        "--report", default=DEFAULT_REPORT_NAME, help="Report JSON filename"
    )
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