# bescom_wrapper.py
import os
import re
import json
import pdfplumber
from PIL import Image
from difflib import SequenceMatcher

from anthropic import Anthropic
import pytesseract


# ==================================================
# CLEAN + SIMILARITY
# ==================================================
def clean_text(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def similarity(a, b):
    return SequenceMatcher(None, clean_text(a), clean_text(b)).ratio()


# ==================================================
# PDF TEXT EXTRACTION
# ==================================================
def extract_text(pdf_path):
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text(layout=True)
            if t:
                chunks.append(t)
    return "\n".join(chunks).strip()


# ==================================================
# PDF -> IMAGES (for scanned PDFs)
# ==================================================
def pdf_to_images(pdf_path, max_pages=2, dpi=200):
    images = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            pil_img = page.to_image(resolution=dpi).original
            # Ensure RGB
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            images.append(pil_img)
    return images

def create_bescom_evidence_screenshot(
    pdf_path,
    output_path,
    dpi=220
):
    """
    Save the page containing customer details.
    """

    images = pdf_to_images(
        pdf_path,
        max_pages=2,
        dpi=dpi
    )

    if not images:
        return

    keywords = [
        "consumer",
        "name",
        "address",
        "rr no",
        "rr number",
        "account",
        "bill amount"
    ]

    best_img = images[0]
    best_score = -1

    for img in images:

        text = pytesseract.image_to_string(img).lower()

        score = sum(
            1
            for k in keywords
            if k in text
        )

        if score > best_score:
            best_score = score
            best_img = img

    best_img.save(output_path)
# ==================================================
# GEMINI CONFIG
# ==================================================
BESCOM_MODEL = "qwen3:8b"

from openai import OpenAI

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def parse_json_strict(raw: str) -> dict:
    raw = (raw or "").strip()

    # Strip ```json fences if present
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"^```\s*", "", raw).strip()
    raw = re.sub(r"\s*```$", "", raw).strip()

    # Try full JSON
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass

    # Try to find first { ... } block
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


# ==================================================
# GEMINI: TEXT MODE
# ==================================================
def claude_extract_from_text(pdf_text: str, debug=False) -> dict:
    client = qwen_client

    prompt = f"""
# ROLE

You are a Senior BESCOM Electricity Bill Verification Officer and Karnataka Utility Document Extraction Specialist.

# CONTEXT

You are analyzing an official BESCOM electricity bill.

Your task is to extract ONLY the registered consumer's name and service address.

The extracted information will be compared against buyer-provided details for identity verification.

# OBJECTIVE

Extract the following fields accurately:

1. Customer Name
2. Service Address

# EXTRACTION PROCESS

Step 1

Read the entire BESCOM bill.

Step 2

Locate the registered consumer information.

Possible labels include:

• Consumer Name
• Name
• Registered Consumer
• Consumer Details
• Consumer Information

Step 3

Locate the Service Address.

Possible labels include:

• Address
• Service Address
• Consumer Address
• Installation Address
• Premises Address

Step 4

Ignore every other section.

Do NOT extract:

• RR Number
• Account ID
• Customer ID
• Tariff
• Sanction Load
• Meter Number
• Bill Amount
• Due Date
• Reading Details
• GST Details
• Payment Details
• Feeder Information

Step 5

Normalize the extracted values.

• Remove unnecessary spaces.
• Preserve original spelling.
• Preserve capitalization if present.
• Keep commas and house numbers.
• Do not abbreviate or rewrite addresses.

# IMPORTANT RULES

• Use ONLY information explicitly present in the bill.

• Never guess missing values.

• Never infer from nearby text.

• If the name is not visible,
return an empty string.

• If the address is not visible,
return an empty string.

• Ignore OCR noise.

• Ignore decorative text.

• Ignore repeated footer/header text.

# OUTPUT

Return ONLY valid JSON.

{{
    "name": "",
    "address": ""
}}

# FINAL VALIDATION

Before returning:

✓ Name must be the registered consumer.

✓ Address must be the complete service address.

✓ No RR Number.

✓ No Meter Number.

✓ No Tariff.

✓ No Bill Amount.

✓ No extra keys.

✓ Return ONLY valid JSON.

BESCOM BILL TEXT

-------------------------

{pdf_text[:20000]}

-------------------------
""".strip()
    client = qwen_client

    response = client.chat.completions.create(
        model=BESCOM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are an information extraction engine. Return ONLY valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    if debug:
        print("\n[DEBUG] Qwen raw output:\n", raw)

    data = parse_json_strict(raw)

    return {
        "name": str(data.get("name", "")).strip(),
        "address": str(data.get("address", "")).strip(),
}

# ==================================================
# GEMINI: IMAGE MODE (for scanned PDFs)
# ==================================================
def claude_extract_from_text(pdf_text: str, debug=False) -> dict:

    client = qwen_client

    prompt = f"""
Extract customer details from a BESCOM electricity bill.

Return ONLY valid JSON:

{{
  "name": "...",
  "address": "..."
}}

Rules:
- Name is the customer name.
- Address is the postal address.
- Do not output tariff/meter details as name.
- If missing, use empty strings.

PDF text:
---
{pdf_text[:20000]}
---
"""

    response = client.chat.completions.create(
        model=BESCOM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are an information extraction engine. Return ONLY valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    if debug:
        print("\n[DEBUG] Qwen raw output:\n", raw)

    data = parse_json_strict(raw)

    return {
        "name": str(data.get("name", "")).strip(),
        "address": str(data.get("address", "")).strip(),
    }

# ==================================================
# AUTO MODE: choose best approach
# ==================================================
def claude_extract_name_address(
    pdf_path: str,
    debug=False
) -> dict:

    pdf_text = extract_text(pdf_path)

    if debug:
        print(
            f"[DEBUG] Extracted text length: {len(pdf_text)}"
        )

    if not pdf_text:
        return {
            "name": "",
            "address": ""
        }

    return claude_extract_from_text(
        pdf_text,
        debug=debug
    )

# ==================================================
# SCORING
# ==================================================
def calculate_risk(system, user):
    name_score = similarity(system["name"], user["name"]) * 50
    addr_score = similarity(system["address"], user["address"]) * 50
    match_score = round(name_score + addr_score, 2)
    risk_score = round(100 - match_score, 2)
    return match_score, risk_score

# ==================================================
# WRAPPER (NEW)
# ==================================================
def run_bescom_wrapper(
    pdf_path: str,
    user_name: str,
    user_address: str,
    debug: bool = False,
    session_id: str = None,
    screenshot_dir: str = None
) -> dict:
    """
    Wrapper for BESCOM bill extraction + match/risk scoring.

    Returns:
    {
      "document_type": "BESCOM",
      "pdf_path": "...",
      "system_data": {"name": "...", "address": "..."},
      "user_data": {"name": "...", "address": "..."},
      "match_score": 0.0,
      "risk_score": 0.0
    }
    """
    # 1) Setup screenshot if needed
    if screenshot_dir and session_id:
        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        screenshot_path = os.path.join(
            screenshot_dir,
            f"bescom_result_{session_id}.png"
        )

        try:

            create_bescom_evidence_screenshot(
                pdf_path,
                screenshot_path
            )

            print(
                f"Saved BESCOM evidence screenshot → {screenshot_path}"
            )

        except Exception as e:

            print(
                f"Failed to save BESCOM screenshot: {e}"
            )
        

    system_data = claude_extract_name_address(pdf_path, debug=debug)

    user_data = {
        "name": (user_name or "").strip(),
        "address": (user_address or "").strip()
    }

    match, risk = calculate_risk(system_data, user_data)

    return {
        "document_type": "BESCOM",
        "pdf_path": pdf_path,
        "system_data": system_data,
        "user_data": user_data,
        "match_score": match,
        "risk_score": risk,
    }


# Optional: keep a simple CLI entry without changing logic
if __name__ == "__main__":
    PDF_PATH = r"D:\aasthiv2\Aasthi\wrappercode\input\bescom\7220755000.pdf"

    # keeping it non-interactive-friendly: edit these two lines if needed
    USER_NAME = "G KRISHNA REDDY"
    USER_ADDRESS = "KAGADASPURAKAGADASPURA-, KAR -56001"

    result = run_bescom_wrapper(PDF_PATH, USER_NAME, USER_ADDRESS, debug=True)
    print(json.dumps(result, indent=2))
