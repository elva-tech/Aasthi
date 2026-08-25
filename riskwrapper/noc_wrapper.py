# noc_wrapper.py
#!/usr/bin/env python3
"""
NOC Risk Scoring (Wrapper): OCR -> Gemini extraction -> deterministic score + LLM risk score -> final blend

Higher safety score = safer (LESS risk).
✅ Added risk_score = 100 - safety_score everywhere (deterministic, llm, final, project aggregates)
"""

import base64
from io import BytesIO
import os
import re
import json
import csv
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib import response

from annotated_types import doc
from dotenv import load_dotenv
from google import genai

load_dotenv()
import ollama
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from anthropic import Anthropic
# -----------------------------
# CONFIG
# -----------------------------
from openai import OpenAI

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=300.0,
    max_retries=0

)
QWEN_CONTEXT_SIZE = 128000
EXTRACTION_MODEL = "gemma3:4b"
RISK_MODEL = "claude-opus-4-7"
OCR_DPI = 200
SCREENSHOT_DIR = r"D:\aasthiv2\Aasthi\riskwrapper\screenshots"
MAX_LLM_CHARS = 14000  # enough for first/last/significant pages of long NOCs

# Initialize with environment variable or default to 'tesseract'
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

WEIGHTS = {
    "authenticity": 0.25,
    "freshness": 0.20,
    "dues": 0.15,
    "compliance": 0.30,
    "purpose": 0.10,
}

CATEGORY_RISK = {
    "loan": 1,
    "electricity": 2,
    "water": 2,
    "fire": 2,
    "society_transfer": 2,
    "airport_height": 3,
    "other": 3,
    "environment": 4,
    "construction": 4,
    "renovation": 4,
}

# ============================================================
# NOC DOCUMENT GROUPING
# ============================================================

DOCUMENT_START_PATTERNS = [
    r"\bfire\s+(department|services?)\b",
    r"\bbwssb\b",
    r"\bbescom\b",
    r"\bkarnataka\s+state\s+pollution\b",
    r"\bpollution\s+control\s+board\b",
    r"\bairport\s+authority\b",
    r"\baai\b",
    r"\btown\s+planning\b",
    r"\bbda\b",
    r"\bbbmp\b",
    r"\bgovernment\s+of\b",
    r"\bgovernment\s+of\s+karnataka\b",
]

REFERENCE_PATTERNS = [
    r"\bref(?:erence)?\.?\s*(?:no|number)?\b",
    r"\bno\.?\s*[:/.-]?\s*[A-Z0-9]",
    r"\bfile\s*(?:no|number)\b",
    r"\bletter\s*(?:no|number)\b",
]

DATE_PATTERNS = [
    r"\bdate\s*[:.]",
    r"\bdated\s*[:.]?",
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
    r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b",
]


def _top_lines(
    text: str,
    n: int = 14
) -> str:

    return "\n".join(
        (text or "").splitlines()[:n]
    )


def _count_patterns(
    text: str,
    patterns: List[str]
) -> int:

    return sum(
        1
        for pattern in patterns
        if re.search(
            pattern,
            text,
            re.IGNORECASE
        )
    )


def document_start_score(
    text: str
) -> int:

    top = _top_lines(
        text,
        14
    )

    if len(top.strip()) < 80:
        return 0

    authority_hits = _count_patterns(
        top,
        DOCUMENT_START_PATTERNS
    )

    ref_hits = _count_patterns(
        top,
        REFERENCE_PATTERNS
    )

    date_hits = _count_patterns(
        top,
        DATE_PATTERNS
    )

    score = 0

    if authority_hits:
        score += 4

    if ref_hits:
        score += 2

    if date_hits:
        score += 2

    # Strong NOC/document heading
    if re.search(
        r"\b("
        r"NO\s+OBJECTION"
        r"|ISSUE\s+OF\s+NOC"
        r"|NOC"
        r"|ENVIRONMENT\s+CLEARANCE"
        r"|CONSENT\s+FOR\s+ESTABLISHMENT"
        r"|CONSENT\s+FOR\s+OPERATION"
        r")\b",
        top,
        re.IGNORECASE
    ):
        score += 3

    if re.search(
        r"\bTo\b",
        top,
        re.IGNORECASE
    ):
        score += 1

    return score


def looks_like_new_document(
    text: str
) -> bool:

    return (
        document_start_score(text)
        >= 7
    )

def split_documents(
    page_texts: List[str],
    page_offset: int = 0
) -> List[Dict[str, Any]]:

    if not page_texts:
        return []

    # ============================================================
    # NORMALIZE PAGE TEXT
    # ============================================================

    normalized_pages = []

    for text in page_texts:
        if text is None:
            text = ""

        text = str(text)

        # Keep original content reasonably intact,
        # but normalize whitespace for detection.
        normalized = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        normalized_pages.append({
            "raw": text,
            "normalized": normalized
        })

    # ============================================================
    # FIND REAL DOCUMENT STARTS
    #
    # IMPORTANT:
    # We do NOT classify a page as a new NOC merely because
    # it contains "fire", "water", "environment", etc.
    #
    # A new document must have strong document-start evidence.
    # ============================================================

    starts = []

    for i, page in enumerate(normalized_pages):

        text = page["normalized"]

        if not text:
            continue

        score = document_start_score(text)

        # --------------------------------------------------------
        # Only strong document-start evidence creates a split.
        # --------------------------------------------------------

        if score >= 7:

            starts.append(i)

            print(
                f"[SPLIT] Strong document start detected: "
                f"PDF page={page_offset + i + 1}, "
                f"score={score}"
            )

    # ============================================================
    # REMOVE NEAR-DUPLICATE STARTS
    #
    # Sometimes OCR causes two consecutive pages to look like
    # document starts. Do not immediately create two NOCs.
    # ============================================================

    filtered_starts = []

    for start in starts:

        if not filtered_starts:
            filtered_starts.append(start)
            continue

        previous = filtered_starts[-1]

        # If another strong start occurs immediately after the
        # previous start, inspect the page before splitting.
        if start == previous + 1:

            current_text = normalized_pages[
                start
            ]["normalized"].lower()

            previous_text = normalized_pages[
                previous
            ]["normalized"].lower()

            # ----------------------------------------------------
            # If the current page clearly contains a new formal
            # document heading/reference, keep it.
            # Otherwise treat it as continuation.
            # ----------------------------------------------------

            explicit_new_document = (
                _has_explicit_noc_document_start(
                    current_text
                )
            )

            if explicit_new_document:
                filtered_starts.append(start)

            else:
                print(
                    f"[SPLIT] Ignoring adjacent weak start "
                    f"at PDF page={page_offset + start + 1}"
                )

        else:
            filtered_starts.append(start)

    starts = filtered_starts

    # ============================================================
    # NO STRONG DOCUMENT START
    #
    # We cannot invent boundaries.
    # Treat the supplied pages as one document.
    # ============================================================

    if not starts:

        print(
            "[SPLIT] No strong document boundaries found. "
            "Keeping all pages as one document."
        )

        return [{
            "start_page": page_offset + 1,

            "end_page":
                page_offset + len(normalized_pages),

            "pages":
                f"{page_offset + 1}-"
                f"{page_offset + len(normalized_pages)}",

            "text":
                "\n\n".join(
                    page["raw"]
                    for page in normalized_pages
                )
        }]

    # ============================================================
    # FIRST PAGE
    #
    # If the first detected start is later than page 1, we do NOT
    # automatically assume page 1 belongs to that NOC.
    #
    # Instead, preserve the pages before the first detected
    # boundary as their own document because we have no evidence
    # to attach them elsewhere.
    # ============================================================

    if starts[0] > 0:

        print(
            f"[SPLIT] Pages "
            f"{page_offset + 1}-"
            f"{page_offset + starts[0]} "
            f"have no detected document start; "
            f"keeping them as a separate document."
        )

        starts.insert(0, 0)

    # ============================================================
    # BUILD DOCUMENTS
    # ============================================================

    documents = []

    for index, start in enumerate(starts):

        if index + 1 < len(starts):

            end = starts[index + 1] - 1

        else:

            end = len(normalized_pages) - 1

        if end < start:
            continue

        document_pages = normalized_pages[
            start:end + 1
        ]

        combined_text = "\n\n".join(
            page["raw"]
            for page in document_pages
        )

        document = {

            "start_page":
                page_offset + start + 1,

            "end_page":
                page_offset + end + 1,

            "pages":
                f"{page_offset + start + 1}-"
                f"{page_offset + end + 1}",

            "text":
                combined_text
        }

        documents.append(document)

        print(
            f"[SPLIT] Document created: "
            f"pages={document['pages']}"
        )

    # ============================================================
    # FINAL SAFETY CHECK
    # ============================================================

    # Ensure documents are ordered and non-overlapping.

    documents.sort(
        key=lambda x: x["start_page"]
    )

    return documents

def _has_explicit_noc_document_start(
    text: str
) -> bool:

    if not text:
        return False

    text = text.lower()

    # ------------------------------------------------------------
    # Explicit NOC/document terminology
    # ------------------------------------------------------------

    explicit_patterns = [

        r"\bno\s+objection\s+certificate\b",

        r"\bnoc\b",

        r"\bno[-\s]?objection\b",

        r"\bcertificate\s+no\b",

        r"\bcertificate\s+number\b",

        r"\bref(?:erence)?\.?\s*(?:no|number)\b",

        r"\bsubject\s*:",

        r"\bto\s*:",

        r"\bissued\s+to\b",

        r"\bvalid\s+(?:up\s+to|until|till)\b",

        r"\bthis\s+is\s+to\s+certify\b",

        r"\bhereby\s+certif(?:y|ies)\b"
    ]

    for pattern in explicit_patterns:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        ):
            return True

    return False

def pdf_pages_to_images(
    pdf_path: str,
    dpi: int = 120,
    jpeg_quality: int = 65
) -> List[Dict[str, Any]]:

    pages = []

    doc = fitz.open(pdf_path)

    try:
        for page_number in range(len(doc)):

            page = doc.load_page(page_number)

            pix = page.get_pixmap(
                dpi=dpi,
                alpha=False
            )

            img = Image.frombytes(
                "RGB",
                (pix.width, pix.height),
                pix.samples
            )

            buffer = BytesIO()

            img.save(
                buffer,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True
            )

            image_b64 = base64.b64encode(
                buffer.getvalue()
            ).decode("utf-8")

            pages.append({
                "page_number": page_number + 1,
                "image_base64": image_b64
            })

            print(
                f"[IMAGE] Page "
                f"{page_number + 1}/{len(doc)} rendered"
            )

    finally:
        doc.close()

    return pages

def get_claude_client():
    """
    Create Claude client for risk scoring.

    Claude is used ONLY for risk analysis.
    Qwen remains responsible for extraction.
    """

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY"
        )

    return Anthropic(
        api_key=api_key
    )

def _count_patterns(text: str, patterns: List[str]) -> int:
    return sum(
        1 for pattern in patterns
        if re.search(pattern, text, re.IGNORECASE)
    )

VISION_EXTRACTION_PROMPT = """
You are an expert Karnataka property-document extraction engine.

You are analyzing ONE PDF PAGE IMAGE.

Your task is ONLY to determine whether the CURRENT PAGE visibly contains
an NOC / statutory clearance document and extract factual information
visible on THIS PAGE.

IMPORTANT:
This is PAGE-LEVEL extraction.

DO NOT decide the final NOC document boundaries.
DO NOT create a new NOC merely because the page contains technical,
legal, environmental, fire, water, electricity, traffic, planning,
parking, or construction information.

The Python program will merge pages into complete NOC documents later.

========================================================
CORE RULE
========================================================

Be CONSERVATIVE.

If the page does not contain sufficient visible evidence that it belongs
to an NOC / statutory clearance, return:

{
  "is_noc": false,
  "page_data": {}
}

It is better to miss an uncertain page than to incorrectly classify an
ordinary project/technical page as an NOC.

========================================================
WHEN is_noc = TRUE
========================================================

Return is_noc=true ONLY when the CURRENT PAGE itself provides visible
evidence that it is an NOC / clearance document.

Strong evidence includes:

1. Explicit NOC / No Objection Certificate wording
2. Explicit Clearance / Environmental Clearance wording
3. Official approval/order issued by a government authority
4. Official utility clearance
5. Official Fire Department clearance
6. Official pollution-control clearance
7. Official water/sewerage clearance
8. Official electricity clearance
9. Official airport/railway/traffic/planning clearance
10. A clearly identifiable continuation page of an NOC

Examples of strong evidence:

- "NO OBJECTION CERTIFICATE"
- "NOC"
- "FIRE NOC"
- "FIRE SAFETY NOC"
- "ENVIRONMENTAL CLEARANCE"
- "ENVIRONMENT CLEARANCE"
- "CONSENT FOR ESTABLISHMENT"
- "CONSENT FOR OPERATION"
- "WATER SUPPLY NOC"
- "SEWERAGE NOC"
- "ELECTRICAL NOC"
- "BESCOM NOC"
- "BWSSB NOC"
- "KSPCB Consent"
- "Airport Authority NOC"
- "Traffic NOC"
- "Planning Authority NOC"

========================================================
CONTINUATION PAGE RULE
========================================================

A continuation page may be classified as is_noc=true ONLY when the
CURRENT PAGE contains visible evidence that it is a continuation.

Examples:

- "Continued"
- "Contd."
- "Page 2 of 4"
- "Page 3 of 5"
- "Continuation"
- continuation of numbered NOC conditions
- continuation of official approval conditions
- continuation of an official NOC letter/document
- repeated official document footer/header
- repeated NOC/reference information
- clearly numbered conditions that obviously belong to an official
  clearance document

If the page only contains general technical information, DO NOT classify
it as an NOC.

========================================================
VERY IMPORTANT: DO NOT INFER FROM TOPIC
========================================================

The following words alone are NOT enough to classify a page as an NOC:

- fire
- water
- electricity
- environment
- pollution
- traffic
- road
- parking
- sewage
- drainage
- lift
- building
- safety
- tank
- transformer
- road width
- fire tender
- landscaping
- trees
- waste
- STP

For example:

A normal building plan containing:

"Fire tender access shall be provided"

is NOT automatically a Fire NOC.

A normal project report containing:

"Water supply shall be provided"

is NOT automatically a Water NOC.

A normal environmental report containing environmental conditions is
NOT automatically an Environmental Clearance.

There must be visible evidence that the page belongs to an official
NOC / clearance document.

========================================================
ISSUER NAME
========================================================

Extract issuer_name ONLY when the OFFICIAL ISSUING AUTHORITY is visibly
printed on the CURRENT PAGE.

Examples of valid issuers:

- Bangalore Water Supply and Sewerage Board
- BWSSB
- Karnataka State Pollution Control Board
- KSPCB
- Karnataka Fire and Emergency Services
- State Level Environment Impact Assessment Authority - Karnataka
- SEIAA Karnataka
- BESCOM
- Airports Authority of India
- BBMP
- BDA
- other clearly identifiable government/utility authorities

IMPORTANT:

A CITY, LOCATION, ADDRESS, DISTRICT, TALUKA OR VILLAGE IS NOT AN ISSUER.

Examples:

"BANGALORE" -> NOT an issuer

"Bengaluru" -> NOT an issuer

"Koramangala" -> NOT an issuer

"Karnataka" -> NOT an issuer unless it is explicitly part of the
official authority name.

Never return a location as issuer_name.

If no official issuing authority is visibly present:

"issuer_name": ""

========================================================
ISSUER TYPE
========================================================

Use ONLY:

govt
utility
society
builder
other

Classify based ONLY on the organization that issued the document.

Examples:

BWSSB -> utility
BESCOM -> utility
KSPCB -> govt
SEIAA Karnataka -> govt
Karnataka Fire and Emergency Services -> govt

If issuer is not visible:

"issuer_type": ""

DO NOT infer issuer_type from the topic.

========================================================
NOC CATEGORY
========================================================

Use ONLY:

electricity
water
fire
environment
pollution
traffic
airport
railway
planning
other

Category must represent the ACTUAL PURPOSE of the official NOC /
clearance.

Examples:

BWSSB water/sewerage clearance -> water

BESCOM electricity clearance -> electricity

Karnataka Fire and Emergency Services clearance -> fire

SEIAA Environmental Clearance -> environment

KSPCB Consent / Pollution clearance -> pollution

Traffic Police / Traffic Authority clearance -> traffic

Airports Authority clearance -> airport

Railway clearance -> railway

Planning Authority approval -> planning

========================================================
CATEGORY MUST NOT BE GUESSED
========================================================

If the page is clearly a continuation but the category is not visible
on the CURRENT PAGE:

"noc_category": ""

Do NOT guess the category from individual words.

For example:

Page contains "fire fighting water tank"

This does NOT automatically mean:

"noc_category": "fire"

Page contains "road width"

This does NOT automatically mean:

"noc_category": "traffic"

Page contains "environmental safeguards"

This does NOT automatically mean:

"noc_category": "environment"

========================================================
REFERENCE NUMBER
========================================================

Extract ONLY an official NOC / clearance / order / file / reference
number visibly printed on THIS PAGE.

Valid examples:

- NOC No.
- Reference No.
- File No.
- Order No.
- Clearance No.

DO NOT extract:

- survey number
- property number
- application number
- project number
- flat number
- page number
- registration number
- PID
- EPID

unless the document explicitly identifies it as the NOC/reference/order
number.

If not visible:

"reference_no": ""

NEVER copy reference numbers from another page.

========================================================
DATES
========================================================

Extract ONLY dates visibly printed on THIS PAGE.

Normalize to:

YYYY-MM-DD

Examples:

28 OCT 2015 -> 2015-10-28
14/12/2015 -> 2015-12-14

DO NOT calculate dates.

DO NOT calculate expiry dates.

If the document says:

"valid for two years"

DO NOT calculate the expiry date.

Only extract expiry_date if an actual expiry/end date is explicitly
printed.

If not visible:

"issue_date": ""
"expiry_date": ""

========================================================
DUES
========================================================

Use ONLY:

no_dues
dues_pending
not_mentioned
conditional

Use no_dues ONLY when the page explicitly states:

- no dues
- no outstanding dues
- dues cleared
- no amount outstanding

Use dues_pending ONLY when the page explicitly states:

- dues pending
- outstanding dues
- unpaid amount
- outstanding amount

Use conditional ONLY when the page explicitly requires payment/charges
as a condition.

Otherwise:

"dues_status": "not_mentioned"

NEVER assume no dues.

========================================================
DUES AMOUNT
========================================================

Extract only an explicitly stated amount that is clearly related to:

- outstanding dues
- pending dues
- payable charges
- payment required by the NOC

Do NOT treat these as dues automatically:

- project cost
- construction cost
- estimated project cost
- investment amount
- general statutory fees
- future charges
- infrastructure estimate

If no explicit dues amount:

"dues_amount": 0

========================================================
PURPOSE
========================================================

Extract a SHORT description of the actual purpose of the NOC if
visible.

Examples:

"Water supply and sewerage clearance"

"Environmental clearance for the proposed residential project"

"Fire safety clearance for the proposed building"

Do NOT copy long paragraphs.

If purpose is not visible:

"purpose": ""

========================================================
CONDITIONS
========================================================

Extract ONLY important conditions visible on THIS PAGE.

Include:

- mandatory approvals
- statutory compliance
- validity conditions
- restrictions
- safety requirements
- environmental requirements
- fire requirements
- water/sewerage requirements
- pollution-control requirements
- payment conditions
- monitoring requirements
- cancellation/withdrawal conditions
- conditions that can prevent operation
- conditions requiring additional government approval

Keep conditions concise.

Do NOT copy the entire page.

Do NOT copy information from another page.

========================================================
PAGE DATA
========================================================

If the page is NOT an NOC:

{
  "is_noc": false,
  "page_data": {}
}

If the page IS an NOC or clearly identifiable continuation:

{
  "is_noc": true,
  "page_data": {
    "issuer_name": "",
    "issuer_type": "",
    "reference_no": "",
    "issue_date": "",
    "expiry_date": "",
    "noc_category": "",
    "purpose": "",
    "dues_status": "not_mentioned",
    "dues_amount": 0,
    "conditions": "",
    "confidence": 0.0
  }
}

========================================================
CONFIDENCE
========================================================

confidence must be between 0.0 and 1.0.

High confidence:
- official NOC/clearance heading visible
- official issuing authority visible
- clear document/reference information

Medium confidence:
- clearly identifiable continuation page

Low confidence:
- partial document evidence
- poor image quality
- uncertain continuation

========================================================
IMPORTANT
========================================================

This model performs PAGE EXTRACTION ONLY.

It does NOT:

- merge documents
- determine final NOC page ranges
- calculate risk
- calculate safety score
- assign risk severity
- make recommendations
- determine legal validity
- infer missing information

The downstream Python system will merge related pages and calculate
risk.

========================================================
FINAL RULE
========================================================

Return ONLY ONE valid JSON object.

No markdown.
No ```json.
No explanations.
No analysis outside JSON.
No risk scores.
No safety scores.
No recommendations.

Accuracy is more important than completeness.

If information is not visibly supported by the CURRENT PAGE, return:

""

or:

"not_mentioned"

Do not guess.
"""
# -----------------------------
# GEMINI: LLM SAFETY SCORE
# -----------------------------
def llm_safety_score(
    extracted_json: Dict[str, Any],
    risk_client
) -> Dict[str, Any]:

    # =========================================================
    # NO LLM CLIENT
    # =========================================================

    if not risk_client:
        return {
            "safety_score_0_100": None,
            "confidence": 0.0,
            "top_risks": [],
            "notes": "LLM risk client unavailable."
        }

    # =========================================================
    # SERIALIZE COMPLETE MERGED NOC
    # =========================================================

    try:
        extracted_data = json.dumps(
            extracted_json,
            ensure_ascii=False,
            indent=2
        )

    except Exception as e:
        return {
            "safety_score_0_100": None,
            "confidence": 0.0,
            "top_risks": [],
            "notes": f"Failed to serialize NOC data: {e}"
        }

    # Prevent excessively large Gemini prompt
    extracted_data = extracted_data[:MAX_LLM_CHARS]

    # =========================================================
    # PROMPT
    # =========================================================

    prompt = f"""
ROLE:
You are a Senior Property Due Diligence Consultant,
Government NOC Compliance Auditor,
and Municipal Risk Assessment Specialist.

TASK:
Assess the COMPLETE NOC document represented by the supplied
structured data.

IMPORTANT DOCUMENT STRUCTURE RULE:

The supplied data represents ONE NOC document.

The NOC may contain multiple pages.

Pages belonging to the same NOC have already been merged.

DO NOT treat individual pages as separate NOCs.

Evaluate the document as ONE complete NOC.

Do NOT create additional NOCs.

Do NOT invent missing information.

Do NOT use outside knowledge as evidence.

------------------------------------------------------------
SCORING
------------------------------------------------------------

Return a SAFETY SCORE from 0 to 100.

100 = Extremely Safe
0   = Extremely Unsafe

The application converts this internally:

Risk Score = 100 - Safety Score

Therefore:

High Safety Score = Low Risk
Low Safety Score  = High Risk

------------------------------------------------------------
EVALUATION FACTORS
------------------------------------------------------------

Evaluate the following factors ONLY when supported by the
supplied NOC data.

1. ISSUER
- Issuer name
- Issuer type
- Government / recognized authority
- Reference number

2. VALIDITY
- Issue date
- Expiry date
- Validity information
- Whether the supplied dates indicate expiry

IMPORTANT:
Do NOT assume that an NOC is expired merely because an
expiry date is missing.

3. NOC CATEGORY
Examples:
- Fire
- Water
- Electricity
- Pollution
- Environment
- Airport
- Traffic
- Other

4. PURPOSE
- Stated purpose
- Intended use
- Whether the stated purpose is consistent with the
  supplied NOC category

5. DUES
- No dues
- Pending dues
- Outstanding amount
- Dues not mentioned

6. CONDITIONS
- Restrictions
- Special conditions
- Compliance requirements
- Violations
- Penalties

7. DOCUMENT COMPLETENESS
Consider whether the supplied data contains:
- Issuer
- Reference number
- Issue date
- Expiry date
- NOC category
- Purpose
- Conditions
- Dues information

------------------------------------------------------------
IMPORTANT SCORING RULES
------------------------------------------------------------

RULE 1:
Never invent facts.

RULE 2:
Missing information should primarily reduce CONFIDENCE.

Do NOT automatically treat missing information as high risk.

RULE 3:
An unknown field is NOT automatically a violation.

RULE 4:
Do NOT assume an NOC is expired unless the supplied data
contains evidence establishing that it is expired.

RULE 5:
Do NOT assume an issuer is invalid merely because you do not
recognize the issuer.

RULE 6:
Increase risk only when the supplied data provides evidence
of an actual problem, such as:
- pending dues
- explicit violation
- expired validity
- serious restriction
- explicit rejection
- explicit cancellation
- explicitly invalid issuer

RULE 7:
Every risk MUST be supported by evidence contained in the
supplied NOC data.

RULE 8:
Evidence quotes must be copied ONLY from the supplied data.

RULE 9:
Do not create evidence quotes.

RULE 10:
Do not use external facts to justify the score.

RULE 11:
The score must reflect the evidence.

RULE 12:
Do not automatically assign 50.

A score of 50 should be used ONLY if the actual evidence
supports a moderate safety assessment.

------------------------------------------------------------
SAFETY GUIDELINES
------------------------------------------------------------

VERY HIGH SAFETY:
- Recognized/identified issuer
- Reference number available
- Validity supported by supplied dates
- No dues or dues explicitly cleared
- No serious restrictions
- No explicit violations
- Complete information

HIGH SAFETY:
- Issuer identified
- Most important fields available
- No significant adverse information
- Some minor information missing

MODERATE SAFETY:
- Some important fields missing
- Expiry not mentioned
- Limited document information
- Minor conditions

LOW SAFETY:
- Pending dues
- Explicit violations
- Expired NOC
- Serious restrictions
- Explicit cancellation/rejection
- Explicitly invalid issuer

VERY LOW SAFETY:
- Strong direct evidence that the NOC is invalid,
  cancelled, rejected, expired with no valid extension,
  or contains serious unresolved compliance problems.

------------------------------------------------------------
COMPLETE MERGED NOC DATA
------------------------------------------------------------

{extracted_data}

------------------------------------------------------------
OUTPUT
------------------------------------------------------------

Return ONLY valid JSON.

{{
    "safety_score_0_100": 0,
    "confidence": 0.0,
    "top_risks": [
        {{
            "risk": "",
            "severity": "low",
            "evidence_quote": ""
        }}
    ],
    "notes": ""
}}

------------------------------------------------------------
OUTPUT RULES
------------------------------------------------------------

safety_score_0_100:
- Number between 0 and 100.

confidence:
- Number between 0 and 1.

top_risks:
- JSON array.
- Maximum 6 risks.

severity:
- Must be exactly:
  "low"
  "medium"
  "high"

evidence_quote:
- Must come directly from the supplied NOC data.
- If there is no evidence, do not create a risk.

notes:
- Brief explanation of the score.

Return ONLY JSON.
""".strip()

    # =========================================================
    # GEMINI CALL
    # =========================================================

    try:

        response = risk_client.messages.create(
            model=RISK_MODEL,
            max_tokens=3000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        raw = ""

        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text

        raw = raw.strip()

        if not raw:
            raise ValueError(
                "Claude returned an empty response"
            )


        # =====================================================
        # CLEAN MARKDOWN
        # =====================================================

        cleaned = raw.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]

        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        # =====================================================
        # PARSE JSON
        # =====================================================

        try:

            result = json.loads(cleaned)

        except json.JSONDecodeError:

            start = cleaned.find("{")
            end = cleaned.rfind("}")

            if start == -1 or end == -1 or end <= start:
                raise ValueError(
                    "LLM response did not contain valid JSON"
                )

            result = json.loads(
                cleaned[start:end + 1]
            )

        if not isinstance(result, dict):
            raise ValueError(
                "LLM response is not a JSON object"
            )

        # =====================================================
        # SAFETY SCORE
        # =====================================================

        safety = result.get(
            "safety_score_0_100"
        )

        if safety is None:
            raise ValueError(
                "LLM response missing "
                "'safety_score_0_100'"
            )

        safety = float(safety)

        safety = max(
            0.0,
            min(100.0, safety)
        )

        # =====================================================
        # CONFIDENCE
        # =====================================================

        confidence = result.get(
            "confidence",
            0.0
        )

        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0

        confidence = max(
            0.0,
            min(1.0, confidence)
        )

        # =====================================================
        # RISKS
        # =====================================================

        risks = result.get(
            "top_risks",
            []
        )

        if not isinstance(risks, list):
            risks = []

        cleaned_risks = []

        for risk in risks[:6]:

            if not isinstance(risk, dict):
                continue

            severity = str(
                risk.get(
                    "severity",
                    "low"
                )
            ).lower()

            if severity not in (
                "low",
                "medium",
                "high"
            ):
                severity = "low"

            cleaned_risks.append({
                "risk": str(
                    risk.get(
                        "risk",
                        ""
                    )
                ),

                "severity": severity,

                "evidence_quote": str(
                    risk.get(
                        "evidence_quote",
                        ""
                    )
                )
            })

        # =====================================================
        # NOTES
        # =====================================================

        notes = result.get(
            "notes",
            ""
        )

        if notes is None:
            notes = ""

        notes = str(notes)

        # =====================================================
        # FINAL RESULT
        # =====================================================

        return {
            "safety_score_0_100": round(
                safety,
                2
            ),

            "confidence": round(
                confidence,
                2
            ),

            "top_risks": cleaned_risks,

            "notes": notes
        }

    # =========================================================
    # ERROR
    # =========================================================

    except Exception as e:

        print(
            f"[ERROR] NOC LLM risk scoring failed: "
            f"{type(e).__name__}: {e}"
        )

        return {
            "safety_score_0_100": None,
            "confidence": 0.0,
            "top_risks": [],
            "notes": (
                f"LLM risk scoring failed: "
                f"{type(e).__name__}: {e}"
            )
        }
QWEN_IMAGE_BATCH_SIZE = 1

def extract_nocs_from_images_qwen(
    page_images: List[Dict[str, Any]]
) -> Dict[str, Any]:

    batch_size = 1
    all_pages = []

    total_pages = len(page_images)

    for batch_start in range(0, total_pages, batch_size):

        batch = page_images[
            batch_start:batch_start + batch_size
        ]

        if not batch:
            continue

        page = batch[0]
        page_number = page["page_number"]

        print("\n" + "=" * 90)
        print(f"🔍 QWEN VISION PAGE {page_number}")
        print(f"📄 PDF page {page_number}")
        print("=" * 90)

        content = [
            {
                "type": "text",
                "text": VISION_EXTRACTION_PROMPT
            },
            {
                "type": "text",
                "text": (
                    f"===== PDF PAGE {page_number} ====="
                )
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        "data:image/jpeg;base64,"
                        + page["image_base64"]
                    )
                }
            }
        ]

        print(
            "[QWEN-VISION] Sending 1 page image"
        )

        try:

            response = qwen_client.chat.completions.create(
                model=EXTRACTION_MODEL,

                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict visual document "
                            "extraction engine. "
                            "Read ONLY the supplied page image. "
                            "Extract only information visibly present "
                            "on this page. "
                            "Do not infer missing information. "
                            "Do not determine document grouping. "
                            "Do not calculate risk. "
                            "Return ONLY valid JSON."
                        )
                    },
                    {
                        "role": "user",
                        "content": content
                    }
                ],

                temperature=0,
                max_tokens=500,

                response_format={
                    "type": "json_object"
                },

                extra_body={
                    "options": {
                        "num_ctx": 8192
                    }
                }
            )

        except Exception as e:

            print(
                f"[QWEN-VISION] Page {page_number} failed: "
                f"{type(e).__name__}: {e}"
            )

            # IMPORTANT:
            # Keep page position even when extraction fails.
            all_pages.append({
                "page_number": page_number,
                "is_noc": False,
                "page_data": {},
                "extraction_error": str(e)
            })

            continue

        # ---------------------------------------------------------
        # READ OPENAI-COMPATIBLE / OLLAMA RESPONSE
        # ---------------------------------------------------------

        try:

            raw = response.choices[0].message.content

        except Exception as e:

            print(
                f"[QWEN-VISION] Could not read response "
                f"for page {page_number}: {e}"
            )

            all_pages.append({
                "page_number": page_number,
                "is_noc": False,
                "page_data": {},
                "extraction_error": str(e)
            })

            continue

        if not raw:

            print(
                f"[QWEN-VISION] Empty response "
                f"for page {page_number}"
            )

            all_pages.append({
                "page_number": page_number,
                "is_noc": False,
                "page_data": {},
                "extraction_error": "Empty Qwen response"
            })

            continue

        raw = raw.strip()

        # ---------------------------------------------------------
        # CLEAN JSON
        # ---------------------------------------------------------

        raw = (
            raw
            .replace("```json", "")
            .replace("```JSON", "")
            .replace("```", "")
            .strip()
        )

        # ---------------------------------------------------------
        # PARSE JSON
        # ---------------------------------------------------------

        try:

            result = json.loads(raw)

        except json.JSONDecodeError:

            start = raw.find("{")
            end = raw.rfind("}")

            if start == -1 or end <= start:

                print(
                    f"[QWEN-VISION] Invalid JSON "
                    f"for page {page_number}"
                )

                all_pages.append({
                    "page_number": page_number,
                    "is_noc": False,
                    "page_data": {},
                    "extraction_error": "Invalid JSON"
                })

                continue

            try:

                result = json.loads(
                    raw[start:end + 1]
                )

            except Exception as e:

                print(
                    f"[QWEN-VISION] JSON parsing failed "
                    f"for page {page_number}: {e}"
                )

                all_pages.append({
                    "page_number": page_number,
                    "is_noc": False,
                    "page_data": {},
                    "extraction_error": str(e)
                })

                continue

        if not isinstance(result, dict):

            all_pages.append({
                "page_number": page_number,
                "is_noc": False,
                "page_data": {},
                "extraction_error": "Response was not object"
            })

            continue

        # ---------------------------------------------------------
        # PAGE-LEVEL DATA ONLY
        # ---------------------------------------------------------

        is_noc = bool(
            result.get("is_noc", False)
        )

        page_data = result.get(
            "page_data",
            {}
        )

        if not isinstance(page_data, dict):
            page_data = {}

        # ---------------------------------------------------------
        # NORMALIZE
        # ---------------------------------------------------------

        normalized = {

            "issuer_name": str(
                page_data.get(
                    "issuer_name",
                    ""
                ) or ""
            ).strip(),

            "issuer_type": str(
                page_data.get(
                    "issuer_type",
                    "other"
                ) or "other"
            ).strip(),

            "reference_no": str(
                page_data.get(
                    "reference_no",
                    ""
                ) or ""
            ).strip(),

            "issue_date": str(
                page_data.get(
                    "issue_date",
                    ""
                ) or ""
            ).strip(),

            "expiry_date": str(
                page_data.get(
                    "expiry_date",
                    ""
                ) or ""
            ).strip(),

            "noc_category": str(
                page_data.get(
                    "noc_category",
                    "other"
                ) or "other"
            ).strip().lower(),

            "purpose": str(
                page_data.get(
                    "purpose",
                    ""
                ) or ""
            ).strip(),

            "dues_status": str(
                page_data.get(
                    "dues_status",
                    "not_mentioned"
                ) or "not_mentioned"
            ).strip(),

            "dues_amount":
                page_data.get(
                    "dues_amount",
                    0
                ),

            "conditions": str(
                page_data.get(
                    "conditions",
                    ""
                ) or ""
            ).strip(),

            "confidence":
                page_data.get(
                    "confidence",
                    0.0
                )
        }

        try:
            normalized["confidence"] = float(
                normalized["confidence"]
            )
        except Exception:
            normalized["confidence"] = 0.0

        normalized["confidence"] = max(
            0.0,
            min(
                1.0,
                normalized["confidence"]
            )
        )

        # ---------------------------------------------------------
        # STORE PAGE
        # ---------------------------------------------------------

        all_pages.append({

            "page_number": page_number,

            "is_noc": is_noc,

            "page_data": normalized
        })

        print(
            f"[QWEN-VISION] Page {page_number}: "
            f"is_noc={is_noc}, "
            f"category={normalized['noc_category']}, "
            f"issuer={normalized['issuer_name']}"
        )

    # ---------------------------------------------------------
    # SORT BY ORIGINAL PDF PAGE
    # ---------------------------------------------------------

    all_pages.sort(
        key=lambda x: x["page_number"]
    )

    return {
        "pages": all_pages
    }
def group_noc_pages(
    pages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    if not pages:
        return []

    groups = []
    current = None

    def clean(value):
        if value is None:
            return ""
        return str(value).strip()

    def same(a, b):
        a = clean(a).lower()
        b = clean(b).lower()

        return (
            a != ""
            and b != ""
            and a == b
        )

    for page in pages:

        page_no = page.get(
            "page_number"
        )

        page_data = page.get(
            "page_data",
            {}
        )

        if not isinstance(page_data, dict):
            page_data = {}

        if not page.get("is_noc", False):

            # Non-NOC pages do not automatically start
            # a new NOC.
            continue

        issuer = clean(
            page_data.get(
                "issuer_name",
                ""
            )
        )

        reference = clean(
            page_data.get(
                "reference_no",
                ""
            )
        )

        category = clean(
            page_data.get(
                "noc_category",
                ""
            )
        )

        issue_date = clean(
            page_data.get(
                "issue_date",
                ""
            )
        )

        purpose = clean(
            page_data.get(
                "purpose",
                ""
            )
        )

        # ---------------------------------------------------------
        # FIRST NOC
        # ---------------------------------------------------------

        if current is None:

            current = {
                "start_page": page_no,
                "end_page": page_no,
                "pages": [page_no],
                "page_data": [page]
            }

            continue

        previous_page = current["end_page"]

        # ---------------------------------------------------------
        # GAP
        # ---------------------------------------------------------

        if page_no != previous_page + 1:

            groups.append(current)

            current = {
                "start_page": page_no,
                "end_page": page_no,
                "pages": [page_no],
                "page_data": [page]
            }

            continue

        # ---------------------------------------------------------
        # INFORMATION FROM CURRENT GROUP
        # ---------------------------------------------------------

        group_pages = current["page_data"]

        group_issuer = ""
        group_reference = ""
        group_category = ""

        for gp in group_pages:

            gd = gp.get(
                "page_data",
                {}
            )

            if not isinstance(gd, dict):
                continue

            if not group_issuer:
                group_issuer = clean(
                    gd.get(
                        "issuer_name",
                        ""
                    )
                )

            if not group_reference:
                group_reference = clean(
                    gd.get(
                        "reference_no",
                        ""
                    )
                )

            if not group_category:
                group_category = clean(
                    gd.get(
                        "noc_category",
                        ""
                    )
                )

        # ---------------------------------------------------------
        # STRONG SAME-NOC SIGNALS
        # ---------------------------------------------------------

        same_reference = (
            reference
            and group_reference
            and same(
                reference,
                group_reference
            )
        )

        same_issuer = (
            issuer
            and group_issuer
            and same(
                issuer,
                group_issuer
            )
        )

        same_category = (
            category
            and group_category
            and same(
                category,
                group_category
            )
        )

        # ---------------------------------------------------------
        # CONTINUATION PAGE
        # ---------------------------------------------------------

        continuation = (
            not issuer
            and not reference
            and not issue_date
            and not purpose
            and (
                not category
                or category == "other"
            )
        )

        # ---------------------------------------------------------
        # DECIDE SAME NOC
        # ---------------------------------------------------------

        same_noc = False

        if same_reference:
            same_noc = True

        elif same_issuer and same_category:
            same_noc = True

        elif same_issuer and not category:
            same_noc = True

        elif same_category and not issuer:
            same_noc = True

        elif continuation:
            same_noc = True

        # ---------------------------------------------------------
        # NEW NOC
        # ---------------------------------------------------------

        if not same_noc:

            groups.append(current)

            current = {
                "start_page": page_no,
                "end_page": page_no,
                "pages": [page_no],
                "page_data": [page]
            }

        # ---------------------------------------------------------
        # SAME NOC
        # ---------------------------------------------------------

        else:

            current["end_page"] = page_no

            current["pages"].append(
                page_no
            )

            current["page_data"].append(
                page
            )

    # ---------------------------------------------------------
    # FINAL GROUP
    # ---------------------------------------------------------

    if current is not None:
        groups.append(current)

    # ---------------------------------------------------------
    # FORMAT
    # ---------------------------------------------------------

    for group in groups:

        start = group["start_page"]
        end = group["end_page"]

        if start == end:
            group["pages_text"] = str(start)
        else:
            group["pages_text"] = (
                f"{start}-{end}"
            )

    print(
        "\n" + "=" * 100
    )

    print(
        "📚 FINAL NOC DOCUMENT GROUPING"
    )

    print(
        "=" * 100
    )

    for index, group in enumerate(
        groups,
        start=1
    ):

        print(
            f"NOC {index}: "
            f"pages={group['pages_text']}"
        )

    print(
        f"TOTAL COMPLETE NOCs: {len(groups)}"
    )

    return groups

def merge_noc_pages(
    page_documents: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merge ALL page-level data belonging to ONE NOC.

    IMPORTANT:
        page_documents must contain actual page dictionaries.

    Example:
        [
            {
                "page_number": 17,
                "page_data": {...}
            },
            {
                "page_number": 18,
                "page_data": {...}
            },
            {
                "page_number": 19,
                "page_data": {...}
            }
        ]

    Returns ONE dictionary representing ONE complete NOC.

    It does NOT create multiple NOCs.
    It does NOT infer missing information.
    """

    if not isinstance(page_documents, list):
        return {}

    # ------------------------------------------------------------
    # SAFETY: remove invalid entries
    # ------------------------------------------------------------

    valid_pages = []

    for item in page_documents:

        if not isinstance(item, dict):
            continue

        if "page_number" not in item:
            continue

        valid_pages.append(item)

    if not valid_pages:
        return {}

    # ------------------------------------------------------------
    # SORT BY PDF PAGE
    # ------------------------------------------------------------

    valid_pages.sort(
        key=lambda x: int(
            x.get("page_number", 0)
        )
    )

    # ------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------

    def clean(value):

        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        return str(value).strip()

    def first_non_empty(values):

        for value in values:

            value = clean(value)

            if value:
                return value

        return ""

    def unique_non_empty(values):

        output = []

        seen = set()

        for value in values:

            value = clean(value)

            if not value:
                continue

            key = value.lower()

            if key not in seen:

                seen.add(key)
                output.append(value)

        return output

    # ------------------------------------------------------------
    # COLLECT PAGE DATA
    # ------------------------------------------------------------

    issuers = []
    issuer_types = []
    references = []
    issue_dates = []
    expiry_dates = []
    categories = []
    purposes = []
    conditions = []

    dues_statuses = []
    dues_amounts = []
    confidences = []

    source_pages = []

    for page in valid_pages:

        page_number = page.get(
            "page_number"
        )

        page_data = page.get(
            "page_data",
            {}
        )

        # --------------------------------------------------------
        # IMPORTANT:
        # page_data MUST be a dictionary.
        # --------------------------------------------------------

        if not isinstance(
            page_data,
            dict
        ):
            page_data = {}

        source_pages.append(
            {
                "page_number": page_number,
                "is_noc": bool(
                    page.get(
                        "is_noc",
                        False
                    )
                ),
                "page_data": page_data
            }
        )

        # --------------------------------------------------------
        # SCALAR FIELDS
        # --------------------------------------------------------

        value = page_data.get(
            "issuer_name",
            ""
        )

        if clean(value):
            issuers.append(
                clean(value)
            )

        value = page_data.get(
            "issuer_type",
            ""
        )

        if clean(value):
            issuer_types.append(
                clean(value)
            )

        value = page_data.get(
            "reference_no",
            ""
        )

        if clean(value):
            references.append(
                clean(value)
            )

        value = page_data.get(
            "issue_date",
            ""
        )

        if clean(value):
            issue_dates.append(
                clean(value)
            )

        value = page_data.get(
            "expiry_date",
            ""
        )

        if clean(value):
            expiry_dates.append(
                clean(value)
            )

        value = page_data.get(
            "noc_category",
            ""
        )

        if clean(value):
            categories.append(
                clean(value).lower()
            )

        value = page_data.get(
            "purpose",
            ""
        )

        if clean(value):
            purposes.append(
                clean(value)
            )

        value = page_data.get(
            "conditions",
            ""
        )

        if clean(value):
            conditions.append(
                clean(value)
            )

        # --------------------------------------------------------
        # DUES STATUS
        # --------------------------------------------------------

        value = page_data.get(
            "dues_status",
            ""
        )

        value = clean(value).lower()

        if value:
            dues_statuses.append(
                value
            )

        # --------------------------------------------------------
        # DUES AMOUNT
        # --------------------------------------------------------

        value = page_data.get(
            "dues_amount",
            0
        )

        try:

            amount = float(
                value or 0
            )

            if amount > 0:
                dues_amounts.append(
                    amount
                )

        except Exception:
            pass

        # --------------------------------------------------------
        # CONFIDENCE
        # --------------------------------------------------------

        value = page_data.get(
            "confidence",
            0
        )

        try:

            confidence = float(
                value
            )

            if 0 <= confidence <= 1:

                confidences.append(
                    confidence
                )

        except Exception:
            pass

    # ------------------------------------------------------------
    # CATEGORY
    #
    # DO NOT use category priority here.
    #
    # If pages explicitly contain different categories,
    # preserve them instead of arbitrarily selecting one.
    # ------------------------------------------------------------

    categories = unique_non_empty(
        categories
    )

    if len(categories) == 1:

        merged_category = categories[0]

    elif len(categories) > 1:

        merged_category = ", ".join(
            categories
        )

    else:

        merged_category = ""

    # ------------------------------------------------------------
    # DUES STATUS
    # ------------------------------------------------------------

    dues_statuses = unique_non_empty(
        dues_statuses
    )

    if "dues_pending" in dues_statuses:

        merged_dues_status = (
            "dues_pending"
        )

    elif "conditional" in dues_statuses:

        merged_dues_status = (
            "conditional"
        )

    elif "no_dues" in dues_statuses:

        merged_dues_status = (
            "no_dues"
        )

    elif dues_statuses:

        merged_dues_status = (
            dues_statuses[0]
        )

    else:

        merged_dues_status = (
            "not_mentioned"
        )

    # ------------------------------------------------------------
    # CONDITIONS
    # ------------------------------------------------------------

    unique_conditions = unique_non_empty(
        conditions
    )

    merged_conditions = "\n\n".join(
        unique_conditions
    )

    # ------------------------------------------------------------
    # CONFIDENCE
    # ------------------------------------------------------------

    if confidences:

        merged_confidence = round(
            sum(confidences)
            / len(confidences),
            3
        )

    else:

        merged_confidence = 0.0

    # ------------------------------------------------------------
    # DUES AMOUNT
    # ------------------------------------------------------------

    if dues_amounts:

        merged_dues_amount = max(
            dues_amounts
        )

    else:

        merged_dues_amount = 0

    # ------------------------------------------------------------
    # PAGE RANGE
    # ------------------------------------------------------------

    page_numbers = [
        int(
            page["page_number"]
        )
        for page in valid_pages
        if page.get("page_number") is not None
    ]

    start_page = min(
        page_numbers
    )

    end_page = max(
        page_numbers
    )

    pages_text = (
        str(start_page)
        if start_page == end_page
        else f"{start_page}-{end_page}"
    )

    # ------------------------------------------------------------
    # ONE COMPLETE NOC
    # ------------------------------------------------------------

    merged = {

        "start_page":
            start_page,

        "end_page":
            end_page,

        "pages":
            pages_text,

        "issuer_name":
            first_non_empty(
                issuers
            ),

        "issuer_type":
            first_non_empty(
                issuer_types
            ),

        "reference_no":
            first_non_empty(
                references
            ),

        "issue_date":
            first_non_empty(
                issue_dates
            ),

        "expiry_date":
            first_non_empty(
                expiry_dates
            ),

        "noc_category":
            merged_category,

        "purpose":
            first_non_empty(
                purposes
            ),

        "dues_status":
            merged_dues_status,

        "dues_amount":
            merged_dues_amount,

        "conditions":
            merged_conditions,

        "confidence":
            merged_confidence,

        # Keep complete page-level evidence.
        "source_pages":
            source_pages
    }

    return merged

def risk_score_from_safety(safety_score: float) -> float:
    """
    Convert safety score to risk score.

    100 safety = 0 risk
    0 safety = 100 risk
    """

    return round(
        max(
            0.0,
            min(
                100.0,
                100.0 - float(safety_score)
            )
        ),
        2
    )
# -----------------------------
# COMBINE SCORES
# -----------------------------
def combine_scores(det_safety: float, llm_safety: int, llm_conf: float) -> float:
    base_llm_weight = 0.25
    w = base_llm_weight * llm_conf  
    final = det_safety * (1 - w) + float(llm_safety) * w
    return round(max(0.0, min(100.0, final)), 2)


# -----------------------------
# DETERMINISTIC SCORING
# -----------------------------
def parse_iso_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

def compute_factor_scores(ex: Dict[str, Any]) -> Dict[str, int]:
    """
    Deterministic NOC risk scoring.

    Factor scale:
        1 = very safe
        2 = low risk
        3 = moderate / insufficient evidence
        4 = high risk
        5 = very high risk

    IMPORTANT:
    Missing information is NOT automatically treated as a high risk.
    Explicit negative evidence increases risk.
    Explicit positive evidence decreases risk.
    """

    # ============================================================
    # 1. AUTHENTICITY
    # ============================================================

    issuer = str(
        ex.get("issuer_name", "") or ""
    ).strip()

    issuer_type = str(
        ex.get("issuer_type", "") or ""
    ).strip().lower()

    reference = str(
        ex.get("reference_no", "") or ""
    ).strip()

    confidence = float(
        ex.get("confidence", 0.0) or 0.0
    )

    # Start neutral
    authenticity = 3

    # Strong official issuer
    if issuer:
        if issuer_type in {"govt", "utility"}:
            authenticity = 1
        else:
            authenticity = 2

    # Reference number improves authenticity
    if reference:
        authenticity = max(
            1,
            authenticity - 1
        )

    # Very low extraction confidence increases uncertainty
    if confidence < 0.40:
        authenticity = min(
            5,
            authenticity + 1
        )

    # ============================================================
    # 2. FRESHNESS
    # ============================================================

    issue_dt = parse_iso_date(
        ex.get("issue_date", "")
    )

    expiry_dt = parse_iso_date(
        ex.get("expiry_date", "")
    )

    today = datetime.now(timezone.utc).date()

    freshness = 3

    # Explicit expiry
    if expiry_dt:

        if expiry_dt.date() < today:
            freshness = 5

        else:
            freshness = 1

    # Otherwise evaluate issue date
    elif issue_dt:

        age_days = (
            today - issue_dt.date()
        ).days

        if age_days < 0:
            # Future-dated document
            freshness = 3

        elif age_days <= 180:
            freshness = 1

        elif age_days <= 365 * 2:
            freshness = 2

        elif age_days <= 365 * 5:
            freshness = 3

        else:
            freshness = 4

    else:
        # Unknown date = uncertainty, not automatically expired
        freshness = 3

    # ============================================================
    # 3. DUES
    # ============================================================

    dues_status = str(
        ex.get(
            "dues_status",
            "not_mentioned"
        ) or "not_mentioned"
    ).lower().strip()

    dues_amount = float(
        ex.get("dues_amount", 0) or 0
    )

    if dues_status == "no_dues":

        dues = 1

    elif dues_status == "dues_pending":

        if dues_amount > 50000:
            dues = 5
        elif dues_amount > 5000:
            dues = 4
        else:
            dues = 4

    elif dues_status == "conditional":

        dues = 3

    else:

        # Not mentioned = neutral
        dues = 3

    # ============================================================
    # 4. COMPLIANCE / CONDITIONS
    # ============================================================

    conditions = str(
        ex.get("conditions", "") or ""
    ).strip().lower()

    compliance = 2

    # Explicitly dangerous / negative conditions
    severe_terms = [
        "violation",
        "unauthorized",
        "illegal",
        "cancelled",
        "cancelled",
        "cancellation",
        "withdrawn",
        "withdrawal",
        "dispute",
        "non-compliance",
        "non compliance",
        "penalty",
        "stop work",
        "rejected",
        "rejection",
        "prohibited",
        "not permitted",
        "shall not",
        "revoked",
        "revocation",
    ]

    moderate_terms = [
        "subject to",
        "conditional",
        "pending",
        "shall comply",
        "must comply",
        "prior approval",
        "additional approval",
        "approval required",
        "permission required",
        "validity",
        "renewal required",
        "charges payable",
        "payment required",
        "monitoring required",
    ]

    positive_terms = [
        "approved",
        "approval granted",
        "no objection",
        "cleared",
        "clearance granted",
        "complied",
        "compliance confirmed",
    ]

    if any(
        term in conditions
        for term in severe_terms
    ):

        compliance = 5

    elif any(
        term in conditions
        for term in moderate_terms
    ):

        compliance = 3

    elif any(
        term in conditions
        for term in positive_terms
    ):

        compliance = 1

    else:

        # Conditions exist but no explicit negative signal
        compliance = 2

    # ============================================================
    # 5. PURPOSE / CATEGORY
    # ============================================================

    category = str(
        ex.get("noc_category", "") or ""
    ).lower().strip()

    purpose = str(
        ex.get("purpose", "") or ""
    ).lower().strip()

    category_risk = {
        "electricity": 2,
        "water": 2,
        "fire": 2,
        "environment": 2,
        "pollution": 2,
        "traffic": 2,
        "airport": 2,
        "railway": 2,
        "planning": 2,
        "other": 3,
        "": 3,
    }

    purpose_score = category_risk.get(
        category,
        3
    )

    # Explicitly known purpose is better evidence
    if purpose:
        purpose_score = max(
            1,
            purpose_score - 1
        )

    # ============================================================
    # RETURN
    # ============================================================

    return {
        "authenticity": int(
            max(1, min(5, authenticity))
        ),

        "freshness": int(
            max(1, min(5, freshness))
        ),

        "dues": int(
            max(1, min(5, dues))
        ),

        "compliance": int(
            max(1, min(5, compliance))
        ),

        "purpose": int(
            max(1, min(5, purpose_score))
        ),
    }

def weighted_risk_1_to_5(scores: Dict[str, int]) -> float:
    return sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)


def safety_score_0_to_100(weighted_1_to_5_val: float) -> float:
    safety = ((5.0 - weighted_1_to_5_val) / 4.0) * 100.0
    return round(max(0.0, min(100.0, safety)), 2)


def decision_from_safety(s: float) -> str:
    if s >= 80:
        return "LOW_RISK_APPROVE"
    if s >= 60:
        return "APPROVE_WITH_CONDITIONS"
    if s >= 40:
        return "HOLD_VERIFY_REVALIDATE"
    return "HIGH_RISK_REJECT"


# -----------------------------
# EXPORT
# -----------------------------
def export_json(results: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def export_csv(results: List[Dict[str, Any]], path: str) -> None:
    if not results:
        return
    flat_rows: List[Dict[str, Any]] = []
    for r in results:
        rr = dict(r)
        fs = rr.pop("factor_scores_1to5", {})
        for k, v in fs.items():
            rr[f"factor_{k}_1to5"] = v
        flat_rows.append(rr)

    fieldnames = list(flat_rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(flat_rows)


def compute_project_scores(ex: Dict[str, Any]) -> Dict[str, int]:
    """
    Deterministic NOC risk scoring.

    IMPORTANT:
    1 = very good / low risk
    5 = very bad / high risk

    Missing information is NOT treated as a violation.
    Explicit negative evidence receives the higher penalty.
    """

    # ============================================================
    # NORMALIZE
    # ============================================================

    def text(value):
        return str(value or "").strip().lower()

    issuer = text(ex.get("issuer_name"))
    issuer_type = text(ex.get("issuer_type"))
    reference = text(ex.get("reference_no"))
    issue_date = text(ex.get("issue_date"))
    expiry_date = text(ex.get("expiry_date"))
    category = text(ex.get("noc_category"))
    purpose = text(ex.get("purpose"))
    dues_status = text(ex.get("dues_status"))
    conditions = text(ex.get("conditions"))

    try:
        confidence = float(
            ex.get("extraction_confidence", ex.get("confidence", 0))
            or 0
        )
    except Exception:
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))

    # ============================================================
    # 1. AUTHENTICITY / DOCUMENT IDENTITY
    # ============================================================

    authenticity = 1

    # No issuer = important missing evidence
    if not issuer:
        authenticity = max(authenticity, 3)

    # No reference number = missing identifier
    if not reference:
        authenticity = max(authenticity, 3)

    # Very poor extraction confidence
    if confidence < 0.40:
        authenticity = max(authenticity, 4)
    elif confidence < 0.60:
        authenticity = max(authenticity, 3)

    # Explicit negative evidence
    negative_identity_terms = [
        "fake",
        "forged",
        "invalid",
        "not genuine",
        "unrecognized",
        "unauthorized issuer",
    ]

    identity_text = (
        issuer + " " +
        issuer_type + " " +
        conditions
    )

    if any(
        term in identity_text
        for term in negative_identity_terms
    ):
        authenticity = 5

    # ============================================================
    # 2. FRESHNESS / VALIDITY
    # ============================================================

    freshness = 1

    issue_dt = parse_iso_date(issue_date)
    expiry_dt = parse_iso_date(expiry_date)

    today = datetime.now(timezone.utc).date()

    # ------------------------------------------------------------
    # Explicit expiry is strongest evidence
    # ------------------------------------------------------------

    if expiry_dt:

        if expiry_dt.date() < today:
            freshness = 5

        else:
            # Valid future expiry
            freshness = 1

    # ------------------------------------------------------------
    # No expiry
    # ------------------------------------------------------------

    elif issue_dt:

        age_days = (
            today - issue_dt.date()
        ).days

        if age_days < 0:
            # Future issue date
            freshness = 3

        elif age_days <= 365:
            freshness = 1

        elif age_days <= 3 * 365:
            freshness = 2

        elif age_days <= 5 * 365:
            freshness = 3

        else:
            freshness = 4

    else:

        # Missing dates = verification required,
        # NOT automatically expired.
        freshness = 3

    # Explicit invalidity
    validity_text = (
        expiry_date + " " +
        conditions
    )

    if any(
        term in validity_text
        for term in [
            "expired",
            "revoked",
            "cancelled",
            "withdrawn",
            "invalid",
        ]
    ):
        freshness = 5

    # ============================================================
    # 3. DUES
    # ============================================================

    dues = 3

    # Explicit no dues
    if any(
        term in dues_status
        for term in [
            "no_dues",
            "no dues",
            "nil dues",
            "no outstanding",
            "paid",
            "cleared",
        ]
    ):
        dues = 1

    # Explicit pending/outstanding
    elif any(
        term in dues_status
        for term in [
            "dues_pending",
            "dues pending",
            "pending",
            "outstanding",
            "unpaid",
            "arrears",
        ]
    ):
        dues = 5

    # Conditional payment
    elif any(
        term in dues_status
        for term in [
            "conditional",
            "subject to payment",
            "payment required",
        ]
    ):
        dues = 4

    # Check conditions for explicit financial problem
    if any(
        term in conditions
        for term in [
            "outstanding dues",
            "dues pending",
            "arrears",
            "unpaid amount",
            "payment overdue",
        ]
    ):
        dues = max(dues, 5)

    # ============================================================
    # 4. COMPLIANCE / CONDITIONS
    # ============================================================

    compliance = 1

    severe_terms = [
        "violation",
        "non-compliance",
        "non compliance",
        "unauthorized",
        "illegal",
        "rejected",
        "rejection",
        "revoked",
        "revocation",
        "cancelled",
        "cancellation",
        "withdrawn",
        "withdrawal",
        "stop work",
        "prohibited",
        "not permitted",
        "penalty",
        "court",
        "dispute",
    ]

    moderate_terms = [
        "subject to",
        "conditional",
        "pending",
        "shall comply",
        "must comply",
        "prior approval",
        "additional approval",
        "approval required",
        "permission required",
        "renewal required",
        "monitoring required",
        "charges payable",
        "payment required",
    ]

    positive_terms = [
        "no objection",
        "approved",
        "approval granted",
        "cleared",
        "clearance granted",
        "complied",
        "compliance confirmed",
    ]

    if any(
        term in conditions
        for term in severe_terms
    ):
        compliance = 5

    elif any(
        term in conditions
        for term in moderate_terms
    ):
        compliance = 3

    elif any(
        term in conditions
        for term in positive_terms
    ):
        compliance = 1

    elif conditions:
        # Conditions exist but no explicit negative statement
        compliance = 2

    # ============================================================
    # 5. PURPOSE / CATEGORY
    # ============================================================

    purpose_score = 2

    known_categories = {
        "fire",
        "electricity",
        "water",
        "pollution",
        "environment",
        "airport",
        "traffic",
        "railway",
        "planning",
        "construction",
    }

    if category in known_categories:
        purpose_score = 1
    elif category in ["other", ""]:
        purpose_score = 3

    # A clearly stated purpose improves evidence quality
    if purpose:
        purpose_score = max(
            1,
            purpose_score - 1
        )

    # Explicit mismatch should be a real risk
    mismatch_terms = [
        "mismatch",
        "does not match",
        "not applicable",
        "wrong purpose",
        "incorrect purpose",
    ]

    if any(
        term in (
            category + " " + purpose + " " + conditions
        )
        for term in mismatch_terms
    ):
        purpose_score = 5

    # ============================================================
    # RETURN
    # ============================================================

    return {
        "authenticity": max(
            1, min(5, authenticity)
        ),
        "freshness": max(
            1, min(5, freshness)
        ),
        "dues": max(
            1, min(5, dues)
        ),
        "compliance": max(
            1, min(5, compliance)
        ),
        "purpose": max(
            1, min(5, purpose_score)
        ),
    }

def save_noc_screenshots(
    pdf_paths,
    screenshot_dir,
    session_id,
    qwen_documents_by_pdf,
    dpi=220,
):
    """
    Save the FIRST PAGE of every NOC detected by Qwen Vision.

    qwen_documents_by_pdf:
        List of Qwen document lists, one list for each PDF.

    Example:
        [
            [
                {"pages": "1-1", ...},
                {"pages": "2-4", ...},
                {"pages": "5-14", ...}
            ]
        ]
    """

    os.makedirs(
        screenshot_dir,
        exist_ok=True
    )

    saved = []

    for pdf_index, pdf in enumerate(
        pdf_paths,
        start=1
    ):

        if not os.path.exists(pdf):
            continue

        pdf_doc = None

        try:

            # ------------------------------------
            # Open original PDF
            # ------------------------------------

            pdf_doc = fitz.open(pdf)

            # ------------------------------------
            # Get Qwen documents for this PDF
            # ------------------------------------

            if pdf_index - 1 >= len(
                qwen_documents_by_pdf
            ):
                print(
                    f"[SCREENSHOT] No Qwen documents "
                    f"available for PDF {pdf_index}"
                )
                continue

            docs = qwen_documents_by_pdf[
                pdf_index - 1
            ]

            if not docs:
                print(
                    f"[SCREENSHOT] No NOCs detected "
                    f"for PDF {pdf_index}"
                )
                continue

            # ------------------------------------
            # First page of first 3 Qwen NOCs
            # ------------------------------------

            print(
                f"[SCREENSHOT] Selecting first "
                f"{min(3, len(docs))} NOCs"
            )


            for noc_index, noc in enumerate(
                docs[:3],
                start=1
            ):

                pages_range = str(
                    noc.get("pages", "")
                ).strip()

                if not pages_range:
                    print(
                        f"[SCREENSHOT] NOC {noc_index} "
                        f"has no page range"
                    )
                    continue

                # --------------------------------
                # Parse first page from:
                #
                # "1-1"
                # "2-4"
                # "15-48"
                # --------------------------------

                try:

                    start_page = int(
                        pages_range.split("-")[0]
                    )

                except (ValueError, IndexError):

                    print(
                        f"[SCREENSHOT] Invalid page range "
                        f"'{pages_range}' "
                        f"for NOC {noc_index}"
                    )

                    continue

                # Qwen pages are 1-based
                page_index = start_page - 1

                if (
                    page_index < 0
                    or page_index >= len(pdf_doc)
                ):
                    print(
                        f"[SCREENSHOT] Invalid page "
                        f"{start_page} for PDF "
                        f"{pdf_index}"
                    )
                    continue

                # --------------------------------
                # Render first page of NOC
                # --------------------------------

                page = pdf_doc.load_page(
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

                # --------------------------------
                # Save screenshot
                # --------------------------------

                output_path = os.path.join(
                    screenshot_dir,
                    f"noc_result_"
                    f"{pdf_index}_"
                    f"{noc_index}_"
                    f"{session_id}.png"
                )

                img.save(
                    output_path,
                    format="PNG"
                )

                saved.append(
                    output_path
                )

                print(
                    f"Saved NOC evidence screenshot → "
                    f"{output_path}"
                )

        except Exception as e:

            print(
                f"Failed to create NOC screenshots "
                f"for {pdf}: {e}"
            )

        finally:

            if pdf_doc is not None:
                pdf_doc.close()

    return saved

def process_pdfs(
    pdf_paths: List[str],
    risk_client=None,
    screenshot_dir: str = None,
    session_id: str = None
) -> List[Dict[str, Any]]:

    results = []

    # Store Qwen-detected NOCs for every PDF.
    all_grouped_documents = []

    for pdf_index, pdf in enumerate(pdf_paths, start=1):

        if not os.path.exists(pdf):
            print(f"⚠️ PDF not found: {pdf}")
            continue

        # ============================================================
        # PDF -> PAGE IMAGES
        # ============================================================

        page_images = pdf_pages_to_images(
            pdf,
            dpi=120,
            jpeg_quality=65
        )

        if not page_images:
            print("⚠️ No pages found")
            continue

        print(
            f"[QWEN-VISION] "
            f"{len(page_images)} page images ready"
        )

        # ============================================================
        # QWEN MUST RETURN PAGE-LEVEL RESULTS
        #
        # Expected:
        #
        # {
        #   "pages": [
        #       {
        #           "page_number": 1,
        #           "is_noc": false,
        #           "page_data": {}
        #       },
        #       {
        #           "page_number": 2,
        #           "is_noc": true,
        #           "page_data": {...}
        #       }
        #   ]
        # }
        # ============================================================

        qwen_result = extract_nocs_from_images_qwen(
            page_images
        )

        page_results = qwen_result.get(
            "pages",
            []
        )

        if not isinstance(page_results, list):
            page_results = []

        # ============================================================
        # NORMALIZE PAGE RESULTS
        # ============================================================

        normalized_pages = []

        for item in page_results:

            if not isinstance(item, dict):
                continue

            page_number = item.get(
                "page_number"
            )

            if page_number is None:
                continue

            try:
                page_number = int(page_number)
            except Exception:
                continue

            is_noc = bool(
                item.get(
                    "is_noc",
                    False
                )
            )

            page_data = item.get(
                "page_data",
                {}
            )

            if not isinstance(
                page_data,
                dict
            ):
                page_data = {}

            normalized_pages.append({
                "page_number": page_number,
                "is_noc": is_noc,
                "page_data": page_data
            })

        # Keep PDF order
        normalized_pages.sort(
            key=lambda x: x["page_number"]
        )

        print(
            f"[QWEN-VISION] "
            f"Received {len(normalized_pages)} "
            f"page-level results"
        )

        if not normalized_pages:
            print(
                "[WARNING] Qwen returned no "
                "page-level NOC data"
            )
            continue

        # ============================================================
        # GROUP PAGES INTO COMPLETE NOCs
        #
        # IMPORTANT:
        #
        # We DO NOT create one NOC per page.
        #
        # A document continues while pages contain evidence that
        # they belong to the same certificate.
        #
        # The grouping function should use:
        #   - reference number
        #   - issuer
        #   - category
        #   - certificate title
        #   - continuation-page signals
        #   - page sequence
        # ============================================================

        grouped_documents = group_noc_pages(
            normalized_pages
        )

        # Keep the detected NOC groups for this PDF so screenshots
        # are generated from the correct PDF/page.
        all_grouped_documents.append(
            grouped_documents
        )

        print(
            "\n" + "=" * 100
        )
        print(
            "📚 GROUPED NOC DOCUMENTS"
        )
        print(
            "=" * 100
        )

        for i, doc in enumerate(
            grouped_documents,
            start=1
        ):

            print(
                f"NOC {i}: "
                f"pages {doc['start_page']}-"
                f"{doc['end_page']} | "
                f"category={doc.get('noc_category', '')} | "
                f"issuer={doc.get('issuer_name', '')}"
            )

        # ============================================================
        # SCORE EACH COMPLETE NOC
        # ============================================================

        for noc_index, grouped_doc in enumerate(
            grouped_documents,
            start=1
        ):

            # --------------------------------------------------------
            # ACTUAL PAGE DATA
            # --------------------------------------------------------

            grouped_page_data = grouped_doc.get(
                "page_data",
                []
            )

            if not isinstance(
                grouped_page_data,
                list
            ):
                grouped_page_data = []

            if not grouped_page_data:
                continue

            # --------------------------------------------------------
            # MERGE ALL PAGES OF THIS ONE NOC
            # --------------------------------------------------------

            merged = merge_noc_pages(
                grouped_page_data
            )

            if not isinstance(
                merged,
                dict
            ):
                print(
                    f"[WARNING] NOC {noc_index}: "
                    "merge_noc_pages returned invalid data"
                )
                continue
            start_page = grouped_doc[
                "start_page"
            ]

            end_page = grouped_doc[
                "end_page"
            ]

            # ========================================================
            # COMPLETE NOC RESULT
            # ========================================================

            result = {
                "doc_index": len(results) + 1,

                "pdf_index": pdf_index,

                "pdf_path": pdf,

                "pages": (
                    f"{start_page}-{end_page}"
                    if start_page != end_page
                    else str(start_page)
                ),

                "start_page": start_page,

                "end_page": end_page,

                "issuer_name": merged.get(
                    "issuer_name",
                    ""
                ),

                "issuer_type": merged.get(
                    "issuer_type",
                    ""
                ),

                "reference_no": merged.get(
                    "reference_no",
                    ""
                ),

                "issue_date": merged.get(
                    "issue_date",
                    ""
                ),

                "expiry_date": merged.get(
                    "expiry_date",
                    ""
                ),

                "noc_category": merged.get(
                    "noc_category",
                    "other"
                ),

                "purpose": merged.get(
                    "purpose",
                    ""
                ),

                "dues_status": merged.get(
                    "dues_status",
                    "not_mentioned"
                ),

                "dues_amount": merged.get(
                    "dues_amount",
                    0
                ),

                "conditions": merged.get(
                    "conditions",
                    ""
                ),

                "extraction_confidence": merged.get(
                    "confidence",
                    0.0
                ),

                # Keep the original page-level evidence.
                "source_pages": grouped_page_data
            }

            # ========================================================
            # DETERMINISTIC SCORE
            # ========================================================

            try:

                factor_scores = compute_factor_scores(
                    result
                )

                weighted_score = (
                    weighted_risk_1_to_5(
                        factor_scores
                    )
                )

                deterministic_safety = (
                    safety_score_0_to_100(
                        weighted_score
                    )
                )

                deterministic_risk = round(
                    100.0 -
                    deterministic_safety,
                    2
                )

                result[
                    "factor_scores_1to5"
                ] = factor_scores

                result[
                    "deterministic_safety_score"
                ] = deterministic_safety

                result[
                    "deterministic_risk_score"
                ] = deterministic_risk

                result[
                    "deterministic_decision"
                ] = decision_from_safety(
                    deterministic_safety
                )

            except Exception as e:

                print(
                    "[WARNING] Deterministic "
                    f"scoring failed for NOC "
                    f"{noc_index}: {e}"
                )

                result[
                    "factor_scores_1to5"
                ] = {}

                result[
                    "deterministic_safety_score"
                ] = None

                result[
                    "deterministic_risk_score"
                ] = None

                result[
                    "deterministic_decision"
                ] = None

            # ========================================================
            # LLM SCORE
            # ========================================================

            if risk_client is not None:

                try:

                    llm_result = llm_safety_score(
                        result,
                        risk_client
                    )

                    llm_safety = (
                        llm_result.get(
                            "safety_score_0_100"
                        )
                    )

                    if llm_safety is not None:

                        llm_safety = max(
                            0.0,
                            min(
                                100.0,
                                float(
                                    llm_safety
                                )
                            )
                        )

                        llm_risk = round(
                            100.0 -
                            llm_safety,
                            2
                        )

                    else:

                        llm_safety = None
                        llm_risk = None

                    result[
                        "llm_safety_score"
                    ] = llm_safety

                    result[
                        "llm_risk_score"
                    ] = llm_risk

                    result[
                        "llm_confidence"
                    ] = llm_result.get(
                        "confidence",
                        0.0
                    )

                    result[
                        "llm_top_risks"
                    ] = llm_result.get(
                        "top_risks",
                        []
                    )

                    result[
                        "llm_notes"
                    ] = llm_result.get(
                        "notes",
                        ""
                    )

                except Exception as e:

                    print(
                        "[WARNING] LLM risk "
                        f"scoring failed for NOC "
                        f"{noc_index}: {e}"
                    )

                    result[
                        "llm_safety_score"
                    ] = None

                    result[
                        "llm_risk_score"
                    ] = None

                    result[
                        "llm_confidence"
                    ] = 0.0

                    result[
                        "llm_top_risks"
                    ] = []

                    result[
                        "llm_notes"
                    ] = str(e)

            else:

                result[
                    "llm_safety_score"
                ] = None

                result[
                    "llm_risk_score"
                ] = None

                result[
                    "llm_confidence"
                ] = 0.0

                result[
                    "llm_top_risks"
                ] = []

                result[
                    "llm_notes"
                ] = "LLM risk scoring disabled"

            # ========================================================
            # FINAL NOC SCORE
            #
            # 70% Python
            # 30% LLM
            # ========================================================

            deterministic = result.get(
                "deterministic_safety_score"
            )

            llm = result.get(
                "llm_safety_score"
            )

            if (
                deterministic is not None
                and llm is not None
            ):

                final_safety = round(
                    (
                        0.70 *
                        float(deterministic)
                    )
                    +
                    (
                        0.30 *
                        float(llm)
                    ),
                    2
                )

            elif deterministic is not None:

                final_safety = round(
                    float(deterministic),
                    2
                )

            elif llm is not None:

                final_safety = round(
                    float(llm),
                    2
                )

            else:

                final_safety = None

            result[
                "final_safety_score"
            ] = final_safety

            result[
                "final_risk_score"
            ] = (
                round(
                    100.0 -
                    final_safety,
                    2
                )
                if final_safety is not None
                else None
            )

            result[
                "final_decision"
            ] = (
                decision_from_safety(
                    final_safety
                )
                if final_safety is not None
                else None
            )

            results.append(result)


    # ============================================================
    # SAVE NOC SCREENSHOTS
    # ============================================================
    #
    # IMPORTANT:
    # We save screenshots from the FINAL scored `results`.
    # Each result already contains:
    #   - pdf_index
    #   - start_page
    #
    # Therefore this cannot accidentally select the wrong PDF or
    # lose the Qwen grouping information.
    # ============================================================

    saved_paths = []

    if screenshot_dir:
        try:

            os.makedirs(
                screenshot_dir,
                exist_ok=True
            )

            if not session_id:
                session_id = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )

            for result in results:

                pdf_index = result.get(
                    "pdf_index"
                )

                start_page = result.get(
                    "start_page"
                )

                noc_index = result.get(
                    "doc_index"
                )

                if pdf_index is None:
                    print(
                        "[SCREENSHOT] Missing pdf_index "
                        f"for NOC {noc_index}"
                    )
                    continue

                if start_page is None:
                    print(
                        "[SCREENSHOT] Missing start_page "
                        f"for NOC {noc_index}"
                    )
                    continue

                try:
                    pdf_index = int(
                        pdf_index
                    )

                    start_page = int(
                        start_page
                    )

                except (
                    TypeError,
                    ValueError
                ):
                    print(
                        "[SCREENSHOT] Invalid page/PDF index "
                        f"for NOC {noc_index}: "
                        f"pdf_index={pdf_index}, "
                        f"start_page={start_page}"
                    )
                    continue

                pdf_position = (
                    pdf_index - 1
                )

                if (
                    pdf_position < 0
                    or pdf_position >= len(pdf_paths)
                ):
                    print(
                        "[SCREENSHOT] PDF index out of range: "
                        f"{pdf_index}"
                    )
                    continue

                pdf_path = pdf_paths[
                    pdf_position
                ]

                if not os.path.isfile(
                    pdf_path
                ):
                    print(
                        "[SCREENSHOT] PDF not found: "
                        f"{pdf_path}"
                    )
                    continue

                page_index = (
                    start_page - 1
                )

                if page_index < 0:
                    print(
                        "[SCREENSHOT] Invalid start page "
                        f"{start_page} for NOC "
                        f"{noc_index}"
                    )
                    continue

                pdf_doc = None

                try:

                    pdf_doc = fitz.open(
                        pdf_path
                    )

                    if page_index >= len(
                        pdf_doc
                    ):
                        print(
                            "[SCREENSHOT] Page "
                            f"{start_page} does not exist "
                            f"in {pdf_path}"
                        )
                        continue

                    page = pdf_doc.load_page(
                        page_index
                    )

                    pix = page.get_pixmap(
                        dpi=220,
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
                        (
                            f"noc_result_"
                            f"{pdf_index}_"
                            f"{noc_index}_"
                            f"{session_id}.png"
                        )
                    )

                    img.save(
                        output_path,
                        format="PNG"
                    )

                    if os.path.isfile(
                        output_path
                    ):
                        saved_paths.append(
                            output_path
                        )

                        print(
                            "[SCREENSHOT] SAVED: "
                            f"{output_path}"
                        )

                    else:
                        print(
                            "[SCREENSHOT] FAILED TO VERIFY: "
                            f"{output_path}"
                        )

                except Exception as e:

                    print(
                        "[SCREENSHOT ERROR] "
                        f"NOC={noc_index} | "
                        f"PDF={pdf_path} | "
                        f"page={start_page} | "
                        f"{type(e).__name__}: {e}"
                    )

                finally:

                    if pdf_doc is not None:
                        pdf_doc.close()

        except Exception as e:

            print(
                "[SCREENSHOT ERROR] "
                f"{type(e).__name__}: {e}"
            )

    print(
        f"[SCREENSHOT] Total saved: "
        f"{len(saved_paths)}"
    )

    # Expose the paths to run_noc_wrapper().
    process_pdfs.last_screenshot_paths = (
        saved_paths
    )

    # ================================================================
    # FINAL OUTPUT
    # ================================================================

    print(
        "\n" + "=" * 100
    )

    print(
        "📦 FINAL NOC DATA + RISK SCORES"
    )

    print(
        "=" * 100
    )



    print(
        "\n" + "=" * 100
    )

    print(
        f"✅ TOTAL NOC DOCUMENTS: "
        f"{len(results)}"
    )

    print(
        "=" * 100
    )

    return results

def run_noc_wrapper(
    pdf_paths: List[str],
    export_files: bool = False,
    export_json_path: str = "noc_scores.json",
    export_csv_path: str = "noc_scores.csv",
    tesseract_cmd: Optional[str] = None,
    session_id: str = None,
    screenshot_dir: str = SCREENSHOT_DIR
) -> Dict[str, Any]:

    print(
        f"DEBUG: run_noc_wrapper received "
        f"{len(pdf_paths)} PDF(s)"
    )
    # ============================================================
    # NOC SCREENSHOT DIRECTORY
    # ============================================================

    screenshot_dir = (
        screenshot_dir
        or SCREENSHOT_DIR
        or r"D:\aasthiv2\Aasthi\riskwrapper\screenshots"
    )

    screenshot_dir = os.path.abspath(
        screenshot_dir
    )

    os.makedirs(
        screenshot_dir,
        exist_ok=True
    )

    if not session_id:
        session_id = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

    session_id = str(session_id).strip()

    print(
        f"[SCREENSHOT] Output directory: {screenshot_dir}"
    )

    print(
        f"[SCREENSHOT] Session ID: {session_id}"
    )
    # ------------------------------------
    # Tesseract
    # ------------------------------------

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = (
            tesseract_cmd
        )

    # ------------------------------------
    # Validate PDFs
    # ------------------------------------

    valid_pdfs = []

    for p in pdf_paths:

        if not p:
            continue

        if not os.path.exists(p):

            print(
                f"⚠️ PDF not found: {p}"
            )

            continue

        valid_pdfs.append(p)

    if not valid_pdfs:
        raise RuntimeError(
            "No valid NOC PDF files were provided."
        )

    # ------------------------------------
    # Gemini risk client
    # ------------------------------------

    risk_client = None

    try:

        risk_client = get_claude_client()

        print(
            "[INFO] Gemini risk scoring enabled."
        )

    except Exception as e:

        print(
            "[INFO] Gemini risk scoring disabled: "
            f"{e}"
        )

        risk_client = None

    # ------------------------------------
    # Process PDFs
    # ------------------------------------
    saved_paths = []

    try:

        results = process_pdfs(
            valid_pdfs,
            risk_client=risk_client,
            screenshot_dir=screenshot_dir,
            session_id=session_id
        )

        # saved_paths belongs to process_pdfs(), so retrieve it here.
        saved_paths = getattr(
            process_pdfs,
            "last_screenshot_paths",
            []
        )

    except Exception as e:

        raise RuntimeError(
            f"NOC processing failed: {e}"
        ) from e

    # ------------------------------------
    # Project scores
    # ------------------------------------
    #
    # IMPORTANT:
    # `project_scores` was previously created as a LIST here, but the
    # final-result code below expects a DICT and calls:
    #
    #     project_scores.get("final", {})
    #
    # That caused:
    #     AttributeError: 'list' object has no attribute 'get'
    #
    # Keep the per-document scores, but also build the aggregate
    # structure expected by the final-result section.

    document_scores = []

    for result in results:
        if not isinstance(result, dict):
            continue

        score = compute_project_scores(result)

        document_scores.append({
            "doc_index": result.get("doc_index"),
            "pages": result.get("pages"),
            "issuer_name": result.get("issuer_name"),
            "reference_no": result.get("reference_no"),
            "noc_category": result.get("noc_category"),
            "scores": score,
            "deterministic_safety_score": result.get(
                "deterministic_safety_score"
            ),
            "deterministic_risk_score": result.get(
                "deterministic_risk_score"
            ),
            "llm_safety_score": result.get(
                "llm_safety_score"
            ),
            "llm_risk_score": result.get(
                "llm_risk_score"
            ),
            "final_safety_score": result.get(
                "final_safety_score"
            ),
            "final_risk_score": result.get(
                "final_risk_score"
            ),
            "final_decision": result.get(
                "final_decision"
            ),
        })

    def _values(key):
        return [
            float(r[key])
            for r in results
            if isinstance(r, dict)
            and r.get(key) is not None
        ]

    def _stats(values):
        if not values:
            return {
                "min": None,
                "avg": None,
                "max": None,
                "risk_min": None,
                "risk_avg": None,
                "risk_max": None,
            }

        return {
            "min": round(min(values), 2),
            "avg": round(sum(values) / len(values), 2),
            "max": round(max(values), 2),
        }

    deterministic_safety = _values(
        "deterministic_safety_score"
    )
    deterministic_risk = _values(
        "deterministic_risk_score"
    )
    llm_safety = _values(
        "llm_safety_score"
    )
    llm_risk = _values(
        "llm_risk_score"
    )
    final_safety = _values(
        "final_safety_score"
    )
    final_risk = _values(
        "final_risk_score"
    )

    deterministic_stats = _stats(deterministic_safety)
    deterministic_stats.update({
        "risk_min": round(min(deterministic_risk), 2)
        if deterministic_risk else None,
        "risk_avg": round(
            sum(deterministic_risk) / len(deterministic_risk), 2
        )
        if deterministic_risk else None,
        "risk_max": round(max(deterministic_risk), 2)
        if deterministic_risk else None,
    })

    llm_stats = _stats(llm_safety)
    llm_stats.update({
        "risk_min": round(min(llm_risk), 2)
        if llm_risk else None,
        "risk_avg": round(
            sum(llm_risk) / len(llm_risk), 2
        )
        if llm_risk else None,
        "risk_max": round(max(llm_risk), 2)
        if llm_risk else None,
    })

    final_stats = _stats(final_safety)
    final_stats.update({
        "risk_min": round(min(final_risk), 2)
        if final_risk else None,
        "risk_avg": round(
            sum(final_risk) / len(final_risk), 2
        )
        if final_risk else None,
        "risk_max": round(max(final_risk), 2)
        if final_risk else None,
    })

    # Match the structure expected by the final-result section.
    project_scores = {
        "deterministic": deterministic_stats,
        "llm": llm_stats,
        "final": final_stats,
        "documents": document_scores,
        "overall_decision_conservative": (
            decision_from_safety(min(final_safety))
            if final_safety else None
        ),
        "overall_decision_average": (
            decision_from_safety(
                sum(final_safety) / len(final_safety)
            )
            if final_safety else None
        ),
    }

    # ------------------------------------
    # Exports
    # ------------------------------------

    exports = {
        "json": None,
        "csv": None
    }

    if export_files:

        try:

            export_csv(
                results,
                export_csv_path
            )

            print(
                "[EXPORT] CSV saved: "
                f"{export_csv_path}"
            )

            exports["csv"] = (
                export_csv_path
            )

        except Exception as e:

            print(
                "[EXPORT] CSV export failed: "
                f"{e}"
            )

    # ------------------------------------
    # Final result
    # ------------------------------------

    final_scores = project_scores.get("final", {})

    overall_safety_score = final_scores.get("avg")
    overall_risk_score = final_scores.get("risk_avg")

    if overall_risk_score is None and overall_safety_score is not None:
        overall_risk_score = round(100 - float(overall_safety_score), 2)

    if overall_safety_score is None and overall_risk_score is not None:
        overall_safety_score = round(100 - float(overall_risk_score), 2)

    if overall_risk_score is not None:
        if overall_risk_score >= 70:
            overall_risk_level = "HIGH RISK"
        elif overall_risk_score >= 40:
            overall_risk_level = "MEDIUM RISK"
        else:
            overall_risk_level = "LOW RISK"
    else:
        overall_risk_level = "UNKNOWN"

    # Explicit project-level values.
    project_scores["overall_safety_score"] = (
        overall_safety_score
    )
    project_scores["overall_risk_score"] = (
        overall_risk_score
    )
    project_scores["overall_risk_level"] = (
        overall_risk_level
    )

    # generate_pdf_report.py reads this field for NOC.
    project_scores["final"]["risk_avg"] = (
        overall_risk_score
    )
    project_scores["final"]["safety_avg"] = (
        overall_safety_score
    )

    # ============================================================
    # EXPORT FINAL JSON AFTER OVERALL SCORE IS CALCULATED
    # ============================================================
    #
    # IMPORTANT:
    # Do NOT export only `results`.
    # The final JSON must contain the project-level overall score.
    # ============================================================

    if export_files:

        try:

            json_report = {
                "documents_scored": len(results),

                "overall_risk_score": (
                    overall_risk_score
                ),

                "overall_safety_score": (
                    overall_safety_score
                ),

                "overall_risk_level": (
                    overall_risk_level
                ),

                "project_scores": (
                    project_scores
                ),

                "results": results,

                "screenshots": (
                    saved_paths
                ),

                "session_id": (
                    session_id
                ),

                "screenshot_dir": (
                    screenshot_dir
                ),

                "tesseract_cmd": (
                    TESSERACT_CMD
                    if TESSERACT_CMD
                    else None
                )
            }

            with open(
                export_json_path,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    json_report,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str
                )

            print(
                "[EXPORT] FINAL JSON saved: "
                f"{export_json_path}"
            )

            exports["json"] = (
                export_json_path
            )

        except Exception as e:

            print(
                "[EXPORT] Final JSON export failed: "
                f"{type(e).__name__}: {e}"
            )

    print(
        "\n" + "=" * 100
    )
    print(
        "📊 NOC OVERALL RISK SCORE"
    )
    print(
        "=" * 100
    )
    print(
        f"Total NOC Documents : {len(results)}"
    )
    print(
        f"Overall Safety Score: {overall_safety_score}"
    )
    print(
        f"Overall Risk Score  : {overall_risk_score}"
    )
    print(
        f"Overall Risk Level  : {overall_risk_level}"
    )
    print(
        f"Screenshots Saved   : {len(saved_paths)}"
    )
    print(
        "=" * 100
    )

    return {
        "documents_scored": len(results),

        "overall_risk_score": overall_risk_score,
        "overall_safety_score": overall_safety_score,
        "overall_risk_level": overall_risk_level,

        "project_scores": project_scores,

        "results": results,

        "screenshots": saved_paths,

        "session_id": session_id,

        "screenshot_dir": screenshot_dir,

        "exports": exports,

        "tesseract_cmd": (
            TESSERACT_CMD
            if TESSERACT_CMD
            else None
        )
    }
if __name__ == "__main__":

    from datetime import datetime

    PDF_PATHS = [
        r"D:\aasthiv2\Aasthi\wrappercode\input\noc\NOC.pdf"
    ]

    SCREENSHOT_DIR = (
        r"D:\aasthiv2\Aasthi\riskwrapper\screenshots"
    )

    SESSION_ID = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    result = run_noc_wrapper(
        pdf_paths=PDF_PATHS,
        export_files=True,
        session_id=SESSION_ID,
        screenshot_dir=SCREENSHOT_DIR,
    )

    print("\n" + "=" * 90)
    print("📦 FINAL NOC RESULT")
    print("=" * 90)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str
        )
    )

    print("=" * 90)