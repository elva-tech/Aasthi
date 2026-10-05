# wrapperlaw.py
"""
KAOA ASSOCIATION BYE-LAWS RISK WRAPPER
======================================

PIPELINE
--------

1. Read Association Bye-laws TXT
2. Split document ONCE into overlapping chunks
3. Qwen3:8B extracts facts from each chunk
4. Python parses and validates each chunk
5. Python OR-merges boolean facts
6. Python validates merged extraction against FULL TXT
7. Python calculates deterministic Safety Score
8. Python converts Safety Score -> Risk Score
9. Gemini performs independent AI risk analysis
10. Claude code is retained but COMMENTED OUT for future use
11. Return combined result

IMPORTANT
---------

Chunk-level FALSE means:

    "Not found in this chunk."

It does NOT mean:

    "Not found anywhere in the document."

Therefore boolean fields are merged using OR logic.

SCORING
-------

Python Safety Score:

    0   = very unsafe
    100 = very safe

Python Risk Score:

    100 - Safety Score

    0   = lowest risk
    100 = highest risk

AI Risk Score:

    Gemini independently provides a qualitative
    risk assessment from 0 to 100.

The Python score remains the deterministic score.
Gemini does NOT overwrite the Python score.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
from google import genai

# ============================================================
# OPTIONAL CLAUDE IMPORT
# ============================================================
#
# Claude is intentionally retained but COMMENTED OUT.
#
# When you want to switch back to Claude:
#
# 1. Uncomment the import
# 2. Uncomment get_claude_client()
# 3. Uncomment call_claude()
# 4. Change AI_PROVIDER = "claude"
#
# ============================================================

from anthropic import Anthropic


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# QWEN / OLLAMA
# ------------------------------------------------------------

EXTRACTION_MODEL = os.getenv(
    "QWEN_MODEL",
    "qwen3:8b"
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1"
)

qwen_client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama"
)

CHUNK_SIZE = int(
    os.getenv(
        "BYLAWS_CHUNK_SIZE",
        "8000"
    )
)

CHUNK_OVERLAP = int(
    os.getenv(
        "BYLAWS_CHUNK_OVERLAP",
        "500"
    )
)

QWEN_MAX_TOKENS = int(
    os.getenv(
        "QWEN_MAX_TOKENS",
        "5000"
    )
)

QWEN_TEMPERATURE = float(
    os.getenv(
        "QWEN_TEMPERATURE",
        "0"
    )
)


# ------------------------------------------------------------
# AI RISK PROVIDER
# ------------------------------------------------------------

# Active provider
#
# Current:
#     Gemini
#
# Future:
#     Claude
#
AI_PROVIDER = os.getenv(
    "BYLAWS_AI_PROVIDER",
    "claude"
).lower().strip()

# ------------------------------------------------------------
# GEMINI
# ------------------------------------------------------------

CLAUDE_RISK_MODEL = os.getenv(
    "CLAUDE_RISK_MODEL",
    "claude-opus-4-7"
)
# ------------------------------------------------------------
# CLAUDE
# ------------------------------------------------------------
#
# Retained for future use.
# Currently NOT ACTIVE.
#
# CLAUDE_RISK_MODEL = os.getenv(
#     "CLAUDE_RISK_MODEL",
#     "claude-opus-4-7"
# )


# ============================================================
# 1. EXTRACTION SCHEMA
# ============================================================

EXTRACTION_SCHEMA = {

    "property": {

        "city": "",

        "state": ""
    },

    "formation": {

        "entity_type": "",

        "is_registered": False,

        "registration_number_present": False,

        "registration_date_present": False
    },

    "declaration_deed": {

        "dod_present": False,

        "dod_registered": False,

        "dod_date_present": False
    },

    "bylaws": {

        "bylaws_present": False,

        "bylaws_registered_or_filed": False,

        "mentions_kaoa_act_or_rules": False,

        "core_sections_present": {

            "membership": False,

            "governance_committee": False,

            "meetings_quorum_voting": False,

            "maintenance_charges": False,

            "funds_audit_accounts": False,

            "penalties_dispute_resolution": False,

            "amendment_process": False
        }
    },

    "governance": {

        "agm_required": False,

        "agm_frequency_yearly": False,

        "elections_defined": False,

        "minutes_and_records_access": False
    },

    "financials": {

        "audit_required": False,

        "audit_frequency_yearly": False,

        "corpus_or_sinking_fund_mentioned": False,

        "collection_enforcement_defined": False
    },

    "property_compliance": {

        "insurance_mentioned": False,

        "fire_safety_compliance_mentioned": False,

        "common_areas_transfer_mentioned": False,

        "litigation_or_disputes_mentioned": False
    },

    "confidence": 0.0,

    "notes": []
}


def empty_schema() -> Dict[str, Any]:

    return copy.deepcopy(
        EXTRACTION_SCHEMA
    )


# ============================================================
# 2. EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = r"""
# ROLE

You are a Senior Apartment Owners Association Compliance Auditor,
KAOA Specialist, and Property Due Diligence Consultant.

# TASK

Extract facts from ONE CHUNK of an Association Bye-laws document.

You are NOT seeing the complete document.

Therefore:

true = explicitly supported by THIS chunk.

false = not explicitly supported by THIS chunk.

A false value does NOT mean the information is absent from the
complete document.

Do NOT guess.

Do NOT infer.

Do NOT use outside knowledge.

# IMPORTANT SEMANTIC RULES

Recognize equivalent terminology when the meaning is explicit.

Governance committee examples:

- Board of Managers
- Board of Management
- Managing Committee
- Executive Committee
- Association Committee
- Board of Office Bearers

=> governance_committee = true

AGM examples:

- Annual General Meeting
- Annual General Body Meeting
- AGM

=> agm_required = true

Election examples:

- Board elected every two years
- members shall elect the Board
- election of committee
- election of office bearers

=> elections_defined = true

Audit examples:

- accounts shall be audited
- auditor shall audit accounts
- annual audited statement
- audited annual financial statement

=> audit_required = true

Yearly audit examples:

- annual audit
- audited every year
- annual audited accounts
- annual financial statement

=> audit_frequency_yearly = true

Fund examples:

- sinking fund
- reserve fund
- corpus fund

=> corpus_or_sinking_fund_mentioned = true

Collection examples:

- recovery of dues
- recovery of maintenance charges
- unpaid assessments may be recovered
- amounts due may be recovered
- collection of association dues

=> collection_enforcement_defined = true

Membership examples:

- owner shall become a member
- membership
- members of the association

=> membership = true

Maintenance examples:

- maintenance charges
- common expenses
- assessment of common expenses
- contribution towards common expenses

=> maintenance_charges = true

# STRICT PROPERTY COMPLIANCE RULES

insurance_mentioned:

true ONLY when insurance of the building, property,
common areas, or equivalent is explicitly mentioned.

Do NOT infer insurance from general maintenance provisions.

fire_safety_compliance_mentioned:

true ONLY when fire safety, fire prevention, fire equipment,
fire authority, fire clearance, fire NOC, or equivalent
is explicitly mentioned.

common_areas_transfer_mentioned:

true ONLY when transfer, conveyance, vesting, handing over,
or equivalent treatment of common areas/common facilities
is explicitly mentioned.

litigation_or_disputes_mentioned:

true ONLY when litigation, court proceedings, arbitration,
legal dispute, dispute resolution, or equivalent legal
proceedings are explicitly mentioned.

Do NOT treat general complaints as litigation.

# BYE-LAWS REGISTRATION RULE

bylaws_registered_or_filed = true ONLY when the BYE-LAWS themselves
are explicitly stated to be registered, filed, approved, adopted,
or submitted to an authority.

Registration of a Declaration Deed alone does NOT prove that the
bye-laws themselves are registered.

# OUTPUT

Return ONLY this JSON structure:

{
  "facts": {
    "property": {
      "city": "",
      "state": ""
    },

    "formation": {
      "entity_type": "",
      "is_registered": false,
      "registration_number_present": false,
      "registration_date_present": false
    },

    "declaration_deed": {
      "dod_present": false,
      "dod_registered": false,
      "dod_date_present": false
    },

    "bylaws": {
      "bylaws_present": false,
      "bylaws_registered_or_filed": false,
      "mentions_kaoa_act_or_rules": false,
      "core_sections_present": {
        "membership": false,
        "governance_committee": false,
        "meetings_quorum_voting": false,
        "maintenance_charges": false,
        "funds_audit_accounts": false,
        "penalties_dispute_resolution": false,
        "amendment_process": false
      }
    },

    "governance": {
      "agm_required": false,
      "agm_frequency_yearly": false,
      "elections_defined": false,
      "minutes_and_records_access": false
    },

    "financials": {
      "audit_required": false,
      "audit_frequency_yearly": false,
      "corpus_or_sinking_fund_mentioned": false,
      "collection_enforcement_defined": false
    },

    "property_compliance": {
      "insurance_mentioned": false,
      "fire_safety_compliance_mentioned": false,
      "common_areas_transfer_mentioned": false,
      "litigation_or_disputes_mentioned": false
    },

    "notes": []
  }
}

# FINAL RULES

Return ONLY JSON.

No Markdown.

No code fences.

No explanation.

No reasoning.

No <think>.

Do not invent facts.
"""


# ============================================================
# 3. RISK PROMPT
# ============================================================

RISK_PROMPT = r"""
# ROLE

You are a Senior Apartment Owners Association Compliance Auditor,
KAOA Specialist, and Property Due Diligence Risk Analyst.

# TASK

Assess the extracted Association Bye-laws information below.

Use ONLY the supplied extracted data.

Do NOT invent facts.

Do NOT assume missing information is compliant.

Do NOT assume missing information is non-compliant.

Missing information should be identified as a verification point.

# PYTHON DETERMINISTIC SCORE

The Python system has already calculated an independent
deterministic risk score.

You may consider it as supporting context, but you MUST NOT
blindly copy it.

# RISK CATEGORIES

Evaluate:

1. Legal formation and registration
2. Declaration Deed
3. Bye-laws coverage
4. Governance and transparency
5. Financial controls
6. Maintenance and collection
7. Property compliance
8. Missing or weak documentation

# IMPORTANT

Every risk must be based on supplied data.

Do not create a risk merely because a field is false.

A false field means that the information was not established
by the extraction.

Distinguish:

- confirmed weakness
- missing information
- positive compliance evidence

# OUTPUT

Return ONLY valid JSON:

{
  "risk_score": 0,
  "risk_level": "LOW",
  "risk_summary": "",
  "key_risks": [],
  "positive_factors": [],
  "missing_information": [],
  "recommended_actions": []
}

# RISK SCORE

risk_score:

0 = very low risk

100 = very high risk

Risk levels:

0-20     LOW
21-40    MEDIUM-LOW
41-60    MEDIUM
61-80    HIGH
81-100   VERY HIGH

Do not output Markdown.
Do not output code fences.
Return JSON only.
"""


# ============================================================
# 4. JSON EXTRACTION
# ============================================================

def extract_json_object(
    raw: str
) -> Dict[str, Any]:

    if not raw:

        raise ValueError(
            "Empty model response."
        )

    text = str(
        raw
    ).strip()

    # Remove markdown fences
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    ).strip()

    # Direct JSON
    try:

        value = json.loads(
            text
        )

        if isinstance(
            value,
            dict
        ):

            return value

    except Exception:
        pass

    # Find first balanced JSON object
    start = text.find(
        "{"
    )

    if start == -1:

        raise ValueError(
            "No JSON object found in model output."
        )

    depth = 0
    in_string = False
    escaped = False

    for i in range(
        start,
        len(text)
    ):

        ch = text[i]

        if in_string:

            if escaped:

                escaped = False

            elif ch == "\\":

                escaped = True

            elif ch == '"':

                in_string = False

            continue

        if ch == '"':

            in_string = True

        elif ch == "{":

            depth += 1

        elif ch == "}":

            depth -= 1

            if depth == 0:

                candidate = text[
                    start:i + 1
                ]

                value = json.loads(
                    candidate
                )

                if not isinstance(
                    value,
                    dict
                ):

                    raise ValueError(
                        "Extracted JSON is not an object."
                    )

                return value

    raise ValueError(
        "Incomplete JSON object in model output."
    )


# ============================================================
# 5. SCHEMA VALIDATION
# ============================================================

def ensure_schema(
    data: Dict[str, Any]
) -> Dict[str, Any]:

    result = empty_schema()

    if not isinstance(
        data,
        dict
    ):

        return result

    def recursive_merge(
        destination: Dict[str, Any],
        source: Dict[str, Any]
    ):

        for key, value in source.items():

            if key not in destination:

                continue

            if (
                isinstance(
                    destination[key],
                    dict
                )
                and isinstance(
                    value,
                    dict
                )
            ):

                recursive_merge(
                    destination[key],
                    value
                )

            elif isinstance(
                destination[key],
                bool
            ):

                destination[key] = (
                    value is True
                )

            elif isinstance(
                destination[key],
                list
            ):

                if isinstance(
                    value,
                    list
                ):

                    destination[key] = value

            elif value is not None:

                destination[key] = value

    recursive_merge(
        result,
        data
    )

    # Confidence
    try:

        confidence = float(
            result.get(
                "confidence",
                0.0
            )
        )

    except Exception:

        confidence = 0.0

    result["confidence"] = max(
        0.0,
        min(
            1.0,
            confidence
        )
    )

    # Notes
    if not isinstance(
        result.get("notes"),
        list
    ):

        result["notes"] = []

    return result


# ============================================================
# 6. DOCUMENT CHUNKING
# ============================================================

def split_document(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP
) -> List[str]:

    if not text:

        return []

    if chunk_size <= 0:

        raise ValueError(
            "chunk_size must be > 0"
        )

    if overlap < 0:

        raise ValueError(
            "overlap cannot be negative"
        )

    if overlap >= chunk_size:

        raise ValueError(
            "overlap must be smaller than chunk_size"
        )

    chunks = []

    start = 0
    length = len(text)

    while start < length:

        end = min(
            start + chunk_size,
            length
        )

        chunk = text[
            start:end
        ]

        if chunk.strip():

            chunks.append(
                chunk
            )

        if end >= length:

            break

        start = (
            end - overlap
        )

    return chunks


# ============================================================
# 7. QWEN CHUNK EXTRACTION
# ============================================================

def call_qwen_chunk(
    prompt: str,
    chunk: str,
    chunk_number: int,
    total_chunks: int
) -> Dict[str, Any]:

    system_prompt = """
You are a strict JSON information extraction engine.

Return ONLY valid JSON.

Do not explain.

Do not summarize.

Do not use Markdown.

Do not use code fences.

Do not output <think>.

The first JSON character must be {.
"""

    user_prompt = (
        prompt
        + "\n\n"
        + "DOCUMENT CHUNK:\n\n"
        + chunk
        + "\n\n"
        + "RETURN ONLY JSON."
    )

    response = qwen_client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        temperature=QWEN_TEMPERATURE,
        max_tokens=QWEN_MAX_TOKENS
    )

    raw = (
        response.choices[0].message.content
        or ""
    ).strip()

    try:

        return extract_json_object(
            raw
        )

    except Exception as first_error:

        print(
            f"\n[QWEN] JSON parsing failed: "
            f"{first_error}"
        )

        print(
            "[QWEN] Retrying chunk..."
        )

        retry_response = (
            qwen_client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """
Return ONLY valid JSON.

No Markdown.
No code fences.
No explanation.
No <think>.
"""
                    },
                    {
                        "role": "user",
                        "content": (
                            "Extract the requested facts "
                            "from this document chunk.\n\n"
                            + user_prompt
                            + "\n\n"
                            "RETURN ONLY JSON."
                        )
                    }
                ],
                temperature=0,
                max_tokens=QWEN_MAX_TOKENS
            )
        )

        retry_raw = (
            retry_response
            .choices[0]
            .message
            .content
            or ""
        ).strip()


        return extract_json_object(
            retry_raw
        )


# ============================================================
# 8. MERGE CHUNK RESULTS
# ============================================================

def merge_chunk_results(
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:

    if not results:

        return empty_schema()

    def merge_values(
        values: List[Any]
    ) -> Any:

        if not values:

            return None

        # ----------------------------------------------------
        # BOOLEAN
        # ----------------------------------------------------

        if all(
            isinstance(
                value,
                bool
            )
            for value in values
        ):

            return any(
                value is True
                for value in values
            )

        # ----------------------------------------------------
        # DICTIONARY
        # ----------------------------------------------------

        if all(
            isinstance(
                value,
                dict
            )
            for value in values
        ):

            merged = {}

            keys = set()

            for value in values:

                keys.update(
                    value.keys()
                )

            for key in keys:

                child_values = [

                    value[key]

                    for value in values

                    if key in value
                ]

                merged[key] = (
                    merge_values(
                        child_values
                    )
                )

            return merged

        # ----------------------------------------------------
        # LIST
        # ----------------------------------------------------

        if all(
            isinstance(
                value,
                list
            )
            for value in values
        ):

            merged_list = []

            for value in values:

                for item in value:

                    if item not in merged_list:

                        merged_list.append(
                            item
                        )

            return merged_list

        # ----------------------------------------------------
        # STRING / NUMBER
        # ----------------------------------------------------

        for value in values:

            if value not in (
                "",
                None
            ):

                return value

        return values[0]

    merged = merge_values(
        results
    )

    return ensure_schema(
        merged
    )


# ============================================================
# 9. FINAL CONFIDENCE
# ============================================================

def calculate_final_confidence(
    results: List[Dict[str, Any]]
) -> float:

    confidences = []

    for result in results:

        try:

            confidence = float(
                result.get(
                    "confidence",
                    0.0
                )
            )

        except Exception:

            continue

        if 0 <= confidence <= 1:

            confidences.append(
                confidence
            )

    if not confidences:

        return 0.0

    # Highest reliable chunk confidence.
    return round(
        max(
            confidences
        ),
        2
    )


# ============================================================
# 10. TEXT EVIDENCE HELPERS
# ============================================================

def text_has_any(
    text: str,
    patterns: List[str]
) -> bool:

    lowered = text.lower()

    return any(
        pattern.lower() in lowered
        for pattern in patterns
    )


def add_validation_note(
    extract: Dict[str, Any],
    message: str
) -> None:

    notes = extract.get(
        "notes"
    )

    if not isinstance(
        notes,
        list
    ):

        notes = []

    if message not in notes:

        notes.append(
            message
        )

    extract["notes"] = notes


# ============================================================
# 11. DETERMINISTIC FULL-TXT VALIDATION
# ============================================================

def validate_extraction_against_text(
    extract: Dict[str, Any],
    text: str
) -> Dict[str, Any]:

    extract = ensure_schema(
        extract
    )

    if not text:

        return extract

    lowered = text.lower()

    # --------------------------------------------------------
    # PROPERTY
    # --------------------------------------------------------

    if (
        not extract["property"]["city"]
        and text_has_any(
            text,
            [
                "bengaluru",
                "bangalore"
            ]
        )
    ):

        extract["property"]["city"] = (
            "Bengaluru"
        )

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "property.city = Bengaluru."
        )

    if (
        not extract["property"]["state"]
        and text_has_any(
            text,
            [
                "karnataka"
            ]
        )
    ):

        extract["property"]["state"] = (
            "Karnataka"
        )

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "property.state = Karnataka."
        )

    # --------------------------------------------------------
    # BYE-LAWS
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "bye-laws",
            "byelaws",
            "by-laws",
            "association bye laws"
        ]
    ):

        extract[
            "bylaws"
        ][
            "bylaws_present"
        ] = True

    # KAOA
    if text_has_any(
        text,
        [
            "karnataka apartment ownership act",
            "karnataka apartment ownership rules",
            "kaoa act",
            "kaoa rules"
        ]
    ):

        extract[
            "bylaws"
        ][
            "mentions_kaoa_act_or_rules"
        ] = True

    # --------------------------------------------------------
    # MEMBERSHIP
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "membership",
            "members of the association",
            "owner shall become a member",
            "each apartment owner shall be a member"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "membership"
        ] = True

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "bylaws.core_sections_present.membership = True."
        )

    # --------------------------------------------------------
    # GOVERNANCE COMMITTEE
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "board of managers",
            "board of management",
            "managing committee",
            "executive committee",
            "association committee",
            "board of office bearers",
            "office bearers"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "governance_committee"
        ] = True

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "bylaws.core_sections_present.governance_committee = True "
            "— a Board/Committee/Office Bearers provision is explicitly present."
        )

    # --------------------------------------------------------
    # MEETINGS / QUORUM / VOTING
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "quorum",
            "general body meeting",
            "annual general meeting",
            "annual general body meeting",
            "voting",
            "vote of the members"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "meetings_quorum_voting"
        ] = True

    # --------------------------------------------------------
    # MAINTENANCE
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "maintenance charges",
            "common expenses",
            "common expense",
            "maintenance contribution",
            "contribution towards common expenses"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "maintenance_charges"
        ] = True

    # --------------------------------------------------------
    # FUNDS / AUDIT / ACCOUNTS
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "audit",
            "auditor",
            "accounts",
            "financial statement",
            "audited statement"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "funds_audit_accounts"
        ] = True

    # --------------------------------------------------------
    # PENALTIES / DISPUTES
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "dispute resolution",
            "disputes shall",
            "arbitration",
            "penalty",
            "penalties",
            "defaulting member",
            "recovery proceedings"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "penalties_dispute_resolution"
        ] = True

    # --------------------------------------------------------
    # AMENDMENT
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "amendment",
            "amend these bye-laws",
            "amendment of the bye-laws"
        ]
    ):

        extract[
            "bylaws"
        ][
            "core_sections_present"
        ][
            "amendment_process"
        ] = True

    # --------------------------------------------------------
    # AGM
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "annual general meeting",
            "annual general body meeting",
            "agm"
        ]
    ):

        extract[
            "governance"
        ][
            "agm_required"
        ] = True

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "governance.agm_required = True."
        )

    # --------------------------------------------------------
    # YEARLY AGM
    # --------------------------------------------------------

    yearly_agm_patterns = [
        "every year",
        "once every year",
        "annually",
        "annual general meeting",
        "annual general body meeting"
    ]

    if (
        text_has_any(
            text,
            yearly_agm_patterns
        )
        and text_has_any(
            text,
            [
                "general meeting",
                "general body meeting",
                "annual general meeting",
                "annual general body meeting"
            ]
        )
    ):

        # Only set true where annual/general meeting language
        # actually occurs.
        extract[
            "governance"
        ][
            "agm_frequency_yearly"
        ] = True

    # --------------------------------------------------------
    # ELECTIONS
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "elected",
            "election",
            "shall elect",
            "elected every",
            "election of the board"
        ]
    ):

        extract[
            "governance"
        ][
            "elections_defined"
        ] = True

    # --------------------------------------------------------
    # MINUTES / RECORDS
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "minutes",
            "minutes of the meeting",
            "records of the association",
            "records shall be maintained",
            "inspection of records",
            "books and records"
        ]
    ):

        extract[
            "governance"
        ][
            "minutes_and_records_access"
        ] = True

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "governance.minutes_and_records_access = True."
        )

    # --------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "accounts shall be audited",
            "audited accounts",
            "audited annual",
            "auditor shall audit",
            "annual audit",
            "audit of accounts"
        ]
    ):

        extract[
            "financials"
        ][
            "audit_required"
        ] = True

    # --------------------------------------------------------
    # YEARLY AUDIT
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "annual audited",
            "audited annual",
            "annual financial statement",
            "every year"
        ]
    ) and text_has_any(
        text,
        [
            "audit",
            "audited",
            "accounts",
            "financial statement"
        ]
    ):

        extract[
            "financials"
        ][
            "audit_frequency_yearly"
        ] = True

    # --------------------------------------------------------
    # SINKING / RESERVE / CORPUS
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "sinking fund",
            "reserve fund",
            "corpus fund",
            "corpus"
        ]
    ):

        extract[
            "financials"
        ][
            "corpus_or_sinking_fund_mentioned"
        ] = True

    # --------------------------------------------------------
    # COLLECTION / RECOVERY
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "recovery of dues",
            "recovery of maintenance charges",
            "recover the amount",
            "amounts due to the association",
            "unpaid maintenance",
            "arrears",
            "dues payable"
        ]
    ):

        extract[
            "financials"
        ][
            "collection_enforcement_defined"
        ] = True

        add_validation_note(
            extract,
            "Deterministic evidence correction: "
            "financials.collection_enforcement_defined = True."
        )

    # --------------------------------------------------------
    # INSURANCE
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "insurance of the building",
            "building insurance",
            "property insurance",
            "insurance policy",
            "insure the building",
            "insurance coverage"
        ]
    ):

        extract[
            "property_compliance"
        ][
            "insurance_mentioned"
        ] = True

    # --------------------------------------------------------
    # FIRE SAFETY
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "fire safety",
            "fire protection",
            "fire prevention",
            "fire equipment",
            "fire clearance",
            "fire noc",
            "fire authority",
            "fire fighting"
        ]
    ):

        extract[
            "property_compliance"
        ][
            "fire_safety_compliance_mentioned"
        ] = True

    # --------------------------------------------------------
    # COMMON AREA TRANSFER
    # --------------------------------------------------------

    if (
        text_has_any(
            text,
            [
                "common areas",
                "common area",
                "common facilities"
            ]
        )
        and text_has_any(
            text,
            [
                "transfer",
                "transferred",
                "conveyance",
                "vested",
                "vesting",
                "handing over",
                "handed over"
            ]
        )
    ):

        extract[
            "property_compliance"
        ][
            "common_areas_transfer_mentioned"
        ] = True

    # --------------------------------------------------------
    # LITIGATION / DISPUTES
    # --------------------------------------------------------

    if text_has_any(
        text,
        [
            "litigation",
            "court proceedings",
            "legal proceedings",
            "arbitration",
            "legal dispute",
            "dispute resolution"
        ]
    ):

        extract[
            "property_compliance"
        ][
            "litigation_or_disputes_mentioned"
        ] = True

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    # Do NOT artificially make confidence high merely because
    # the document contains many facts.
    #
    # Confidence remains based on Qwen chunk confidence unless
    # already established by the caller.

    extract = ensure_schema(
        extract
    )

    return extract


# ============================================================
# 12. SCORING HELPERS
# ============================================================

def get_nested(
    data: Dict[str, Any],
    *keys
) -> Any:

    current = data

    for key in keys:

        if not isinstance(
            current,
            dict
        ):

            return None

        current = current.get(
            key
        )

    return current


def bool_score(
    flag: Any,
    points: int
) -> int:

    return (
        points
        if flag is True
        else 0
    )


# ============================================================
# 13. PYTHON DETERMINISTIC RISK SCORE
# ============================================================

def compute_association_risk_score(
    extract: Dict[str, Any]
) -> Tuple[
    int,
    str,
    Dict[str, Any]
]:

    # --------------------------------------------------------
    # 1. LEGAL FORMATION / REGISTRATION = 25
    # --------------------------------------------------------

    legal = 0

    legal += bool_score(
        get_nested(
            extract,
            "formation",
            "is_registered"
        ),
        10
    )

    legal += bool_score(
        get_nested(
            extract,
            "formation",
            "registration_number_present"
        ),
        5
    )

    legal += bool_score(
        get_nested(
            extract,
            "formation",
            "registration_date_present"
        ),
        3
    )

    legal += bool_score(
        get_nested(
            extract,
            "declaration_deed",
            "dod_present"
        ),
        2
    )

    legal += bool_score(
        get_nested(
            extract,
            "declaration_deed",
            "dod_registered"
        ),
        5
    )

    # Cap to 25
    legal = min(
        legal,
        25
    )

    # --------------------------------------------------------
    # 2. BYE-LAWS COVERAGE = 15
    # --------------------------------------------------------

    bylaws = 0

    bylaws += bool_score(
        get_nested(
            extract,
            "bylaws",
            "bylaws_present"
        ),
        2
    )

    bylaws += bool_score(
        get_nested(
            extract,
            "bylaws",
            "bylaws_registered_or_filed"
        ),
        2
    )

    bylaws += bool_score(
        get_nested(
            extract,
            "bylaws",
            "mentions_kaoa_act_or_rules"
        ),
        2
    )

    core = get_nested(
        extract,
        "bylaws",
        "core_sections_present"
    ) or {}

    core_fields = [
        "membership",
        "governance_committee",
        "meetings_quorum_voting",
        "maintenance_charges",
        "funds_audit_accounts",
        "penalties_dispute_resolution",
        "amendment_process"
    ]

    for field in core_fields:

        if core.get(field) is True:

            bylaws += 1

    bylaws = min(
        bylaws,
        15
    )

    # --------------------------------------------------------
    # 3. GOVERNANCE = 15
    # --------------------------------------------------------

    gov = 0

    gov += bool_score(
        get_nested(
            extract,
            "governance",
            "agm_required"
        ),
        4
    )

    gov += bool_score(
        get_nested(
            extract,
            "governance",
            "agm_frequency_yearly"
        ),
        3
    )

    gov += bool_score(
        get_nested(
            extract,
            "governance",
            "elections_defined"
        ),
        4
    )

    gov += bool_score(
        get_nested(
            extract,
            "governance",
            "minutes_and_records_access"
        ),
        4
    )

    gov = min(
        gov,
        15
    )

    # --------------------------------------------------------
    # 4. FINANCIAL DISCIPLINE = 20
    # --------------------------------------------------------

    fin = 0

    fin += bool_score(
        get_nested(
            extract,
            "financials",
            "audit_required"
        ),
        6
    )

    fin += bool_score(
        get_nested(
            extract,
            "financials",
            "audit_frequency_yearly"
        ),
        4
    )

    fin += bool_score(
        get_nested(
            extract,
            "financials",
            "corpus_or_sinking_fund_mentioned"
        ),
        4
    )

    fin += bool_score(
        get_nested(
            extract,
            "financials",
            "collection_enforcement_defined"
        ),
        6
    )

    fin = min(
        fin,
        20
    )

    # --------------------------------------------------------
    # 5. PROPERTY COMPLIANCE = 10
    # --------------------------------------------------------

    comp = 0

    comp += bool_score(
        get_nested(
            extract,
            "property_compliance",
            "insurance_mentioned"
        ),
        2
    )

    comp += bool_score(
        get_nested(
            extract,
            "property_compliance",
            "fire_safety_compliance_mentioned"
        ),
        3
    )

    comp += bool_score(
        get_nested(
            extract,
            "property_compliance",
            "common_areas_transfer_mentioned"
        ),
        3
    )

    # Absence of litigation is not automatically a positive.
    # Therefore litigation field is not awarded points.

    comp = min(
        comp,
        10
    )

    # --------------------------------------------------------
    # 6. EVIDENCE CONFIDENCE = 15
    # --------------------------------------------------------

    try:

        confidence = float(
            extract.get(
                "confidence",
                0.0
            )
        )

    except Exception:

        confidence = 0.0

    confidence = max(
        0.0,
        min(
            1.0,
            confidence
        )
    )

    confidence_points = round(
        15 * confidence
    )

    # --------------------------------------------------------
    # TOTAL SAFETY
    # --------------------------------------------------------

    total = (
        legal
        + bylaws
        + gov
        + fin
        + comp
        + confidence_points
    )

    total = max(
        0,
        min(
            100,
            total
        )
    )

    # --------------------------------------------------------
    # RISK LEVEL
    # --------------------------------------------------------

    if total >= 85:

        level = "LOW"

    elif total >= 70:

        level = "MEDIUM-LOW"

    elif total >= 55:

        level = "MEDIUM"

    elif total >= 40:

        level = "HIGH"

    else:

        level = "VERY HIGH"

    breakdown = {

        "dimension_scores": {

            "legal_formation_registration": {

                "score": legal,

                "max": 25
            },

            "bylaws_coverage_quality": {

                "score": bylaws,

                "max": 15
            },

            "governance_transparency": {

                "score": gov,

                "max": 15
            },

            "financial_discipline": {

                "score": fin,

                "max": 20
            },

            "property_compliance": {

                "score": comp,

                "max": 10
            },

            "evidence_confidence": {

                "score": confidence_points,

                "max": 15
            }
        },

        "notes": extract.get(
            "notes",
            []
        )
    }

    return (
        total,
        level,
        breakdown
    )


# ============================================================
# 14. PYTHON RISK SCORE
# ============================================================

def risk_score_from_safety(
    score: Any
) -> Optional[int]:

    try:

        safety = float(
            score
        )

    except Exception:

        return None

    safety = max(
        0,
        min(
            100,
            safety
        )
    )

    return int(
        round(
            100 - safety
        )
    )


# ============================================================
# 17. CLAUDE CLIENT - COMMENTED OUT
# ============================================================

def get_claude_client():

    key = os.getenv(
         "ANTHROPIC_API_KEY"
     )

    if not key:

         raise RuntimeError(
             "Missing ANTHROPIC_API_KEY"
        )

    return Anthropic(
        api_key=key
    )


# ============================================================
# 18. CLAUDE RISK - COMMENTED OUT
# ============================================================

def call_claude(
    prompt: str,
    extract: Dict[str, Any],
    python_safety_score: Optional[int] = None,
    python_risk_score: Optional[int] = None
) -> str:

    client = get_claude_client()

    full_prompt = f"""
{prompt}

EXTRACTED BYLAWS DATA

{json.dumps(
    extract,
    indent=2,
    ensure_ascii=False
)}

PYTHON DETERMINISTIC SCORE

Safety Score:
{python_safety_score}

Risk Score:
{python_risk_score}

Return ONLY valid JSON.
"""

    response = client.messages.create(
        model=CLAUDE_RISK_MODEL,
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    )

    raw = ""

    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text

    if not raw.strip():
        raise RuntimeError(
            "Claude returned empty response."
        )

    return raw.strip()


# ============================================================
# 19. AI RISK NORMALIZATION
# ============================================================

def normalize_ai_risk(
    data: Any,
    raw_output: Optional[str] = None
) -> Dict[str, Any]:

    default = {

        "risk_score": None,

        "risk_level": "UNKNOWN",

        "risk_summary": "",

        "key_risks": [],

        "positive_factors": [],

        "missing_information": [],

        "recommended_actions": []
    }

    if not isinstance(
        data,
        dict
    ):

        if raw_output:

            default[
                "raw"
            ] = raw_output

        return default

    result = dict(
        default
    )

    # --------------------------------------------------------
    # Accept alternative score field names
    # --------------------------------------------------------

    score = data.get(
        "risk_score"
    )

    if score is None:

        score = data.get(
            "suggested_score_out_of_100"
        )

    if score is None:

        score = data.get(
            "score"
        )

    try:

        if score is not None:

            score = float(
                score
            )

            score = max(
                0.0,
                min(
                    100.0,
                    score
                )
            )

            result[
                "risk_score"
            ] = round(
                score,
                2
            )

    except (
        TypeError,
        ValueError
    ):

        result[
            "risk_score"
        ] = None

    # --------------------------------------------------------
    # Risk level
    # --------------------------------------------------------

    level = data.get(
        "risk_level"
    )

    if level is None:

        level = data.get(
            "overall_risk_level"
        )

    if level:

        result[
            "risk_level"
        ] = str(
            level
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    result[
        "risk_summary"
    ] = str(
        data.get(
            "risk_summary",
            data.get(
                "conclusion",
                ""
            )
        )
        or ""
    )

    # --------------------------------------------------------
    # Lists
    # --------------------------------------------------------

    for field in [
        "key_risks",
        "positive_factors",
        "missing_information",
        "recommended_actions"
    ]:

        value = data.get(
            field,
            []
        )

        if isinstance(
            value,
            list
        ):

            result[field] = value

    # Alternative action field
    if not result[
        "recommended_actions"
    ]:

        actions = data.get(
            "suggested_actions",
            []
        )

        if isinstance(
            actions,
            list
        ):

            result[
                "recommended_actions"
            ] = actions

    if raw_output:

        result[
            "raw"
        ] = raw_output

    return result


# ============================================================
# 20. FILE IO
# ============================================================

def read_input_text(
    path: Optional[str]
) -> str:

    if path:

        file_path = Path(
            path
        )

        if not file_path.exists():

            raise FileNotFoundError(
                f"Input file not found: "
                f"{file_path}"
            )

        if not file_path.is_file():

            raise ValueError(
                f"Input path is not a file: "
                f"{file_path}"
            )

        return file_path.read_text(
            encoding="utf-8",
            errors="replace"
        )

    if sys.stdin.isatty():

        raise ValueError(
            "No input file supplied.\n"
            "Use:\n"
            "python wrapperlaw.py <bylaws.txt>\n"
            "or:\n"
            "python wrapperlaw.py --input <bylaws.txt>"
        )

    return sys.stdin.read()


def load_json(
    path: str
) -> Dict[str, Any]:

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(
            f
        )


def save_json(
    path: str,
    obj: Any
) -> None:

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False
        )

        f.write(
            "\n"
        )


# ============================================================
# 21. MAIN WRAPPER
# ============================================================

def run_bylaws_wrapper(
    text: Optional[str] = None,
    input_path: Optional[str] = None,
    extracted_json_path: Optional[str] = None,
    out_prefix: str = "assoc_extract",
    save_artifacts: bool = False,
    pdf_path=None,
    session_id=None,
    screenshot_dir=None
) -> Dict[str, Any]:

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BYLAWS WRAPPER STARTING"
    )

    print(
        "=" * 70
    )

    # ========================================================
    # CASE 1:
    # EXISTING JSON
    # ========================================================

    if extracted_json_path:

        print(
            "Using existing extracted JSON."
        )

        extract = load_json(
            extracted_json_path
        )

        extract = ensure_schema(
            extract
        )

        # ----------------------------------------------------
        # If original text was supplied, validate it.
        # ----------------------------------------------------

        if text:

            try:

                extract = (
                    validate_extraction_against_text(
                        extract=extract,
                        text=text
                    )
                )

            except Exception as e:

                print(
                    "[VALIDATION] Existing JSON "
                    f"validation failed: {e}"
                )

        # ----------------------------------------------------
        # Python score
        # ----------------------------------------------------

        safety_score, level, breakdown = (
            compute_association_risk_score(
                extract
            )
        )

        risk_score = (
            risk_score_from_safety(
                safety_score
            )
        )

        # ----------------------------------------------------
        # Gemini
        # ----------------------------------------------------

        ai_analysis = {
            "risk_score": None,
            "risk_level": "UNKNOWN",
            "risk_summary": "",
            "key_risks": [],
            "positive_factors": [],
            "missing_information": [],
            "recommended_actions": []
        }

        try:
            # ------------------------------------------------
            # CLAUDE
            # ------------------------------------------------

            if AI_PROVIDER == "claude":

                raw_ai = call_claude(
                    RISK_PROMPT,
                    extract,
                    safety_score,
                    risk_score
                )

                ai_analysis = normalize_ai_risk(
                    extract_json_object(
                        raw_ai
                    ),
                    raw_output=raw_ai
                )
        except Exception as e:

            print(
                f"[AI] Risk analysis failed: {e}"
            )

            ai_analysis[
                "error"
            ] = str(
                e
            )

        return {

            "module": "bylaws",

            "document_type": "BYLAWS",

            "raw_output": None,

            "extracted": extract,

            "python_score": {

                "safety_score": safety_score,

                "risk_score": risk_score,

                "risk_level": level,

                "breakdown": breakdown
            },

            "ai_provider": AI_PROVIDER,

            "ai_analysis": ai_analysis,

            "extracted_json_path": (
                extracted_json_path
            )
        }

    # ========================================================
    # READ INPUT
    # ========================================================

    if text is None:

        text = read_input_text(
            input_path
        )

    text = (
        text or ""
    ).strip()

    if not text:

        raise ValueError(
            "No input text provided."
        )

    # ========================================================
    # DOCUMENT CHUNKING
    #
    # IMPORTANT:
    #
    # THIS IS THE ONLY CHUNKING OPERATION.
    #
    # We call call_qwen_chunk() directly below.
    #
    # We DO NOT call call_qwen_extraction() from here.
    # ========================================================

    chunks = split_document(
        text,
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP
    )


    if not chunks:

        raise ValueError(
            "Document produced zero chunks."
        )

    # ========================================================
    # QWEN EXTRACTION
    # ========================================================

    chunk_results = []

    raw_outputs = []

    for i, chunk in enumerate(
        chunks,
        start=1
    ):

        try:

            raw = call_qwen_chunk(
                prompt=EXTRACTION_PROMPT,
                chunk=chunk,
                chunk_number=i,
                total_chunks=len(chunks)
            )

            # ------------------------------------------------
            # Store raw Qwen output
            # ------------------------------------------------

            raw_outputs.append(
                json.dumps(
                    raw,
                    indent=2,
                    ensure_ascii=False
                )
                if isinstance(
                    raw,
                    dict
                )
                else str(raw)
            )

            # ------------------------------------------------
            # Handle dict
            # ------------------------------------------------

            if isinstance(
                raw,
                dict
            ):

                extract_chunk = raw

            # ------------------------------------------------
            # Handle JSON string
            # ------------------------------------------------

            elif isinstance(
                raw,
                str
            ):

                extract_chunk = (
                    extract_json_object(
                        raw
                    )
                )

            else:

                raise ValueError(
                    "Qwen returned unsupported "
                    f"type: {type(raw).__name__}"
                )

            # ------------------------------------------------
            # Unwrap:
            #
            # {
            #   "facts": {...}
            # }
            # ------------------------------------------------

            if (
                isinstance(
                    extract_chunk,
                    dict
                )
                and isinstance(
                    extract_chunk.get(
                        "facts"
                    ),
                    dict
                )
            ):

                extract_chunk = (
                    extract_chunk[
                        "facts"
                    ]
                )

            # ------------------------------------------------
            # Schema
            # ------------------------------------------------

            extract_chunk = (
                ensure_schema(
                    extract_chunk
                )
            )

            chunk_results.append(
                extract_chunk
            )

            print(
                f"Chunk {i} extraction successful."
            )

        except Exception as e:

            print(
                f"Chunk {i} extraction error: "
                f"{e}"
            )

            continue

        if i < len(chunks):

            time.sleep(
                0.5
            )

    # ========================================================
    # SUCCESS CHECK
    # ========================================================

    if not chunk_results:

        raise ValueError(
            "No valid Qwen extraction was obtained "
            "from any chunk."
        )

    # ========================================================
    # MERGE
    # ========================================================


    extract = merge_chunk_results(
        chunk_results
    )

    extract = ensure_schema(
        extract
    )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    extract[
        "confidence"
    ] = calculate_final_confidence(
        chunk_results
    )

    

    # ========================================================
    # FULL DOCUMENT EVIDENCE VALIDATION
    # ========================================================


    try:

        extract = (
            validate_extraction_against_text(
                extract=extract,
                text=text
            )
        )

    except Exception as e:

        print(
            "[VALIDATION] Failed: "
            f"{e}"
        )

    # ========================================================
    # FINAL SCHEMA
    # ========================================================

    extract = ensure_schema(
        extract
    )

    # Preserve calculated confidence
    extract[
        "confidence"
    ] = calculate_final_confidence(
        chunk_results
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "FINAL EXTRACTED BYLAWS DATA"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            extract,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        f"\nSuccessfully extracted "
        f"{len(chunk_results)}/{len(chunks)} chunks."
    )

    print(
        f"Final confidence: "
        f"{extract.get('confidence', 0.0)}"
    )

    # ========================================================
    # SAVE EXTRACTION
    # ========================================================

    json_path = None

    raw_path = None

    score_path = None

    if save_artifacts:

        json_path = (
            f"{out_prefix}.json"
        )

        save_json(
            json_path,
            extract
        )

        raw_path = (
            f"{out_prefix}.raw.txt"
        )

        with open(
            raw_path,
            "w",
            encoding="utf-8"
        ) as f:

            for index, raw in enumerate(
                raw_outputs,
                start=1
            ):

                f.write(
                    "\n"
                    + "=" * 70
                    + "\n"
                )

                f.write(
                    f"CHUNK {index}\n"
                )

                f.write(
                    "=" * 70
                    + "\n"
                )

                f.write(
                    raw
                )

                f.write(
                    "\n"
                )

        print(
            f"Extracted JSON saved: "
            f"{json_path}"
        )

        print(
            f"Raw Qwen output saved: "
            f"{raw_path}"
        )

    # ========================================================
    # PYTHON RISK SCORE
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "PYTHON DETERMINISTIC RISK SCORE"
    )

    print(
        "=" * 70
    )

    safety_score, level, breakdown = (
        compute_association_risk_score(
            extract
        )
    )

    risk_score = (
        risk_score_from_safety(
            safety_score
        )
    )

    print(
        f"Safety Score : "
        f"{safety_score}/100"
    )

    print(
        f"Risk Score   : "
        f"{risk_score}/100"
    )

    print(
        f"Risk Level   : "
        f"{level}"
    )

    print(
        json.dumps(
            breakdown,
            indent=2,
            ensure_ascii=False
        )
    )

    # ========================================================
    # SAVE SCORE
    # ========================================================

    if save_artifacts:

        score_path = (
            f"{out_prefix}.score.json"
        )

        save_json(
            score_path,
            {
                "safety_score": safety_score,

                "risk_score": risk_score,

                "risk_level": level,

                **breakdown
            }
        )

        print(
            f"Score saved: "
            f"{score_path}"
        )

    # ========================================================
    # GEMINI / AI RISK ANALYSIS
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        f"AI RISK ANALYSIS "
        f"[{AI_PROVIDER.upper()}]"
    )

    print(
        "=" * 70
    )

    ai_analysis = {

        "risk_score": None,

        "risk_level": "UNKNOWN",

        "risk_summary": "",

        "key_risks": [],

        "positive_factors": [],

        "missing_information": [],

        "recommended_actions": []
    }

    ai_raw = None

    try:

        # ====================================================
        # GEMINI ACTIVE
        # ====================================================

        # ====================================================
        # CLAUDE
        # ====================================================

        if AI_PROVIDER == "claude":

            ai_raw = call_claude(
                RISK_PROMPT,
                extract,
                safety_score,
                risk_score
            )

            print(
                "\nRAW CLAUDE RISK OUTPUT:"
            )

            print(
                ai_raw
            )

            try:

                parsed_ai = (
                    extract_json_object(
                        ai_raw
                    )
                )

            except Exception:

                parsed_ai = {}

            ai_analysis = normalize_ai_risk(
                parsed_ai,
                raw_output=ai_raw
            )

        else:

            raise ValueError(
                "Unsupported BYLAWS_AI_PROVIDER: "
                f"{AI_PROVIDER}. "
                "Use 'gemini'."
            )

    except Exception as e:

        print(
            f"[AI] Risk analysis failed: "
            f"{e}"
        )

        ai_analysis = {

            "risk_score": None,

            "risk_level": "UNKNOWN",

            "risk_summary": "",

            "key_risks": [],

            "positive_factors": [],

            "missing_information": [],

            "recommended_actions": [],

            "error": str(e)
        }

    # ========================================================
    # FINAL RESULT
    # ========================================================

    artifacts = {

        "raw_output_path": raw_path,

        "extract_json_path": json_path,

        "score_json_path": score_path
    }

    if not save_artifacts:

        artifacts = None

    result = {

        "module": "bylaws",

        "document_type": "BYLAWS",

        "raw_output": (
            "\n\n".join(
                raw_outputs
            )
        ),

        "extracted": extract,

        "python_score": {

            "safety_score": safety_score,

            "risk_score": risk_score,

            "risk_level": level,

            "breakdown": breakdown
        },

        "ai_provider": AI_PROVIDER,

        "ai_analysis": ai_analysis,

        "extracted_json_path": json_path,

        "artifacts": artifacts
    }

    # ========================================================
    # COMPLETE
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BYLAWS WRAPPER COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"Python Safety Score : "
        f"{safety_score}/100"
    )

    print(
        f"Python Risk Score   : "
        f"{risk_score}/100"
    )

    print(
        f"Python Risk Level   : "
        f"{level}"
    )

    print(
        f"AI Provider         : "
        f"{AI_PROVIDER}"
    )

    print(
        f"AI Risk Score       : "
        f"{ai_analysis.get('risk_score')}"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

    return result


# ============================================================
# 22. COMMAND LINE
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "KAOA Association Bye-laws "
            "Qwen Extraction and Risk Wrapper"
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help=(
            "Path to bylaws text file "
            "(positional)"
        )
    )

    parser.add_argument(
        "--input",
        dest="input_file",
        default=None,
        help=(
            "Path to bylaws text file"
        )
    )

    parser.add_argument(
        "--output",
        default="assoc_extract",
        help=(
            "Output prefix"
        )
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "Save extracted JSON, "
            "raw Qwen output and score"
        )
    )

    parser.add_argument(
        "--json",
        dest="extracted_json_path",
        default=None,
        help=(
            "Use an already extracted JSON "
            "instead of running Qwen"
        )
    )

    args = parser.parse_args()

    input_path = (
        args.input_file
        or args.input
    )

    result = run_bylaws_wrapper(

        input_path=input_path,

        extracted_json_path=(
            args.extracted_json_path
        ),

        out_prefix=args.output,

        save_artifacts=args.save
    )

    print(
        "\nFINAL RESULT:"
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )