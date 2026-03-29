# bescom_wrapper.py
import os
import re
import json
import pdfplumber
from PIL import Image
from difflib import SequenceMatcher

import google.generativeai as old_genai # keep for now if needed elsewhere
from google import genai
from google.genai import types


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


# ==================================================
# GEMINI CONFIG
# ==================================================
BESCOM_MODEL = "models/gemini-2.0-flash-lite"

def get_genai_client():
    key = (
        os.environ.get("GEMINI_BESCOM", "").strip() or 
        os.environ.get("GEMINI_EXTRACTION_KEY", "").strip() or 
        os.environ.get("GEMINI_API_KEY", "").strip()
    )
    if not key:
        raise RuntimeError("No Gemini API key found (GEMINI_BESCOM, GEMINI_EXTRACTION_KEY, or GEMINI_API_KEY).")
    return genai.Client(api_key=key)


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
def gemini_extract_from_text(pdf_text: str, debug=False) -> dict:
    client = get_genai_client()

    prompt = f"""
Extract customer details from a BESCOM electricity bill.

Return ONLY valid JSON:
{{
  "name": "...",
  "address": "..."
}}

Rules:
- Name is the customer name (usually CAPS).
- Address is the postal address (may include PIN).
- Do NOT output tariff/type/meter fields as name.
- If missing, use empty strings.

PDF text:
---
{pdf_text[:20000]}
---
"""

    resp = client.models.generate_content(
        model=BESCOM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        )
    )

    raw = (resp.text or "").strip()
    if debug:
        print("\n[DEBUG] Gemini raw output (TEXT MODE):\n", raw)

    data = parse_json_strict(raw)
    return {
        "name": str(data.get("name", "")).strip(),
        "address": str(data.get("address", "")).strip(),
    }


# ==================================================
# GEMINI: IMAGE MODE (for scanned PDFs)
# ==================================================
def gemini_extract_from_images(images, debug=False) -> dict:
    client = get_genai_client()

    prompt = """
You are reading images of a BESCOM electricity bill.

Extract the CUSTOMER NAME and FULL POSTAL ADDRESS.
Return ONLY valid JSON:
{
  "name": "...",
  "address": "..."
}

Rules:
- Name is the customer name (usually CAPS).
- Address is the postal address (may include PIN).
- Do NOT output tariff/type/meter fields as name.
- If missing, use empty strings.
"""

    if debug:
        print(f"DEBUG: Calling Gemini API for BESCOM extraction (IMAGE MODE)...")
    
    resp = client.models.generate_content(
        model=BESCOM_MODEL,
        contents=[prompt, images[0]],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        )
    )
    if debug:
        print(f"DEBUG: Gemini API response received for BESCOM (IMAGE MODE).")

    raw = (resp.text or "").strip()
    if debug:
        print("\n[DEBUG] Gemini raw output (IMAGE MODE):\n", raw)

    data = parse_json_strict(raw)
    return {
        "name": str(data.get("name", "")).strip(),
        "address": str(data.get("address", "")).strip(),
    }


# ==================================================
# AUTO MODE: choose best approach
# ==================================================
def gemini_extract_name_address(pdf_path: str, debug=False) -> dict:
    pdf_text = extract_text(pdf_path)

    # If text is too small, likely scanned -> image mode
    if debug:
        print(f"[DEBUG] Extracted text length: {len(pdf_text)}")

    if len(pdf_text) >= 300:
        out = gemini_extract_from_text(pdf_text, debug=debug)
        # If Gemini failed in text mode, fallback to image mode
        if (not out["name"] and not out["address"]) and debug:
            print("[DEBUG] Text mode returned empty. Falling back to image mode...")
        if out["name"] or out["address"]:
            return out

    images = pdf_to_images(pdf_path, max_pages=2, dpi=220)
    return gemini_extract_from_images(images, debug=debug)


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
        import os
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"bescom_result_{session_id}.png")
        print(f"DEBUG: BESCOM wrapper - attempting to capture screenshot to {screenshot_path}")
        # Reuse existing pdf_to_images to save the first page
        try:
            print(f"DEBUG: BESCOM wrapper - calling pdf_to_images for screenshot...")
            images = pdf_to_images(pdf_path, max_pages=1, dpi=220)
            if images:
                print(f"DEBUG: BESCOM wrapper - saving first page as screenshot...")
                images[0].save(screenshot_path)
                print(f"DEBUG: Saved BESCOM screenshot to {screenshot_path}")
        except Exception as e:
            print(f"DEBUG: BESCOM wrapper - failed to capture screenshot: {e}")

    system_data = gemini_extract_name_address(pdf_path, debug=debug)

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
    PDF_PATH = r"D:\aasthi\wrappercode\7220755000\7220755000.pdf"

    # keeping it non-interactive-friendly: edit these two lines if needed
    USER_NAME = "ENTER_NAME_HERE"
    USER_ADDRESS = "ENTER_ADDRESS_HERE"

    result = run_bescom_wrapper(PDF_PATH, USER_NAME, USER_ADDRESS, debug=True)
    print(json.dumps(result, indent=2))
