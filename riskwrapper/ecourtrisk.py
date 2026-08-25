import os
import json
from anthropic import Anthropic

# ============================================================
# CONFIG
# ============================================================

API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = Anthropic(
    api_key=API_KEY
)

MODEL = os.getenv(
    "claude-opus-4-7"
)


# ============================================================
# JSON PARSER
# ============================================================

def parse_json(text):
    """Extract the first JSON object from an LLM response."""
    if not text:
        raise ValueError("Empty LLM response")

    text = text.replace("```json", "")
    text = text.replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No valid JSON object found in LLM response")

    return json.loads(text[start:end + 1])


# ============================================================
# NORMALIZE eCOURT JSON
# ============================================================

def normalize_case_data(raw_case):
    """
    Converts the JSON produced by ecourt.py into the compact
    structure used by the risk engine.

    IMPORTANT:
    This function does NOT perform data extraction with an AI model.
    It only reads values already present in the eCourt JSON.
    """

    # ecourt.py normally stores the actual case inside "views".
    if isinstance(raw_case, dict) and isinstance(raw_case.get("views"), list):
        views = raw_case["views"]
        if not views:
            return {}

        # Use the first successfully populated view.
        view = next(
            (
                v for v in views
                if isinstance(v, dict)
                and (
                    v.get("case_details")
                    or v.get("case_status")
                    or v.get("petitioner_and_advocate")
                    or v.get("respondent_and_advocate")
                )
            ),
            views[0] if isinstance(views[0], dict) else {}
        )
    else:
        view = raw_case if isinstance(raw_case, dict) else {}

    case_details = view.get("case_details") or {}
    case_status = view.get("case_status") or {}

    # Support both the original eCourt keys and normalized keys.
    def get_value(data, *keys):
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return str(data[key]).strip()
        return ""

    case_type = get_value(
        case_details,
        "Case Type",
        "case_type"
    )

    filing_number = get_value(
        case_details,
        "Filing Number",
        "filing_number"
    )

    registration_number = get_value(
        case_details,
        "Registration Number",
        "registration_number"
    )

    cnr_number = get_value(
        case_details,
        "CNR Number",
        "cnr_number"
    )

    filing_date = get_value(
        case_details,
        "Filing Date",
        "filing_date"
    )

    registration_date = get_value(
        case_details,
        "Registration Date",
        "registration_date"
    )

    first_hearing_date = get_value(
        case_status,
        "First Hearing Date",
        "first_hearing_date"
    )

    decision_date = get_value(
        case_status,
        "Decision Date",
        "decision_date"
    )

    # New DOM extractor may preserve the complete status fields.
    status = get_value(
        case_status,
        "Case Status",
        "case_status",
        "status"
    )

    nature_of_disposal = get_value(
        case_status,
        "Nature of Disposal",
        "nature_of_disposal"
    )

    court_name = get_value(
        view,
        "court_name",
        "Court Name",
        "court"
    )

    # If court_name was not stored inside the view, use the outer JSON.
    if not court_name and isinstance(raw_case, dict):
        court_name = get_value(
            raw_case,
            "court",
            "court_name"
        )

    # ------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------

    petitioner = view.get("petitioner_and_advocate") or []
    respondent = view.get("respondent_and_advocate") or []

    def party_names(parties):
        names = []

        if not isinstance(parties, list):
            return ""

        for party in parties:
            if isinstance(party, dict):
                name = get_value(
                    party,
                    "name",
                    "petitioner",
                    "respondent",
                    "party"
                )
                if name:
                    names.append(name)

            elif isinstance(party, str):
                value = party.strip()
                if value:
                    names.append(value)

        return "; ".join(names)

    petitioner_text = party_names(petitioner)
    respondent_text = party_names(respondent)

    # ------------------------------------------------------------
    # Acts
    # ------------------------------------------------------------

    acts = view.get("acts") or []
    act_values = []

    if isinstance(acts, list):
        for act in acts:
            if not isinstance(act, dict):
                continue

            values = []
            for key, value in act.items():
                if key == "_links":
                    continue

                value = str(value).strip() if value is not None else ""
                if value:
                    values.append(value)

            if values:
                act_values.append(" | ".join(values))

    act_text = "; ".join(act_values)

    # ------------------------------------------------------------
    # Pending flag
    # ------------------------------------------------------------

    pending = (
        status.upper() == "PENDING"
        or "PENDING" in status.upper()
    )

    return {
        "case_type": case_type,
        "filing_number": filing_number,
        "registration_number": registration_number,
        "cnr_number": cnr_number,
        "filing_date": filing_date,
        "registration_date": registration_date,
        "first_hearing_date": first_hearing_date,
        "decision_date": decision_date,
        "case_status": status,
        "nature_of_disposal": nature_of_disposal,
        "court_name": court_name,
        "petitioner": petitioner_text,
        "respondent": respondent_text,
        "act": act_text,
        "pending": pending
    }


# ============================================================
# LLM RISK ASSESSMENT
# ============================================================

def llm_court_risk_assessment(case_data):

    prompt = f"""
# ROLE

You are a Senior Indian Property Litigation Lawyer,
Real Estate Due Diligence Consultant,
and Civil Court Risk Assessment Specialist.

# CONTEXT

A prospective property buyer wants to evaluate whether an existing court case
creates legal risk before purchasing the property.

Assess ONLY the supplied case information.

Do NOT assume any facts.

# OBJECTIVE

Estimate Buyer Legal Risk.

Risk Scale

0 = No Legal Risk
100 = Extremely High Legal Risk

# EVALUATION FRAMEWORK

Evaluate:

1. Case Status
2. Nature of Litigation
3. Court Level
4. Parties
5. Disposal
6. Overall Buyer Risk

# DECISION GUIDELINES

Highest Risk:
- Pending property title dispute
- Pending injunction
- Specific performance
- Partition suit
- Execution petition
- High Court/Supreme Court litigation
- Government acquisition dispute

Moderate Risk:
- Civil disputes
- Transferred matters
- Appeals

Lower Risk:
- Disposed cases
- Dismissed petitions
- Compromised settlements

# IMPORTANT RULES

Never invent facts.

Never assume the property is affected unless supported.

Missing information does not increase risk.

Reasons must reference supplied case data.

Recommendations must be practical.

# CASE DATA

{json.dumps(case_data, indent=2, ensure_ascii=False)}

# OUTPUT

Return ONLY valid JSON.

{{
    "risk_score": 0,
    "risk_level": "LOW|MEDIUM|HIGH",
    "confidence": 0.0,
    "major_risks": [],
    "positive_findings": [],
    "reasoning": [],
    "recommendations": [],
    "summary": ""
}}
""".strip()
    response = client.messages.create(
        model=MODEL,
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
        raise ValueError("Claude returned an empty response")

    return parse_json(raw)

# ============================================================
# PYTHON CASE RISK ENGINE
# ============================================================

def calculate_case_risk(case_data):

    score = 0
    reasons = []

    status = case_data.get("case_status", "").upper()
    disposal = case_data.get("nature_of_disposal", "").upper()
    case_type = case_data.get("case_type", "").upper()

    # --------------------------------------------------------
    # CASE STATUS
    # --------------------------------------------------------

    if "PENDING" in status:
        score += 60
        reasons.append("Case is still pending")

    elif "DISPOSED" in status:
        score += 5
        reasons.append("Case already disposed")

    elif "CLOSED" in status:
        score += 5
        reasons.append("Case is closed")

    else:
        score += 20
        reasons.append("Case status unclear")

    # --------------------------------------------------------
    # EXECUTION PETITIONS
    # --------------------------------------------------------

    if "EXECUTION" in case_type:
        score += 10
        reasons.append("Execution petition filed")

    # --------------------------------------------------------
    # TRANSFERRED CASE
    # --------------------------------------------------------

    if "TRANSFERRED" in disposal:
        score += 5
        reasons.append("Transferred matter")

    # --------------------------------------------------------
    # CIVIL DISPUTE
    # --------------------------------------------------------

    if "CIVIL" in case_type:
        score += 10
        reasons.append("Civil dispute")

    score = min(score, 100)

    if score >= 70:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "risk_score": score,
        "risk_level": level,
        "reasons": reasons
    }


# ============================================================
# SCORE BLENDING
# ============================================================

def blend_scores(rule_score, llm_score, rule_weight=0.7):

    final = (
        rule_score * rule_weight +
        llm_score * (1 - rule_weight)
    )

    if final >= 70:
        level = "HIGH"
    elif final >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "risk_score": round(final, 2),
        "risk_level": level
    }


# ============================================================
# READ eCOURT JSON FILES
# ============================================================

def load_ecourt_json_files(folder):
    """
    Reads JSON files generated by ecourt.py.

    Expected structure:

        ecourtjson/
        ├── case_1.json
        ├── case_2.json
        ├── case_3.json
        └── ...

    No screenshots are required.
    No OCR is required.
    No Qwen is required.
    """

    if not os.path.isdir(folder):
        raise FileNotFoundError(
            f"eCourt JSON folder not found: {folder}"
        )

    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(".json")
    )

    return files


# ============================================================
# ANALYZE eCOURT JSON
# ============================================================

def analyze_ecourt_json(
    folder
):

    all_cases = []

    json_files = load_ecourt_json_files(folder)

    if not json_files:
        return {
            "document_type": "ECOURT",
            "status": "FAILED",
            "error": "No JSON case files found."
        }

    print("\n" + "=" * 90)
    print("⚖️ eCOURT JSON RISK ANALYSIS")
    print("=" * 90)
    print(f"📁 JSON folder: {folder}")
    print(f"📄 Cases found: {len(json_files)}")
    print("=" * 90)

    # --------------------------------------------------------
    # PROCESS EACH JSON
    # --------------------------------------------------------

    for case_index, filename in enumerate(
        json_files,
        start=1
    ):

        filepath = os.path.join(
            folder,
            filename
        )

        print("\n" + "=" * 90)
        print(
            f"⚖️ PROCESSING CASE {case_index}: "
            f"{filename}"
        )
        print("=" * 90)

        try:
            with open(
                filepath,
                "r",
                encoding="utf-8"
            ) as f:
                raw_case = json.load(f)

        except Exception as e:
            print(f"❌ JSON read failed: {e}")

            all_cases.append({
                "case_id": filename,
                "status": "FAILED",
                "error": str(e)
            })

            continue

        # ----------------------------------------------------
        # NO DATA EXTRACTION MODEL HERE
        # ----------------------------------------------------

        case_data = normalize_case_data(raw_case)

        print("\n📦 CASE DATA FROM eCOURT JSON:")
        print(
            json.dumps(
                case_data,
                indent=2,
                ensure_ascii=False
            )
        )

        # ----------------------------------------------------
        # PYTHON RISK
        # ----------------------------------------------------

        rule_risk = calculate_case_risk(
            case_data
        )

        print("\n🐍 PYTHON RISK:")
        print(
            json.dumps(
                rule_risk,
                indent=2,
                ensure_ascii=False
            )
        )

        # ----------------------------------------------------
        # GEMINI RISK
        # ----------------------------------------------------

        try:

            llm_risk = llm_court_risk_assessment(
                case_data
            )

            print("\n🤖 GEMINI RISK:")
            print(
                json.dumps(
                    llm_risk,
                    indent=2,
                    ensure_ascii=False
                )
            )

            final_assessment = blend_scores(
                rule_risk["risk_score"],
                float(llm_risk.get("risk_score", 0))
            )

        except Exception as e:

            print(
                f"⚠️ Gemini risk failed: {e}"
            )

            llm_risk = {
                "error": str(e)
            }

            final_assessment = {
                "risk_score":
                    rule_risk["risk_score"],

                "risk_level":
                    rule_risk["risk_level"]
            }

        # ----------------------------------------------------
        # STORE RESULT
        # ----------------------------------------------------

        all_cases.append({

            "case_id":
                filename,

            "case_data":
                case_data,

            "rule_based_risk":
                rule_risk,

            "llm_risk":
                llm_risk,

            "final_assessment":
                final_assessment
        })

    # ========================================================
    # OVERALL RISK
    # ========================================================

    valid_cases = [
        c for c in all_cases
        if "final_assessment" in c
    ]

    if valid_cases:

        overall_score = sum(
            c["final_assessment"]["risk_score"]
            for c in valid_cases
        ) / len(valid_cases)

        if overall_score >= 70:
            overall_level = "HIGH"
        elif overall_score >= 40:
            overall_level = "MEDIUM"
        else:
            overall_level = "LOW"

    else:

        overall_score = None
        overall_level = None

    result = {

        "document_type":
            "ECOURT",

        "status":
            "RISK_ANALYSIS_SUCCESS",

        "case_count":
            len(all_cases),

        "cases":
            all_cases,

        "overall_court_risk": {

            "risk_score":
                round(overall_score, 2)
                if overall_score is not None
                else None,

            "risk_level":
                overall_level
        }
    }

    print("\n" + "=" * 90)
    print("🔍 FINAL eCOURT RISK RESULT")
    print("=" * 90)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

    print("=" * 90)

    return result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    result = analyze_ecourt_json(
        folder=r"D:\aasthiv2\Aasthi\wrappercode\ecourtjson"
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )