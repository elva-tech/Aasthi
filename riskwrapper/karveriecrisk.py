"""
====================================================================
APARTMENT TITLE CHECK — REQUIRED DOCUMENTS
====================================================================

THIS WRAPPER IS FOR RESIDENTIAL APARTMENTS ONLY.

PRIMARY DOCUMENTS REQUIRED
--------------------------
1. ACTUAL REGISTERED SALE DEED OF THE APARTMENT
   - Most important apartment-specific title document.
   - Must contain seller, purchaser, apartment number, tower/building,
     UDS, area, consideration and registration details.

2. PARENT / MOTHER TITLE DEEDS
   - Sale deeds, partition deeds, exchange deeds, gift deeds,
     settlement deeds or other documents by which the land owners
     acquired the underlying land.
   - These establish the parent title chain.

3. JOINT DEVELOPMENT AGREEMENT (JDA)
   - Required where the developer is not the original land owner.
   - Check registered document number/date, land owners, developer,
     development rights and sharing/allocation terms.

4. POWER OF ATTORNEY (GPA)
   - Required where the developer/representative signs or sells
     on behalf of land owners.
   - Verify registration details and authority granted.

5. LAND CONVERSION ORDER / CONVERSION CERTIFICATE
   - Required where agricultural land was converted for residential use.
   - Verify survey numbers, extent and conversion order details.

6. RERA UPLOADED TITLE / LAND DOCUMENTS
   - Use RERA as an additional source, not as a replacement for
     registered title documents.
   - Useful documents include:
       * Land documents and location
       * Title deed / title-related documents
       * JDA / development documents
       * GPA / authorization documents
       * Conversion certificate
       * Approved plans / approvals
       * Encumbrance Certificate
       * Any other Rights/Title/Interest/Name document

7. ENCUMBRANCE CERTIFICATE (EC)
   - EC is a SUPPORTING CHECK for registered transactions,
     mortgages/charges and other registered entries.
   - EC does NOT by itself prove complete title.
   - Kaveri/EC and Title Check are related but NOT the same check.

IMPORTANT
---------
For a COMPLETE apartment title check, the wrapper should not mark
title as verified merely because RERA data or an EC is available.

The minimum strong combination is:
    Actual Sale Deed
    + Parent/Mother Deeds
    + JDA (if applicable)
    + GPA (if applicable)
    + Conversion Order (if applicable)
    + RERA title documents
    + EC

OUTPUT PHILOSOPHY
-----------------
The wrapper separates:
    A. DOCUMENT EXTRACTION
    B. TITLE-CHAIN ANALYSIS
    C. DEVELOPER AUTHORITY ANALYSIS
    D. EC TRANSACTION ANALYSIS
    E. FINAL BUYER-CENTRIC RISK

Missing documents are reported as "MISSING / NOT PROVIDED".
They are NOT treated as proof of fraud.

====================================================================
"""

import os
import json
import re
from typing import Any, Dict, List, Optional, Union

import fitz
from PIL import Image
from anthropic import Anthropic
from openai import OpenAI


# ====================================================================
# MODELS
# ====================================================================

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

EXTRACTION_MODEL = "qwen3:8b"

MODEL = "claude-opus-4-7"

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)


# ====================================================================
# GENERAL PDF HELPERS
# ====================================================================

def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF while preserving page boundaries."""
    doc = fitz.open(pdf_path)
    pages = []

    try:
        for page_no, page in enumerate(doc, start=1):
            page_text = page.get_text()
            if page_text:
                pages.append(
                    f"\n===== PAGE {page_no} =====\n{page_text}"
                )
    finally:
        doc.close()

    return "\n".join(pages)


def create_evidence_screenshot(
    pdf_path: str,
    output_path: str,
    keywords: Optional[List[str]] = None,
    max_pages: int = 3,
    dpi: int = 180,
) -> None:
    """
    Create a compact evidence image from the most relevant PDF pages.

    This is evidence only. It does not replace document extraction.
    """
    if keywords is None:
        keywords = [
            "title deed",
            "sale deed",
            "joint development",
            "power of attorney",
            "conversion",
            "survey",
            "schedule a",
            "schedule b",
            "schedule c",
            "registered",
            "document no",
        ]

    doc = fitz.open(pdf_path)

    try:
        scored_pages = []

        for page_no in range(len(doc)):
            text = doc[page_no].get_text().lower()
            score = sum(1 for keyword in keywords if keyword in text)

            scored_pages.append((page_no, score))

        scored_pages.sort(key=lambda item: item[1], reverse=True)

        selected = [
            page_no
            for page_no, score in scored_pages[:max_pages]
            if score > 0
        ]

        if not selected:
            selected = list(range(min(max_pages, len(doc))))

        images = []

        for page_no in selected:
            page = doc.load_page(page_no)
            pix = page.get_pixmap(dpi=dpi, alpha=False)

            image = Image.frombytes(
                "RGB",
                (pix.width, pix.height),
                pix.samples,
            )

            images.append(image)

        if not images:
            return

        width = max(image.width for image in images)
        height = sum(image.height for image in images)

        canvas = Image.new("RGB", (width, height), "white")

        y = 0
        for image in images:
            canvas.paste(image, (0, y))
            y += image.height

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        canvas.save(output_path)

    finally:
        doc.close()


# ====================================================================
# TEXT CHUNKING
# ====================================================================

def split_text(text: str, max_chars: int = 8500) -> List[str]:
    """
    Split long PDF text into manageable chunks.

    Qwen extraction is deliberately chunked so that a long Sale Deed
    does not exceed the local model context.
    """
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = []

    current_len = 0

    paragraphs = re.split(
        r"\n(?===== PAGE |\s*$)",
        text,
    )

    # If the page split did not work well, fall back to line groups.
    if len(paragraphs) <= 1:
        paragraphs = text.split("\n")

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if current and current_len + len(paragraph) + 1 > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

        current.append(paragraph)
        current_len += len(paragraph) + 1

    if current:
        chunks.append("\n".join(current))

    return chunks


# ====================================================================
# JSON HELPERS
# ====================================================================

def parse_json_response(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()

    raw = raw.replace("```json", "")
    raw = raw.replace("```", "").strip()

    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)

    if match:
        value = json.loads(match.group(0))
        if isinstance(value, dict):
            return value

    raise ValueError("Model returned invalid JSON")


# ====================================================================
# TITLE DOCUMENT CLASSIFICATION
# ====================================================================

def classify_title_document(pdf_path: str) -> Dict[str, Any]:
    """
    Classify one supplied PDF into a title-document category.

    This is deliberately conservative.
    """
    text = extract_pdf_text(pdf_path)

    prompt = f"""
You are a Karnataka apartment title-document classifier.

Classify the supplied document ONLY from information actually visible
in the supplied text.

Allowed document types:
- ACTUAL_SALE_DEED
- PARENT_TITLE_DEED
- MOTHER_DEED
- JOINT_DEVELOPMENT_AGREEMENT
- POWER_OF_ATTORNEY
- CONVERSION_ORDER
- RERA_TITLE_DOCUMENT
- ENCUMBRANCE_CERTIFICATE
- AGREEMENT_FOR_SALE
- DEED_OF_DECLARATION
- OTHER_TITLE_DOCUMENT
- UNKNOWN

Return ONLY JSON:

{{
  "document_type": "",
  "confidence": 0.0,
  "title_relevance": "HIGH|MEDIUM|LOW",
  "reason": ""
}}

Do not invent information.

DOCUMENT:
{text[:12000]}
""".strip()

    response = qwen_client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify Karnataka apartment title documents. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
        max_tokens=800,
        response_format={"type": "json_object"},
    )

    return parse_json_response(
        response.choices[0].message.content
    )


# ====================================================================
# TITLE FACT EXTRACTION
# ====================================================================

def extract_title_facts(
    pdf_path: str,
    document_type: str = "UNKNOWN",
) -> Dict[str, Any]:
    """
    Extract title-chain facts from a supplied title document.

    The function works page/chunk-wise to avoid sending a long Sale Deed
    in one request.
    """
    text = extract_pdf_text(pdf_path)

    chunks = split_text(text, max_chars=8500)

    all_facts = []

    for index, chunk in enumerate(chunks, start=1):

        prompt = f"""
You are a Karnataka residential apartment title-document extraction
specialist.

The document is classified as:
{document_type}

Extract ONLY facts visibly present in this document chunk.

The purpose is apartment TITLE DUE DILIGENCE.

Look especially for:

1. Land owners
2. Developer / builder
3. Seller
4. Purchaser
5. Project name
6. Apartment number
7. Building / tower
8. Floor
9. Carpet area
10. Super built-up area
11. Undivided share (UDS)
12. Survey numbers
13. Village
14. Hobli
15. Taluk
16. District
17. Land extent
18. Acquisition deed numbers/dates
19. Parent title documents
20. JDA numbers/dates
21. GPA numbers/dates
22. Conversion order numbers/dates
23. Sub-Registrar Office
24. Registration document numbers
25. Deed of Declaration
26. Occupancy Certificate reference
27. Statements about title/ownership
28. Statements about authority to sell
29. Encumbrance references
30. Any title limitation, dispute, restriction, acquisition,
    mortgage or adverse claim explicitly stated

IMPORTANT:
- Do NOT treat a project approval as proof of title.
- Do NOT treat an EC as proof of complete title.
- Do NOT invent missing information.
- Preserve document numbers exactly where possible.
- If a field is not present in this chunk, leave it empty.
- A document may contain multiple owners.
- Keep all visible owner names.
- Do not confuse project promoter with land owner.
- Do not confuse developer with seller unless the document says so.

Return ONLY JSON:

{{
  "document_type": "{document_type}",
  "land_owners": [],
  "developer": "",
  "seller": "",
  "purchaser": "",
  "project_name": "",
  "apartment_number": "",
  "building": "",
  "tower": "",
  "floor": "",
  "carpet_area": "",
  "super_built_up_area": "",
  "uds": "",
  "survey_numbers": [],
  "village": "",
  "hobli": "",
  "taluk": "",
  "district": "",
  "land_extent": "",
  "parent_documents": [],
  "jda_documents": [],
  "gpa_documents": [],
  "conversion_documents": [],
  "registration_documents": [],
  "sro": "",
  "deed_of_declaration": "",
  "occupancy_certificate": "",
  "title_statements": [],
  "authority_to_sell_statements": [],
  "adverse_title_statements": [],
  "other_title_facts": []
}}

DOCUMENT CHUNK {index}:

{chunk}
""".strip()

        try:
            response = qwen_client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract Karnataka property title facts. "
                            "Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                max_tokens=1800,
                response_format={"type": "json_object"},
            )

            result = parse_json_response(
                response.choices[0].message.content
            )

            all_facts.append(result)

        except Exception as exc:
            print(
                f"[WARNING] Title extraction chunk "
                f"{index}/{len(chunks)} failed: {exc}"
            )

    return merge_title_facts(all_facts)


# ====================================================================
# MERGE TITLE FACTS
# ====================================================================

def _append_unique(target: List[Any], values: Any) -> None:
    if not isinstance(values, list):
        return

    for value in values:
        if value is None:
            continue

        value = str(value).strip()

        if value and value not in target:
            target.append(value)


def merge_title_facts(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = {
        "document_type": "",
        "land_owners": [],
        "developer": "",
        "seller": "",
        "purchaser": "",
        "project_name": "",
        "apartment_number": "",
        "building": "",
        "tower": "",
        "floor": "",
        "carpet_area": "",
        "super_built_up_area": "",
        "uds": "",
        "survey_numbers": [],
        "village": "",
        "hobli": "",
        "taluk": "",
        "district": "",
        "land_extent": "",
        "parent_documents": [],
        "jda_documents": [],
        "gpa_documents": [],
        "conversion_documents": [],
        "registration_documents": [],
        "sro": "",
        "deed_of_declaration": "",
        "occupancy_certificate": "",
        "title_statements": [],
        "authority_to_sell_statements": [],
        "adverse_title_statements": [],
        "other_title_facts": [],
    }

    scalar_fields = [
        "document_type",
        "developer",
        "seller",
        "purchaser",
        "project_name",
        "apartment_number",
        "building",
        "tower",
        "floor",
        "carpet_area",
        "super_built_up_area",
        "uds",
        "village",
        "hobli",
        "taluk",
        "district",
        "land_extent",
        "sro",
        "deed_of_declaration",
        "occupancy_certificate",
    ]

    list_fields = [
        "land_owners",
        "survey_numbers",
        "parent_documents",
        "jda_documents",
        "gpa_documents",
        "conversion_documents",
        "registration_documents",
        "title_statements",
        "authority_to_sell_statements",
        "adverse_title_statements",
        "other_title_facts",
    ]

    for fact in facts:

        if not isinstance(fact, dict):
            continue

        for field in scalar_fields:
            value = fact.get(field)

            if value and not result[field]:
                result[field] = str(value).strip()

        for field in list_fields:
            _append_unique(
                result[field],
                fact.get(field, []),
            )

    return result


# ====================================================================
# RERA DATA NORMALIZATION
# ====================================================================

def normalize_rera_data(
    rera_data: Optional[Union[Dict[str, Any], str]]
) -> Dict[str, Any]:
    """
    Accept a dict or a JSON file path.

    RERA is treated as supporting evidence. It does not automatically
    prove ownership.
    """
    if not rera_data:
        return {}

    if isinstance(rera_data, dict):
        return rera_data

    if isinstance(rera_data, str) and os.path.isfile(rera_data):
        with open(rera_data, "r", encoding="utf-8") as file:
            value = json.load(file)

        return value if isinstance(value, dict) else {}

    return {}


# ====================================================================
# DOCUMENT INVENTORY
# ====================================================================

def build_document_inventory(
    document_paths: List[str],
) -> List[Dict[str, Any]]:

    inventory = []

    for path in document_paths:

        if not path or not os.path.isfile(path):
            inventory.append(
                {
                    "path": path,
                    "status": "MISSING",
                    "document_type": "UNKNOWN",
                }
            )
            continue

        try:
            classification = classify_title_document(path)

            inventory.append(
                {
                    "path": path,
                    "status": "AVAILABLE",
                    **classification,
                }
            )

        except Exception as exc:
            inventory.append(
                {
                    "path": path,
                    "status": "EXTRACTION_FAILED",
                    "document_type": "UNKNOWN",
                    "error": str(exc),
                }
            )

    return inventory


# ====================================================================
# TITLE DOCUMENT RISK ASSESSMENT
# ====================================================================

def llm_title_risk_assessment(
    title_facts: Dict[str, Any],
    document_inventory: List[Dict[str, Any]],
    rera_data: Dict[str, Any],
    ec_transactions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:

    prompt = f"""
You are a Senior Karnataka Property Lawyer and apartment title
due-diligence specialist.

Assess BUYER-CENTRIC TITLE RISK for a residential apartment.

IMPORTANT DISTINCTION
---------------------
TITLE CHECK:
Checks ownership, title chain, parent documents, developer authority,
JDA/GPA, conversion and apartment-specific conveyance.

EC CHECK:
Checks registered transaction/encumbrance history.

RERA:
Provides project/promoter/title-related disclosures and uploaded
documents, but RERA information alone must NOT be treated as conclusive
proof of title.

Do not invent facts.

Do not call missing documents fraud.

A missing document means the title check is INCOMPLETE and should be
flagged for verification.

TITLE FACTS
-----------
{json.dumps(title_facts, indent=2, ensure_ascii=False)}

DOCUMENT INVENTORY
------------------
{json.dumps(document_inventory, indent=2, ensure_ascii=False)}

RERA DATA
---------
{json.dumps(rera_data, indent=2, ensure_ascii=False)[:18000]}

EC TRANSACTIONS
---------------
{json.dumps(ec_transactions or [], indent=2, ensure_ascii=False)}

CHECK THESE AREAS
-----------------
1. Land ownership
2. Parent title chain
3. Survey-number consistency
4. Land extent consistency
5. Conversion consistency
6. JDA existence and registration
7. GPA existence and registration
8. Developer authority to sell
9. Apartment-specific Sale Deed
10. UDS / Schedule B
11. Apartment / Schedule C
12. Seller-to-purchaser chain
13. RERA-to-title consistency
14. EC-to-title consistency
15. Explicit adverse title statements
16. Acquisition/dispute/restriction statements
17. Missing critical documents

RISK PRINCIPLES
---------------
HIGH:
- Contradictory ownership
- Broken title chain with evidence of competing title
- Seller lacks demonstrated authority
- Conflicting survey numbers for the same property
- Active adverse title claim explicitly shown
- Document inconsistency that materially affects ownership

MEDIUM:
- Critical parent document not provided
- JDA/GPA referenced but not verified
- Apartment-specific deed missing
- UDS/apartment details missing
- RERA and title data cannot be reconciled

LOW:
- Documents are available and consistent
- Ownership and authority chain is supported
- Apartment-specific conveyance is supported
- No material adverse title issue is visible

OUTPUT ONLY JSON:

{{
  "risk_score": 0,
  "risk_level": "LOW|MEDIUM|HIGH",
  "confidence": 0.0,
  "title_status": "COMPLETE|PARTIALLY_VERIFIED|INCOMPLETE|ADVERSE_INDICATOR",
  "critical_missing_documents": [],
  "major_risks": [],
  "positive_findings": [],
  "verification_checks": [],
  "reasoning": [],
  "recommendations": [],
  "summary": ""
}}

CONFIDENCE:
- High only when the critical documents are actually available.
- Do not give high confidence based only on RERA data or EC.

Return ONLY valid JSON.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=5000,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    raw = ""

    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text

    return parse_json_response(raw)


# ====================================================================
# EC TRANSACTION EXTRACTION
# ====================================================================

def extract_ec_transactions(
    ec_text: str,
) -> Dict[str, Any]:
    """
    Extract actual EC transaction rows.

    This remains separate from title-document extraction.
    """
    final_transactions = []

    page_pattern = re.compile(
        r"(?i)(?=Page\s+\d+\s+Of\s+\d+)"
    )

    chunks = [
        chunk.strip()
        for chunk in page_pattern.split(ec_text)
        if chunk.strip()
    ]

    if len(chunks) == 1 and len(ec_text) > 7000:
        chunks = [
            ec_text[i:i + 6000]
            for i in range(0, len(ec_text), 6000)
        ]

    for chunk_index, chunk in enumerate(chunks, start=1):

        prompt = f"""
You are a Karnataka Encumbrance Certificate transaction extractor.

Extract ACTUAL TRANSACTION ROWS only.

One transaction row = one object.

Return ONLY:

{{
  "transactions": [
    {{
      "date": "",
      "type": "",
      "seller": "",
      "buyer": "",
      "document_number": "",
      "amount": 0
    }}
  ]
}}

Allowed type values:
SALE
SALE_DEED
AGREEMENT_OF_SALE
MORTGAGE
DISCHARGE
RELEASE
LEASE
POWER_OF_ATTORNEY
GPA
GIFT
PARTITION
SETTLEMENT
RELINQUISHMENT
CANCELLATION
EXCHANGE
OTHER

Rules:
- Never use EC search-period dates as transaction dates.
- Property numbers, survey numbers and EC numbers are not transactions.
- Preserve all visible parties.
- Do not invent seller/buyer.
- Do not use Market Value when Consideration Amount exists.
- Extract every actual row.
- If there are no rows, return an empty list.

EC PAGE/CHUNK:
{chunk}
""".strip()

        try:
            response = qwen_client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract Karnataka EC transaction rows. "
                            "Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )

            result = parse_json_response(
                response.choices[0].message.content
            )

            transactions = result.get("transactions", [])

            if isinstance(transactions, list):
                final_transactions.extend(
                    item
                    for item in transactions
                    if isinstance(item, dict)
                )

        except Exception as exc:
            print(
                f"[WARNING] EC extraction page/chunk "
                f"{chunk_index}/{len(chunks)} failed: {exc}"
            )

    # Normalize and deduplicate.
    normalized = []
    seen = set()

    for transaction in final_transactions:

        cleaned = {
            "date": str(
                transaction.get("date") or ""
            ).strip(),

            "type": str(
                transaction.get("type") or "OTHER"
            ).strip().upper(),

            "seller": str(
                transaction.get("seller") or ""
            ).strip(),

            "buyer": str(
                transaction.get("buyer") or ""
            ).strip(),

            "document_number": str(
                transaction.get("document_number") or ""
            ).strip(),

            "amount": 0,
        }

        amount = transaction.get("amount", 0)

        try:
            if isinstance(amount, str):
                amount = (
                    amount.replace(",", "")
                    .replace("₹", "")
                    .replace("Rs.", "")
                    .replace("Rs", "")
                    .strip()
                )

            cleaned["amount"] = int(float(amount or 0))

        except (ValueError, TypeError):
            cleaned["amount"] = 0

        key = tuple(cleaned.values())

        if key not in seen:
            seen.add(key)
            normalized.append(cleaned)

    return {
        "transactions": normalized
    }


# ====================================================================
# EC RULE-BASED SUPPORT CHECKS
# ====================================================================

def ec_support_risk(
    transactions: List[Dict[str, Any]]
) -> Dict[str, Any]:

    score = 0
    flags = []

    if not transactions:
        return {
            "risk_score": 50,
            "flags": [
                "No EC transactions were extracted; EC review is incomplete."
            ],
        }

    for transaction in transactions:

        tx_type = transaction.get("type", "").upper()

        if tx_type in {"MORTGAGE"}:
            score += 20
            flags.append(
                f"Mortgage transaction found: "
                f"{transaction.get('document_number', '')}"
            )

        if tx_type in {"POWER_OF_ATTORNEY", "GPA"}:
            score += 5
            flags.append(
                f"POA/GPA transaction found: "
                f"{transaction.get('document_number', '')}"
            )

    return {
        "risk_score": min(score, 100),
        "flags": flags,
    }


# ====================================================================
# DOCUMENT COMPLETENESS
# ====================================================================

def assess_document_completeness(
    document_inventory: List[Dict[str, Any]]
) -> Dict[str, Any]:

    available_types = {
        item.get("document_type", "UNKNOWN")
        for item in document_inventory
        if item.get("status") == "AVAILABLE"
    }

    critical = []

    if "ACTUAL_SALE_DEED" not in available_types:
        critical.append("Actual registered Sale Deed of the apartment")

    if not (
        "PARENT_TITLE_DEED" in available_types
        or "MOTHER_DEED" in available_types
    ):
        critical.append("Parent/Mother title deed(s)")

    return {
        "available_document_types": sorted(available_types),
        "critical_missing_documents": critical,
        "complete": len(critical) == 0,
    }


# ====================================================================
# MAIN TITLE CHECK WRAPPER
# ====================================================================

def run_kaveri_ec_wrapper(
    pdf_path: Optional[str] = None,
    session_id: Optional[str] = None,
    screenshot_dir: Optional[str] = None,
    title_document_paths: Optional[List[str]] = None,
    rera_data: Optional[Union[Dict[str, Any], str]] = None,
    ec_pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main apartment title-check wrapper.

    BACKWARD COMPATIBILITY
    ----------------------
    pdf_path is treated as the EC PDF when ec_pdf_path is not supplied.

    NEW USAGE
    ---------
    title_document_paths = [
        actual_sale_deed.pdf,
        parent_sale_deed.pdf,
        jda.pdf,
        gpa.pdf,
        conversion.pdf,
    ]

    rera_data can be:
        - a dictionary
        - a JSON file path

    ec_pdf_path is optional and is used only for the EC support check.
    """

    # ---------------------------------------------------------------
    # Backward compatibility with the old wrapper.
    # ---------------------------------------------------------------

    if ec_pdf_path is None and pdf_path:
        ec_pdf_path = pdf_path

    if title_document_paths is None:
        title_document_paths = []

    # ---------------------------------------------------------------
    # Build title-document inventory.
    # ---------------------------------------------------------------

    document_inventory = build_document_inventory(
        title_document_paths
    )

    # ---------------------------------------------------------------
    # Extract facts from every available title document.
    # ---------------------------------------------------------------

    title_documents = []

    for item in document_inventory:

        if item.get("status") != "AVAILABLE":
            continue

        path = item.get("path")
        document_type = item.get(
            "document_type",
            "UNKNOWN"
        )

        try:
            facts = extract_title_facts(
                path,
                document_type=document_type,
            )

            title_documents.append(
                {
                    "file": os.path.basename(path),
                    "document_type": document_type,
                    "facts": facts,
                }
            )

        except Exception as exc:
            print(
                f"[WARNING] Failed title extraction for "
                f"{path}: {exc}"
            )

    # ---------------------------------------------------------------
    # Merge all title facts.
    # ---------------------------------------------------------------

    merged_facts = merge_title_facts(
        [
            item["facts"]
            for item in title_documents
            if isinstance(item.get("facts"), dict)
        ]
    )

    # ---------------------------------------------------------------
    # RERA data.
    # ---------------------------------------------------------------

    normalized_rera = normalize_rera_data(rera_data)

    # ---------------------------------------------------------------
    # EC support check.
    # ---------------------------------------------------------------

    ec_transactions = []
    ec_result = {
        "status": "NOT_PROVIDED",
        "transactions": [],
        "support_risk": {
            "risk_score": 0,
            "flags": [
                "EC not provided for this title-check run."
            ],
        },
    }

    if ec_pdf_path and os.path.isfile(ec_pdf_path):

        try:
            ec_text = extract_pdf_text(ec_pdf_path)

            extracted_ec = extract_ec_transactions(
                ec_text
            )

            ec_transactions = extracted_ec.get(
                "transactions",
                []
            )

            ec_result = {
                "status": "EXTRACTED",
                "transactions": ec_transactions,
                "support_risk": ec_support_risk(
                    ec_transactions
                ),
            }

            if session_id and screenshot_dir:

                screenshot_path = os.path.join(
                    screenshot_dir,
                    f"kaveri_ec_evidence_{session_id}.png",
                )

                create_evidence_screenshot(
                    ec_pdf_path,
                    screenshot_path,
                    keywords=[
                        "sale",
                        "mortgage",
                        "release",
                        "discharge",
                        "gpa",
                        "power of attorney",
                        "registration",
                        "document no",
                    ],
                )

                ec_result["evidence_screenshot"] = (
                    screenshot_path
                )

        except Exception as exc:
            ec_result = {
                "status": "FAILED",
                "transactions": [],
                "error": str(exc),
            }

    # ---------------------------------------------------------------
    # Document completeness.
    # ---------------------------------------------------------------

    completeness = assess_document_completeness(
        document_inventory
    )

    # ---------------------------------------------------------------
    # Legal/title LLM assessment.
    # ---------------------------------------------------------------

    try:
        legal_assessment = llm_title_risk_assessment(
            title_facts=merged_facts,
            document_inventory=document_inventory,
            rera_data=normalized_rera,
            ec_transactions=ec_transactions,
        )

    except Exception as exc:
        legal_assessment = {
            "risk_score": None,
            "risk_level": "UNKNOWN",
            "confidence": 0.0,
            "title_status": "INCOMPLETE",
            "critical_missing_documents": (
                completeness["critical_missing_documents"]
            ),
            "major_risks": [
                f"LLM title assessment failed: {exc}"
            ],
            "positive_findings": [],
            "verification_checks": [],
            "reasoning": [],
            "recommendations": [],
            "summary": (
                "Title assessment could not be completed."
            ),
        }

    # ---------------------------------------------------------------
    # Conservative final score.
    #
    # Missing critical documents are NOT automatically treated as
    # fraud. They reduce confidence and keep the status incomplete.
    # ---------------------------------------------------------------

    risk_score = legal_assessment.get("risk_score")

    if isinstance(risk_score, (int, float)):
        risk_score = round(
            max(0, min(100, float(risk_score))),
            2,
        )

    title_status = legal_assessment.get(
        "title_status",
        "INCOMPLETE",
    )

    # If critical documents are missing, never report COMPLETE.
    if not completeness["complete"]:
        if title_status == "COMPLETE":
            title_status = "PARTIALLY_VERIFIED"

    final_result = {
        "status": "SUCCESS",
        "scope": "RESIDENTIAL_APARTMENT_TITLE_CHECK",
        "title_status": title_status,
        "risk_score": risk_score,
        "risk_level": legal_assessment.get(
            "risk_level",
            "UNKNOWN",
        ),
        "confidence": legal_assessment.get(
            "confidence",
            0.0,
        ),
        "document_inventory": document_inventory,
        "document_completeness": completeness,
        "title_documents": title_documents,
        "merged_title_facts": merged_facts,
        "rera": {
            "provided": bool(normalized_rera),
            "data": normalized_rera,
        },
        "ec_support": ec_result,
        "title_assessment": legal_assessment,
    }

    # ---------------------------------------------------------------
    # Print concise result.
    # ---------------------------------------------------------------

    print("\n" + "=" * 90)
    print("🏠 APARTMENT TITLE CHECK")
    print("=" * 90)
    print(
        json.dumps(
            final_result,
            indent=2,
            ensure_ascii=False,
        )
    )
    print("=" * 90)

    return final_result


# ====================================================================
# EXAMPLE
# ====================================================================

if __name__ == "__main__":

    # ---------------------------------------------------------------
    # APARTMENT TITLE DOCUMENTS
    # Replace these with the actual documents for the apartment.
    # ---------------------------------------------------------------

    TITLE_DOCUMENTS = [
        # r"D:\aasthiv2\Aasthi\input\sale_deed.pdf",
        # r"D:\aasthiv2\Aasthi\input\parent_sale_deed.pdf",
        # r"D:\aasthiv2\Aasthi\input\jda.pdf",
        # r"D:\aasthiv2\Aasthi\input\gpa.pdf",
        # r"D:\aasthiv2\Aasthi\input\conversion_order.pdf",
    ]

    # Optional RERA JSON exported by your RERA wrapper.
    RERA_DATA = None
    # Example:
    # RERA_DATA = r"D:\aasthiv2\Aasthi\output\rera_result.json"

    # Optional EC PDF.
    EC_PDF = None
    # Example:
    # EC_PDF = r"D:\aasthiv2\Aasthi\input\kaveriec\download.pdf"

    result = run_kaveri_ec_wrapper(
        title_document_paths=TITLE_DOCUMENTS,
        rera_data=RERA_DATA,
        ec_pdf_path=EC_PDF,
        session_id="123456",
        screenshot_dir="screenshots",
    )
