# waterbill_wrapper.py
import re
from difflib import SequenceMatcher
from waterbill import WaterBillFetcher


# =============================
# TEXT NORMALIZATION
# =============================
def clean_text(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]', ' ', s)   # remove punctuation
    s = re.sub(r'\s+', ' ', s)         # remove extra spaces
    return s.strip()


# =============================
# SIMILARITY
# =============================
def similarity(a, b):
    return SequenceMatcher(
        None,
        clean_text(a),
        clean_text(b)
    ).ratio()


# =============================
# WEIGHTS
# =============================
WEIGHTS = {
    "Consumer Name": 50,
    "Consumer Address": 50
}


# =============================
# RISK ENGINE
# =============================
def calculate_risk(system_data, user_data):

    score = 0

    # ----- NAME -----
    score += (
        similarity(
            system_data.get("Consumer Name", ""),
            user_data.get("Consumer Name", "")
        ) * WEIGHTS["Consumer Name"]
    )

    # ----- ADDRESS -----
    score += (
        similarity(
            system_data.get("Consumer Address", ""),
            user_data.get("Consumer Address", "")
        ) * WEIGHTS["Consumer Address"]
    )

    match_score = round(score, 2)
    risk_score = round(100 - match_score, 2)

    return match_score, risk_score


# =============================
# WRAPPER (NEW)
# =============================
def run_waterbill_wrapper(
    rr_number: str,
    user_name: str,
    user_address: str,
    session_id: str = None,
    screenshot_dir: str = None
) -> dict:
    """
    Wrapper for Water Bill fetch + match/risk scoring.

    Returns:
    {
      "document_type": "WATER_BILL",
      "rr_number": "...",
      "system_data": {...},
      "user_data": {...},
      "match_score": 0.0,
      "risk_score": 0.0
    }
    """

    # Fetch system data
    fetcher = WaterBillFetcher(session_id=session_id, screenshot_dir=screenshot_dir)
    system_data = fetcher.fetch_by_rr((rr_number or "").strip())
    fetcher.close()

    user_data = {
        "Consumer Name": (user_name or "").strip(),
        "Consumer Address": (user_address or "").strip()
    }

    match, risk = calculate_risk(system_data, user_data)

    return {
        "document_type": "WATER_BILL",
        "rr_number": (rr_number or "").strip(),
        "system_data": system_data,
        "user_data": user_data,
        "match_score": match,
        "risk_score": risk
    }


# =============================
# OPTIONAL CLI ENTRY
# =============================
if __name__ == "__main__":

    # Keep as editable values (no interactive input forced)
    RR_NUMBER = "N-435608"
    USER_NAME = ""
    USER_ADDRESS = ""

    result = run_waterbill_wrapper(RR_NUMBER, USER_NAME, USER_ADDRESS)

    print("\nSYSTEM DATA :", result["system_data"])
    print("USER INPUT  :", result["user_data"])
    print("MATCH SCORE:", result["match_score"])
    print("RISK SCORE :", result["risk_score"])
