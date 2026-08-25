# ============================================================
# BBMP KHATA RISK ANALYZER
# Uses Gemini to read PDF directly
# Returns Khata Type + Risk Score
#
# pip install google-genai python-dotenv
# ============================================================

import os
import json
from anthropic import Anthropic
import base64
import fitz  # PyMuPDF
from PIL import Image
import re
from dotenv import load_dotenv

# ============================================================
# CONFIG
# ============================================================
from openai import OpenAI

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

EXTRACTION_MODEL = "qwen2.5vl:7b"
MODEL = "claude-opus-4-7"

#api_key = os.getenv("ANTHROPIC_API_KEY")

#if not api_key:
#       raise RuntimeError("Missing ANTHROPIC_API_KEY")

#client = Anthropic(api_key=api_key)
# ============================================================
# JSON PARSER
# ============================================================
import fitz

def extract_pdf_text(pdf_path):
    text = ""

    doc = fitz.open(pdf_path)

    for page in doc:
        text += page.get_text()

    doc.close()

    return text

def parse_json(text):

    text = text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    try:
        return json.loads(text)

    except Exception:

        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end >= 0:
            return json.loads(text[start:end+1])

        raise Exception("Unable to parse Gemini JSON")

def create_khata_evidence_screenshot(
        pdf_path,
        output_path,
        khata_data
):
    """
    Saves the page containing the important Khata information.
    """

    keywords = []

    for key in [
        "owner_name",
        "pid_number",
        "application_number",
        "survey_number",
        "property_address"
    ]:
        value = str(khata_data.get(key, "")).strip()
        if value:
            keywords.append(value.lower())

    doc = fitz.open(pdf_path)

    best_page = 0
    best_score = -1

    for page_no in range(len(doc)):

        page = doc.load_page(page_no)

        text = page.get_text().lower()

        score = 0

        for kw in keywords:
            if kw and kw in text:
                score += 1

        # Bonus for common Khata headings
        for kw in [
            "owner",
            "pid",
            "application",
            "khata",
            "address"
        ]:
            if kw in text:
                score += 1

        if score > best_score:
            best_score = score
            best_page = page_no

    page = doc.load_page(best_page)

    pix = page.get_pixmap(dpi=220)

    pix.save(output_path)

    print(f"Saved evidence screenshot: {output_path}")

    doc.close()
# ============================================================
# EXTRACT KHATA DETAILS
# ============================================================

def extract_khata_data(pdf_path):

    doc = fitz.open(pdf_path)

    # ========================================================
    # EXTRACTION PROMPT
    # ========================================================

    prompt = """
# ROLE

You are a Senior BBMP Khata Verification Officer,
Karnataka Municipal Records Specialist,
and Property Due Diligence Expert.

# TASK

Extract property information from the supplied BBMP Khata/eKhata
document page.

The supplied page is one page from ONE document.

Extract ONLY information that is visibly present.

Do NOT guess or infer missing information.

# LANGUAGE UNDERSTANDING

The document may contain:

- English
- Kannada
- English and Kannada together

You MUST understand both English and Kannada.

The field labels may themselves be written in Kannada.

Use the meaning of Kannada labels to correctly identify the
corresponding fields.

For Kannada text:

- Read Kannada text accurately.
- Do not ignore Kannada fields.
- Preserve Kannada text when the extracted value is written
  in Kannada.
- Do not invent an English translation.
- Do not invent an English transliteration.
- If the same value is visible in both Kannada and English,
  use the clearest explicitly visible value.
- Preserve names and addresses exactly as visible.

# IMPORTANT

This is a partial page from a larger document.

Therefore:

- Extract whatever information is visible on this page.
- Missing fields are acceptable.
- Do NOT invent values.
- Do NOT assume a field is absent from the complete document
  just because it is absent from this page.

# FIELDS

Extract:

- document_type
- document_status
- khata_type
- owner_name
- pid_number
- application_number
- survey_number
- ward_number
- property_address
- area_sqft

# DOCUMENT TYPE

Identify the document type only from visible text or the document heading.

For this document, if the visible heading/content clearly identifies it
as a BBMP eKhata / BBMP Khata document, return:

"BBMP e-Khata"

Do not leave document_type empty when the document type is explicitly
identifiable from the page.


# KHATA TYPE

Only extract the actual Khata Type if explicitly visible.

Possible values:

A
B
E-KHATA
UNKNOWN

Do NOT assume E-KHATA merely because the document is called
eKhata.

# DOCUMENT STATUS

Only extract if explicitly visible.

Possible values:

FINAL
DRAFT
UNKNOWN
# IDENTIFIERS

Do not confuse:

PID Number
Application Number
Khata Number
Survey Number

Preserve the exact value visible in the corresponding field.

IMPORTANT:

If the corresponding field explicitly contains:

NA
N/A
Not Available
-

then preserve that value exactly.

Do NOT convert an explicitly displayed "NA" into an empty string.

Only return an empty string when the field/value is genuinely not visible.

# OUTPUT

Return ONLY valid JSON.

{
    "document_type": "",
    "document_status": "",
    "khata_type": "",
    "owner_name": "",
    "pid_number": "",
    "application_number": "",
    "survey_number": "",
    "ward_number": "",
    "property_address": "",
    "area_sqft": ""
}

# RULES

✓ Only visible information.
✓ Understand English and Kannada.
✓ No guessing.
✓ No inference.
✓ Preserve names exactly.
✓ Preserve Kannada text exactly when visible.
✓ Preserve identifiers exactly.
✓ Preserve addresses exactly as visible.
✓ Return empty string when a field is not visible.
✓ Return ONLY valid JSON.
"""

    # ========================================================
    # DEFAULT EMPTY RESULT
    # ========================================================

    final_data = {
        "document_type": "",
        "document_status": "",
        "khata_type": "",
        "owner_name": "",
        "pid_number": "",
        "application_number": "",
        "survey_number": "",
        "ward_number": "",
        "property_address": "",
        "area_sqft": ""
    }

    # ========================================================
    # PROCESS ALL PAGES INTERNALLY
    # ========================================================

    for page_number in range(len(doc)):

        page = doc.load_page(page_number)

        pix = page.get_pixmap(
            dpi=120,
            alpha=False
        )

        image_bytes = pix.tobytes("jpeg")

        image_b64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        response = qwen_client.chat.completions.create(

            model=EXTRACTION_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict visual information "
                        "extraction engine. "
                        "You understand English and Kannada. "
                        "Return ONLY valid JSON."
                    )
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
                                f"data:image/jpeg;base64,"
                                f"{image_b64}"
                            }
                        }
                    ]
                }
            ],

            temperature=0
        )

        text = response.choices[0].message.content

        page_data = parse_json(text)

        # ====================================================
        # MERGE PAGE DATA INTO FINAL RESULT
        # ====================================================

        for key in final_data:

            value = page_data.get(key, "")

            if value is None:
                continue

            value = str(value).strip()

            if value and not final_data[key]:
                final_data[key] = value

    doc.close()

    # ========================================================
    # ONLY FINAL OUTPUT
    # ========================================================

    print("\n" + "=" * 90)
    print("📦 FINAL QWEN eKHATA EXTRACTION")
    print("=" * 90)

    print(
        json.dumps(
            final_data,
            indent=2,
            ensure_ascii=False
        )
    )

    print("=" * 90)

    return final_data

'''
def llm_khata_risk_score(khata_data):
    prompt = f"""
# ROLE

You are a Senior Karnataka Property Due Diligence Consultant,
Municipal Records Auditor,
and Real Estate Legal Risk Specialist.

# CONTEXT

A prospective property buyer wants to evaluate whether this
BBMP Khata document represents a legally safe property.

Assess ONLY the supplied Khata information.

Do NOT invent facts.

# OBJECTIVE

Estimate Buyer Risk.

Risk Scale

0 = No Risk

100 = Extremely High Risk

# EVALUATION FRAMEWORK

Evaluate:

1. Khata Type

• A Khata

• B Khata

• E-Khata

• Unknown

2. Document Status

• Final

• Draft

• Unknown

3. Owner Information

4. PID Number

5. Application Number

6. Survey Number

7. Property Address

8. Internal Document Consistency

# DECISION GUIDELINES

Lowest Risk

• A Khata

• E-Khata

• Final document

• Complete identifiers

Moderate Risk

• Missing identifiers

• Unknown status

Highest Risk

• B Khata

• Draft document

• Unknown Khata type

• Multiple missing identifiers

# IMPORTANT RULES

Never invent information.

Missing information reduces confidence,
not automatically the risk.

Use ONLY supplied data.

Reasons must reference supplied fields.

Recommendations must be practical.

# KHATA DATA

{json.dumps(khata_data, indent=2)}

# OUTPUT

Return ONLY valid JSON.

{{
    "risk_score":0,

    "risk_level":"LOW|MEDIUM|HIGH",

    "confidence":0.0,

    "major_risks":[
        "...",
        "..."
    ],

    "reasoning":[
        "...",
        "..."
    ],

    "summary":""
}}

# FINAL VALIDATION

Before returning:

✓ Risk score between 0 and 100.

✓ Risk level matches score.

✓ Confidence matches completeness.

✓ Reasons supported by supplied data.

✓ Return ONLY valid JSON.
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    text = ""

    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    return parse_json(text)
'''

# ============================================================
# RISK ENGINE
# ============================================================

def calculate_khata_risk(data):
    score = 0
    reasons = []

    # --------------------------------------------------------
    # NORMALIZE INPUTS
    # --------------------------------------------------------
    khata_type = (
        str(data.get("khata_type", ""))
        .upper()
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )
    khata_type = " ".join(khata_type.split())

    status = (
        str(data.get("document_status", ""))
        .upper()
        .strip()
    )

    pid = str(data.get("pid_number", "")).strip()
    owner = str(data.get("owner_name", "")).strip()
    application = str(data.get("application_number", "")).strip()
    survey = str(data.get("survey_number", "")).strip()
    address = str(data.get("property_address", "")).strip()

    # --------------------------------------------------------
    # KHATA TYPE
    # --------------------------------------------------------
    if khata_type in ("A", "A KHATA"):
        score += 5
        reasons.append("A Khata detected")

    elif khata_type in ("E", "E KHATA", "EKHATA"):
        score += 5
        reasons.append("E-Khata detected")

    elif khata_type in ("B", "B KHATA"):
        score += 60
        reasons.append("B Khata detected")

    else:
        score += 70
        reasons.append("Khata type could not be verified")

    # --------------------------------------------------------
    # DOCUMENT STATUS
    # --------------------------------------------------------
    if status == "DRAFT":
        score += 10
        reasons.append("Draft Khata document")

    elif status == "UNKNOWN":
        score += 5
        reasons.append("Document status could not be verified")

    # --------------------------------------------------------
    # PID
    # --------------------------------------------------------
    if not pid:
        score += 10
        reasons.append("PID number missing")

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------
    if not owner:
        score += 5
        reasons.append("Owner name missing")

    # --------------------------------------------------------
    # APPLICATION NUMBER
    # --------------------------------------------------------
    if not application:
        score += 5
        reasons.append("Application number missing")

    # --------------------------------------------------------
    # SURVEY NUMBER
    # --------------------------------------------------------
    if not survey:
        score += 5
        reasons.append("Survey number missing")

    # --------------------------------------------------------
    # PROPERTY ADDRESS
    # --------------------------------------------------------
    if not address:
        score += 5
        reasons.append("Property address missing")

    # --------------------------------------------------------
    # CAP SCORE
    # --------------------------------------------------------
    score = min(score, 100)

    # --------------------------------------------------------
    # RISK LEVEL
    # --------------------------------------------------------
    if score <= 25:
        level = "LOW"
    elif score <= 50:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "risk_score": score,
        "risk_level": level,
        "reasons": reasons
    }

# ============================================================
# FINAL REPORT
# ============================================================

def generate_report(
    pdf_path,
    session_id=None,
    screenshot_dir=None
):
    """
    Generates Khata report.

    Also saves an evidence screenshot:
        khata_result_<session_id>.png
    """

    # ------------------------------------
    # Extract document details (Claude)
    # ------------------------------------
    khata_data = extract_khata_data(pdf_path)
    print("\n" + "=" * 90)
    print("🔍 QWEN eKHATA EXTRACTION RESULT")
    print("=" * 90)

    print(
        json.dumps(
            khata_data,
            indent=2,
            ensure_ascii=False
        )
    )

    print("=" * 90)
    # ------------------------------------
    # Save evidence screenshot
    # ------------------------------------
    if session_id and screenshot_dir:

        os.makedirs(screenshot_dir, exist_ok=True)

        screenshot_path = os.path.join(
            screenshot_dir,
            f"khata_result_{session_id}.png"
        )

        try:
            create_khata_evidence_screenshot(
                pdf_path=pdf_path,
                output_path=screenshot_path,
                khata_data=khata_data
            )

            print(f"DEBUG: Saved KHATA screenshot to {screenshot_path}")

        except Exception as e:
            print(f"DEBUG: Failed to save KHATA screenshot: {e}")

    return {
        "document_type": "KHATA",
        "status": "QWEN_EXTRACTION_SUCCESS",
        "pdf_path": pdf_path,
        "facts": khata_data
    }
    # ------------------------------------
    # Rule-based Risk
    # ------------------------------------
    #rule_risk = calculate_khata_risk(khata_data)

    # ------------------------------------
    # Claude Risk
    # ------------------------------------
'''
    try:
        llm_risk = llm_khata_risk_score(khata_data)

        final_score = round(
            0.7 * rule_risk["risk_score"] +
            0.3 * llm_risk["risk_score"],
            2
        )

    except Exception as e:

        llm_risk = {
            "error": str(e)
        }

        # Fallback to Python rule-based score
        final_score = rule_risk["risk_score"]

    if final_score <= 25:
        final_level = "LOW"

    elif final_score <= 50:
        final_level = "MEDIUM"

    else:
        final_level = "HIGH"

    # ------------------------------------
    # Return Report
    # ------------------------------------
    return {
        "document_details": khata_data,

        "rule_based_risk": rule_risk,

        "llm_risk": llm_risk,

        "final_assessment": {
            "risk_score": final_score,
            "risk_level": final_level
        }
    }
'''
   
# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    PDF_PATH = r"D:\aasthiv2\Aasthi\wrappercode\input\ekhata\87a0b46b-9cb5-40b7-89f9-f06827dd2e2e.pdf"

    report = generate_report(PDF_PATH)

    print(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        )
    )