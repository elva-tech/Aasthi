#!/usr/bin/env python3

"""
Parking Risk Scoring

PDF
 ↓
Relevant page detection
 ↓
PDF page images
 ↓
Qwen2.5-VL:7B image extraction
 ↓
Merge parking evidence
 ↓
Python deterministic score
 ↓
Claude rubric score
 ↓
70% Python + 30% Claude
 ↓
Final risk score
"""

from __future__ import annotations

import base64
import datetime
import json
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import os
import fitz
from PIL import Image
from io import BytesIO

from google import genai
from pydantic import BaseModel, Field
import ollama
from openai import OpenAI
from anthropic import Anthropic
from dotenv import load_dotenv
import pytesseract

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

MODEL_EXTRACT = "qwen2.5vl:7b"
MODEL_SCORE = "claude-opus-4-7"


RENDER_ZOOM = 8.0
AGREEMENT_MAX_PAGES = None

WEIGHT_DETERMINISTIC = 0.7
WEIGHT_LLM = 0.3


# ============================================================
# QWEN CLIENT
# ============================================================

qwen_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


# ============================================================
# CLAUDE CLIENT
# ============================================================

def get_claude_client():

    key = os.getenv(
        "ANTHROPIC_API_KEY",
        ""
    ).strip()

    if not key:
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY"
        )

    return Anthropic(
        api_key=key
    )

# ============================================================
# IMAGE → BASE64
# ============================================================

def image_to_base64(
    img: Image.Image
) -> str:

    buffer = BytesIO()

    img.convert("RGB").save(
        buffer,
        format="JPEG",
        quality=85
    )

    return base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

def resize_for_qwen(
    image: Image.Image,
    max_dimension: int = 4500
) -> Image.Image:

    image = image.convert("RGB")

    width, height = image.size

    if max(width, height) <= max_dimension:
        return image

    scale = max_dimension / max(width, height)

    new_size = (
        int(width * scale),
        int(height * scale)
    )

    return image.resize(
        new_size,
        Image.Resampling.LANCZOS
    )
# ============================================================
# PDF → IMAGES
# ============================================================

def render_pdf_pages(
    pdf_path: str,
    zoom: float = 8.0,
    max_pages: Optional[int] = None
) -> List[Image.Image]:

    doc = fitz.open(pdf_path)

    page_count = doc.page_count

    if max_pages is not None:
        page_count = min(
            page_count,
            max_pages
        )

    images = []

    for i in range(page_count):

        page = doc.load_page(i)

        pix = page.get_pixmap(
            matrix=fitz.Matrix(
                zoom,
                zoom
            ),
            alpha=False
        )

        img = Image.frombytes(
            "RGB",
            [
                pix.width,
                pix.height
            ],
            pix.samples
        )

        images.append(img)

    doc.close()

    return images


# ============================================================
# QWEN VISION JSON EXTRACTION
# ============================================================

def qwen_vision_json_extract(
    prompt: str,
    image: Image.Image
) -> Dict[str, Any]:

    # Resize large images before sending to Qwen
    image = resize_for_qwen(
        image,
        max_dimension=4500
    )

    buffer = BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=90,
        optimize=True
    )

    image_bytes = buffer.getvalue()

    print(
        f"[QWEN] Using {MODEL_EXTRACT} "
        f"with context size 8192"
    )

    response = ollama.chat(
        model=MODEL_EXTRACT,

        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [
                    image_bytes
                ]
            }
        ],

        options={
            "num_ctx": 8192,
            "temperature": 0,
            "num_predict": 700
        },

        format="json"
    )

    raw = response["message"]["content"].strip()

    raw = (
        raw
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    try:
        return json.loads(raw)

    except json.JSONDecodeError as e:

        raise RuntimeError(
            "Qwen returned invalid JSON: "
            f"{e}\n"
            f"Raw response:\n{raw}"
        )
# ============================================================
# PARKING PAGE DETECTION
# ============================================================

def find_parking_page_numbers(
    pdf_path: str
) -> List[int]:

    doc = fitz.open(
        pdf_path
    )

    keywords = [
        "parking",
        "car parking",
        "slot",
        "basement",
        "vehicle",
        "car park",
        "exclusive parking"
    ]

    selected_pages = []

    for page_no in range(
        len(doc)
    ):

        page = doc.load_page(
            page_no
        )

        text = (
            page.get_text(
                "text"
            )
            or ""
        ).lower()

        if any(
            keyword in text
            for keyword in keywords
        ):

            selected_pages.append(
                page_no
            )

    doc.close()

    return selected_pages


# ============================================================
# SCHEMAS
# ============================================================

class AgreementParkingExtract(BaseModel):
    exclusive_right: bool = False

    # True only if an actual parking slot identifier is visible
    slot_number_present: bool = False
    slot_number_value: Optional[str] = None

    # True if the page contains a parking-space reference,
    # even when the actual slot number is blank
    parking_slot_reference_present: bool = False

    basement_or_level_present: bool = False
    basement_or_level_value: Optional[str] = None

    limited_common_area_defined: bool = False

    usage_restrictions_present: bool = False

    supporting_quotes: List[str] = Field(
        default_factory=list
    )
class SitePlanParkingExtract(
    BaseModel
):

    has_parking_area_labels: bool = False

    has_entry_exit_or_ramps: bool = False

    has_slot_numbering: bool = False

    key_labels_found: List[str] = Field(
        default_factory=list
    )

    notes: List[str] = Field(
        default_factory=list
    )

    parking_evidence: List[str] = Field(
        default_factory=list
    )


class CombinedExtract(
    BaseModel
):

    agreement: AgreementParkingExtract

    siteplan: SitePlanParkingExtract


class LLMStableScore(
    BaseModel
):

    llm_score_0_100: int

    llm_interpretation: str

    llm_factor_scores_1to5: Dict[
        str,
        int
    ]

    llm_reasoning_bullets: List[str] = Field(
        default_factory=list
    )


AGREEMENT_PROMPT = """
You are a Senior Real Estate Agreement Examiner
and Parking Rights Verification Specialist.

You are analyzing ONE IMAGE PAGE from an Indian Agreement to Sell.

READ THE SUPPLIED IMAGE DIRECTLY.

Your ONLY task is to extract PARKING-RELATED information
that is VISIBLY PRESENT on THIS IMAGE.

Do NOT use external information.
Do NOT use prior pages.
Do NOT use information from other images.
Do NOT infer or guess.
Do NOT assume information that is not visible.

============================================================
OBJECTIVE
============================================================

Extract ONLY:

1. Exclusive parking right
2. Parking slot reference
3. Actual parking slot number
4. Basement / floor / parking level
5. Limited Common Area definition
6. Parking usage restrictions
7. Supporting evidence

============================================================
1. EXCLUSIVE PARKING RIGHT
============================================================

Set "exclusive_right" to TRUE when the image explicitly
establishes that the Purchaser has an exclusive, specifically
allotted, specifically acquired, or earmarked parking right/use.

Strong positive phrases include:

- "exclusive right"
- "exclusive use"
- "exclusively use"
- "entitled to exclusively use"
- "earmarked for the exclusive use"
- "specifically allotted to the Purchaser"
- "specifically acquired by the Purchaser"
- "parking space specifically allotted"
- "parking space specifically acquired"
- "parking space/area specifically acquired by the Purchaser"
- "earmarked for the exclusive use of the Purchaser"

IMPORTANT:

If the image visibly says:

"The Purchaser shall be entitled to exclusively use
the parking space..."

then:

"exclusive_right": true

If the image visibly says:

"parking space/area specifically acquired by the Purchaser
and earmarked for the exclusive use of the Purchaser"

then:

"exclusive_right": true

DO NOT require an actual parking slot number.

These are independent facts:

"exclusive_right": true
"slot_number_present": false

is completely valid.

Return false ONLY when the supplied image contains
NO explicit evidence of exclusive, specifically allotted,
specifically acquired, or earmarked parking use/right.

Do NOT infer exclusive rights merely because the image mentions:

- parking;
- car parking;
- parking area;
- parking facility;
- parking space;
- parking amenity;
- parking availability;
- general parking provisions.

============================================================
2. PARKING SLOT REFERENCE
============================================================

Set "parking_slot_reference_present" to TRUE when the image
explicitly refers to a parking slot or parking space assigned,
allocated, reserved, acquired, or intended for the Purchaser,
EVEN IF THE ACTUAL SLOT NUMBER IS BLANK.

Examples:

"car parking slot No. __"
"Parking Slot No. _____"
"one car parking space"
"parking space specifically allotted to the Purchaser"
"parking space specifically acquired by the Purchaser"
"parking space earmarked for the exclusive use of the Purchaser"

IMPORTANT:

A parking-slot reference and an actual slot number are DIFFERENT.

For example:

"car parking slot No. __ in the _____ basement"

must produce:

"parking_slot_reference_present": true
"slot_number_present": false
"slot_number_value": null

Do NOT require a filled number for
"parking_slot_reference_present".

============================================================
3. ACTUAL PARKING SLOT NUMBER
============================================================

Set "slot_number_present" to TRUE ONLY when an ACTUAL
parking slot identifier/number is visibly readable.

Valid examples:

- "P-12"
- "Parking Slot No. 25"
- "Slot No. A-14"
- "Car Park 32"
- "Parking 07"

Do NOT treat these as parking slot numbers:

- apartment number;
- flat number;
- unit number;
- building number;
- wing number;
- villa number;
- survey number;
- plot number;
- road number;
- page number.

A blank placeholder is NOT an actual slot number.

For:

"Slot No. ______"

return:

"slot_number_present": false
"slot_number_value": null

If an actual slot number is visible:

"slot_number_present": true

and return the exact visible identifier in:

"slot_number_value"

DO NOT invent or infer a slot number.

============================================================
4. BASEMENT / FLOOR / PARKING LEVEL
============================================================

Set "basement_or_level_present" to TRUE when the image
explicitly states where the parking space is located.

Look for:

- basement
- lower basement
- upper basement
- basement level
- surface level
- ground level
- stilt level
- parking level
- podium level
- basement/surface level
- basement or surface level
- basement or at the surface level

Example:

"The Purchaser shall be entitled to exclusively use
the parking space specifically allotted to the Purchaser
either in the basement or at the surface level..."

means:

"basement_or_level_present": true

Return the exact visible wording in:

"basement_or_level_value"

Do NOT normalize or rewrite it.

============================================================
5. LIMITED COMMON AREA
============================================================

Set "limited_common_area_defined" to TRUE when the image
contains an explicit legal definition or classification
connecting parking with "Limited Common Area".

This includes wording such as:

"Limited Common Area shall mean the Purchaser Car Parking Area..."

or:

"Limited Common Area" includes the Purchaser Car Parking Area.

IMPORTANT:

The wording does NOT have to literally say:

"the parking area is a Limited Common Area."

If the image explicitly defines "Limited Common Area"
as including the Purchaser Car Parking Area, return TRUE.

For example:

"Limited Common Area shall mean the Purchaser Car Parking Area
and such other areas from and out of the Common Areas of the
Project, which are allotted for the exclusive use by the
apartment owners..."

must produce:

"limited_common_area_defined": true

Do NOT infer this merely because:

- parking is exclusive;
- parking is allotted;
- parking is attached to an apartment;
- parking is in a basement.

There must be explicit legal wording connecting
parking with Limited Common Area.

============================================================
6. PARKING USAGE RESTRICTIONS
============================================================

Set "usage_restrictions_present" to TRUE when the image
explicitly states ANY parking-related restriction,
prohibition, permitted use, or limitation.

Look for:

- parking only for cars;
- parking only for light motor vehicles;
- no storage;
- no disposal of old tyres;
- no accommodation for helpers;
- no accommodation for drivers;
- no commercial use;
- no use for goods/materials;
- no use of another owner's parking space;
- no encroachment into another parking space;
- parking only in the allotted space;
- parking only in the specifically acquired space;
- parking only in the earmarked space;
- restrictions on vehicle type;
- restrictions on obstruction;
- restrictions on alteration;
- restrictions on access/use of parking.

For example:

"only for the purpose of parking cars and light motor vehicles"

means:

"usage_restrictions_present": true

Do NOT infer restrictions that are not explicitly visible.

============================================================
7. SUPPORTING QUOTES
============================================================

Return up to 5 SHORT, EXACT quotations from THIS IMAGE.

Quotes must be copied from visible text.

Prioritize:

1. Exclusive parking right
2. Limited Common Area definition
3. Parking allocation/reference
4. Actual slot number
5. Basement / parking level
6. Parking restrictions

Examples of useful evidence:

- exclusive-use wording;
- specifically allotted wording;
- specifically acquired wording;
- Limited Common Area definition;
- parking slot reference;
- parking level;
- parking-only restriction;
- storage/tyre/helper/driver restrictions.

DO NOT:

- invent quotations;
- paraphrase quotations;
- combine separate sentences into a new quotation;
- quote unrelated agreement text;
- use information from another page.

Maximum:

5 quotations.

If there is no relevant parking evidence:

"supporting_quotes": []

============================================================
IMPORTANT IMAGE READING RULES
============================================================

Inspect the ENTIRE supplied image before deciding the values.

Parking information may appear:

- inside a paragraph;
- inside a definition;
- inside a schedule;
- inside a table;
- in a heading;
- near the top of the page;
- near the bottom of the page;
- in a clause containing multiple legal concepts.

Do NOT stop after finding the first parking sentence.

Search the entire image for ALL relevant parking evidence.

However, output ONLY the requested parking fields.

Ignore unrelated:

- sale consideration;
- apartment specifications;
- general property details;
- survey numbers;
- general building details;
- unrelated legal clauses.

============================================================
PAGE-SPECIFIC RULE
============================================================

You are analyzing ONLY THIS IMAGE.

Do NOT use information from other pages.

If another page contains an actual parking slot number
but this image contains only:

"Slot No. ____"

then this page must return:

"slot_number_present": false
"slot_number_value": null

If another page establishes exclusive parking rights,
do NOT mark "exclusive_right": true on THIS page unless
this image itself contains explicit supporting evidence.

============================================================
EVIDENCE CONSISTENCY RULE
============================================================

The boolean fields MUST agree with the visible evidence
you place in "supporting_quotes".

If a supporting quote explicitly establishes an
exclusive parking right, then:

"exclusive_right": true

If a supporting quote explicitly defines Limited Common Area
in connection with parking, then:

"limited_common_area_defined": true

If a supporting quote explicitly states a parking restriction,
then:

"usage_restrictions_present": true

If a supporting quote contains a parking-slot reference
but the number is blank, then:

"parking_slot_reference_present": true
"slot_number_present": false

Do NOT return a contradictory combination.

============================================================
NO INFERENCE RULE
============================================================

The following alone are NOT sufficient for exclusive_right:

- "parking facility"
- "car parking"
- "parking area"
- "parking space"
- "parking shall be provided"
- "parking is available"
- "Purchaser shall park the vehicle"
- "parking charges"
- "parking regulations"

Exclusive_right requires explicit wording establishing
exclusive, specifically allotted, specifically acquired,
or earmarked parking use/right.

============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON.

Do NOT return:

- markdown;
- ```json;
- explanations;
- comments;
- additional keys.

Use EXACTLY this structure:

{
  "exclusive_right": false,
  "slot_number_present": false,
  "slot_number_value": null,
  "parking_slot_reference_present": false,
  "basement_or_level_present": false,
  "basement_or_level_value": null,
  "limited_common_area_defined": false,
  "usage_restrictions_present": false,
  "supporting_quotes": []
}

Every value MUST be based ONLY on information visibly
present in the supplied image.

Missing information:

- missing boolean -> false
- missing slot number -> null
- missing parking level -> null
- missing quotations -> []

Do not guess.
Do not infer.
Do not use other pages.
"""
# ============================================================
# SITE PLAN PROMPT
# ============================================================
SITEPLAN_PROMPT = """
You are a Senior Real Estate Parking Plan Examiner.

You are analyzing ONE IMAGE from an Indian real-estate
site plan / parking plan.

READ THE IMAGE DIRECTLY AND CAREFULLY.

Your ONLY task is to identify PARKING-RELATED information.

============================================================
VERY IMPORTANT
============================================================

This is a dense architectural drawing.

The parking information may appear as a TABLE or TEXT BLOCK,
not only as a label on the site layout.

You MUST inspect:

1. headings
2. tables
3. numeric parking statements
4. basement parking statements
5. car counts
6. parking provision statements
7. parking labels
8. entry / exit / ramp labels

DO NOT assume that parking information must look like
individual parking rectangles or numbered slots.

A clearly readable section titled:

"PARKING"

IS sufficient evidence that parking information exists.

============================================================
WHAT COUNTS AS PARKING EVIDENCE
============================================================

Parking evidence includes ANY clearly readable:

- PARKING
- CAR PARKING
- CAR PARK
- VISITOR PARKING
- PARKING AREA
- PARKING PROVISION
- BASEMENT PARKING
- LOWER BASEMENT
- UPPER BASEMENT
- CAR COUNT related to parking
- CARS REQUIRED
- CARS PROVIDED
- PARKING REQUIREMENT
- PARKING STATEMENT
- PARKING SLOT
- RAMP
- ENTRY
- EXIT

A parking table containing statements such as:

"Cars Required"
"Total Cars Required"
"Net Total Cars Required"
"Total Cars Provided"

MUST be treated as parking evidence.

============================================================
1. PARKING AREA LABELS
============================================================

Set:

"has_parking_area_labels": true

when ANY clearly readable parking-related heading,
label, table heading, or statement is visible.

For example:

"PARKING"

"CAR PARKING"

"VISITOR PARKING"

"BASEMENT PARKING"

"Parking Statement"

"Total Cars Required"

"Total Cars Provided"

Do NOT require an individual parking slot number.

============================================================
2. ENTRY / EXIT / RAMPS
============================================================

Set:

"has_entry_exit_or_ramps": true

ONLY if clearly readable parking-related:

- ENTRY
- EXIT
- VEHICLE ENTRY
- VEHICLE EXIT
- RAMP
- UP RAMP
- DOWN RAMP
- BASEMENT RAMP

is visible.

Do not infer this from roads.

============================================================
3. SLOT NUMBERING
============================================================

Set:

"has_slot_numbering": true

ONLY when actual parking slot identifiers are visibly
readable.

Examples:

- P-01
- P1
- CP-01
- SLOT 01
- PARKING SLOT 12

Do NOT treat apartment, villa, building, wing,
survey or plot numbers as parking slots.

If parking exists but individual slot numbers are not visible:

"has_slot_numbering": false

============================================================
4. KEY LABELS
============================================================

Return ONLY parking-related labels.

Maximum 10.

Examples:

[
  "PARKING",
  "VISITOR PARKING",
  "LOWER BASEMENT",
  "UPPER BASEMENT",
  "CARS REQUIRED",
  "TOTAL CARS PROVIDED"
]

Do NOT return:

- Building 01
- Building 02
- Villa A
- Wing A
- Block B
- apartment numbers
- survey numbers

============================================================
5. PARKING NOTES
============================================================

Use notes for clearly visible parking facts.

Maximum 10 notes.

IMPORTANT:

If the image contains readable parking counts,
extract them.

Examples:

"Total cars required = 758"

"Cars required for previous sanctioned buildings = 3942"

"Net total cars required = 4700"

"Total cars provided = 5599"

"Basement Floor Club House = 78 cars"

"Villas GF = 542 cars"

Only report numbers that are actually visible.

============================================================
6. PARKING EVIDENCE
============================================================

Return short exact quotations or statements copied from
the visible parking section.

Maximum 10.

Examples:

"PARKING"

"Total Cars Required = 542 + 54 + 162 = 758 Cars"

"Net Total cars Required = 758 + 3,942 = 4,700 cars"

"Total Cars Provided = 5,599 Cars"

Do NOT invent quotations.

============================================================
IMPORTANT IMAGE READING RULE
============================================================

Do NOT stop after looking at the site layout.

Inspect the ENTIRE IMAGE.

In particular, carefully inspect any:

- large table
- text block
- heading
- parking statement
- basement statement
- numeric car-count section

Parking information may be much clearer in a table than
in the graphical site layout.

============================================================
NO INFERENCE
============================================================

Do not infer:

- parking slots
- parking numbers
- ramps
- entry
- exit

unless visibly readable.

However, if a clearly readable "PARKING" heading or
parking table exists, mark:

"has_parking_area_labels": true

============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

Use EXACTLY:

{
  "has_parking_area_labels": false,
  "has_entry_exit_or_ramps": false,
  "has_slot_numbering": false,
  "key_labels_found": [],
  "notes": [],
  "parking_evidence": []
}
"""
# ============================================================
# CLAUDE SCORING PROMPT
# ============================================================

LLM_RUBRIC_PROMPT = """
You are a Senior Property Due Diligence Consultant,
Parking Allocation Auditor,
and Real Estate Documentation Specialist.

A prospective property buyer wants to determine whether
parking documentation clearly establishes:

- parking allocation
- parking location
- exclusive rights
- site-plan corroboration
- legal definition

Evaluate ONLY the supplied extracted evidence.

Do NOT invent facts.

If information is missing or unclear,
give the WORSE score.

SCORING

1 = Excellent / very clear
2 = Good
3 = Moderate
4 = Weak
5 = Very poor / missing

FACTORS

slot_identified_1to5

1 = actual parking slot clearly identified
5 = no identifiable slot

location_clarity_1to5

1 = exact parking location clearly identified
5 = location not identifiable

exclusive_right_1to5

1 = exclusive parking right clearly granted
5 = exclusive right absent or unclear

plan_corroboration_1to5

1 = site plan clearly corroborates parking
5 = no corroborating evidence

legal_definition_1to5

1 = parking legal status clearly defined
5 = legal status not defined

Use ONLY the supplied extracted data.

OUTPUT ONLY VALID JSON:

{
  "slot_identified_1to5": 1,
  "location_clarity_1to5": 1,
  "exclusive_right_1to5": 1,
  "plan_corroboration_1to5": 1,
  "legal_definition_1to5": 1,
  "evidence_bullets": []
}
"""


# ============================================================
# DETERMINISTIC SCORE
# ============================================================

@dataclass
class RiskBreakdown:

    legal_allocation_certainty: int

    layout_planning_evidence: int

    documentation_strength: int

    operational_dispute_risk: int

    total_score: int

    interpretation: str


_SLOT_ID_RE = re.compile(
    r"\b([A-Z]{0,3}\s*[-]?\s*\d{1,4})\b",
    re.IGNORECASE
)


def has_real_slot_id(
    slot_value: Optional[str]
) -> bool:

    if slot_value is None:
        return False

    s = str(
        slot_value
    ).strip()

    if not s:
        return False

    if s.upper() in {
        "__",
        "_",
        "-",
        "NA",
        "N/A",
        "NONE",
        "NULL"
    }:
        return False

    if "_" in s:
        return False

    if not any(
        ch.isdigit()
        for ch in s
    ):
        return False

    return bool(
        _SLOT_ID_RE.search(s)
    )


def interp_from_score(
    score: int
) -> str:

    if score >= 85:
        return "Very Low Risk"

    if score >= 70:
        return "Low–Moderate Risk"

    if score >= 50:
        return "Moderate Risk"

    return "High Risk"


def compute_risk_score(
    ag: AgreementParkingExtract,
    sp: SitePlanParkingExtract
) -> RiskBreakdown:

    has_real_slot = has_real_slot_id(
        ag.slot_number_value
    )

    legal = 0

    legal += (
        10
        if ag.exclusive_right
        else 0
    )

    legal += (
        15
        if has_real_slot
        else 0
    )

    legal += (
        10
        if ag.basement_or_level_present
        else 0
    )

    legal += (
        5
        if ag.limited_common_area_defined
        else 0
    )

    if (
        ag.slot_number_present
        and not has_real_slot
    ):

        legal = max(
            0,
            legal - 10
        )

    legal = min(
        40,
        legal
    )

    layout = 0

    layout += (
        15
        if sp.has_parking_area_labels
        else 0
    )

    layout += (
        10
        if sp.has_entry_exit_or_ramps
        else 0
    )

    layout = min(
        25,
        layout
    )

    docs = 0

    docs += (
        10
        if (
            ag.exclusive_right
            or
            ag.limited_common_area_defined
        )
        else 0
    )

    docs += (
        5
        if ag.usage_restrictions_present
        else 0
    )

    docs += (
        5
        if (
            sp.has_parking_area_labels
            or
            sp.has_entry_exit_or_ramps
        )
        else 0
    )

    docs = min(
        20,
        docs
    )

    ops = 0

    ops += (
        7
        if ag.exclusive_right
        else 0
    )

    ops += (
        5
        if ag.usage_restrictions_present
        else 0
    )

    ops += (
        3
        if has_real_slot
        else 0
    )

    penalty = (
        3
        if not (
            sp.has_parking_area_labels
            or
            sp.has_entry_exit_or_ramps
        )
        else 0
    )

    ops = max(
        0,
        min(
            15,
            ops - penalty
        )
    )

    total = int(
        max(
            0,
            min(
                100,
                legal
                + layout
                + docs
                + ops
            )
        )
    )

    return RiskBreakdown(
        legal_allocation_certainty=legal,
        layout_planning_evidence=layout,
        documentation_strength=docs,
        operational_dispute_risk=ops,
        total_score=total,
        interpretation=interp_from_score(
            total
        )
    )


# ============================================================
# RISK SCORE
# ============================================================

def risk_score_from_safety(
    safety_score: Any
) -> Optional[int]:

    try:

        score = int(
            float(
                safety_score
            )
        )

    except Exception:

        return None

    score = max(
        0,
        min(
            100,
            score
        )
    )

    return 100 - score


# ============================================================
# LLM FACTOR WEIGHTS
# ============================================================

WEIGHTS_1TO5 = {

    "slot_identified_1to5":
        0.35,

    "location_clarity_1to5":
        0.20,

    "exclusive_right_1to5":
        0.20,

    "plan_corroboration_1to5":
        0.15,

    "legal_definition_1to5":
        0.10,
}


def llm_factors_to_score_0_100(
    factors: Dict[str, int]
) -> int:

    weighted = 0.0

    for key, weight in (
        WEIGHTS_1TO5.items()
    ):

        value = int(
            factors.get(
                key,
                3
            )
        )

        value = max(
            1,
            min(
                5,
                value
            )
        )

        weighted += (
            value
            * weight
        )

    score = int(
        round(
            (
                (
                    5.0
                    - weighted
                )
                / 4.0
            )
            * 100.0
        )
    )

    return max(
        0,
        min(
            100,
            score
        )
    )


# ============================================================
# CLAUDE LLM SCORING
# ============================================================

def claude_llm_stable_score(
    ag: AgreementParkingExtract,
    sp: SitePlanParkingExtract
) -> LLMStableScore:

    payload = {

        "agreement_extract":
            ag.model_dump(),

        "siteplan_extract":
            sp.model_dump()
    }

    prompt = (
        LLM_RUBRIC_PROMPT
        + "\n\nSUPPLIED EVIDENCE:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        )
    )

    client = get_claude_client()

    response = client.messages.create(

        model=MODEL_SCORE,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw = (
        response
        .content[0]
        .text
        .strip()
    )

    raw = (
        raw
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    try:

        data = json.loads(
            raw
        )

    except json.JSONDecodeError as e:

        raise RuntimeError(
            "Claude returned invalid JSON: "
            f"{e}\n"
            f"Raw response:\n{raw}"
        )

    factors = {}

    for key in (
        WEIGHTS_1TO5.keys()
    ):

        if key not in data:

            raise RuntimeError(
                f"Claude response missing '{key}'"
            )

        try:

            value = int(
                data[key]
            )

        except Exception:

            raise RuntimeError(
                f"Invalid value for '{key}'"
            )

        factors[key] = max(
            1,
            min(
                5,
                value
            )
        )

    bullets = data.get(
        "evidence_bullets",
        []
    )

    if not isinstance(
        bullets,
        list
    ):

        bullets = []

    bullets = [
        str(x)[:200]
        for x in bullets
    ][:6]

    llm_score = (
        llm_factors_to_score_0_100(
            factors
        )
    )

    return LLMStableScore(

        llm_score_0_100=
            llm_score,

        llm_interpretation=
            interp_from_score(
                llm_score
            ),

        llm_factor_scores_1to5=
            factors,

        llm_reasoning_bullets=
            bullets
    )


# ============================================================
# MERGE AGREEMENT EXTRACTIONS
# ============================================================
def normalize_agreement_evidence(
    data: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(data, dict):
        return data

    text = " ".join(
        str(q)
        for q in data.get(
            "supporting_quotes",
            []
        )
    ).lower()

    # --------------------------------------------------
    # Exclusive-right evidence
    # --------------------------------------------------

    exclusive_phrases = [
        "exclusively use",
        "exclusive use",
        "exclusive right",
        "earmarked for the exclusive use",
        "specifically allotted to the purchaser",
        "specifically acquired by the purchaser"
    ]

    if any(
        phrase in text
        for phrase in exclusive_phrases
    ):
        data["exclusive_right"] = True

    # --------------------------------------------------
    # Basement / level evidence
    # --------------------------------------------------

    level_phrases = [
        "basement",
        "surface level",
        "ground level",
        "parking level",
        "stilt level"
    ]

    if any(
        phrase in text
        for phrase in level_phrases
    ):
        data[
            "basement_or_level_present"
        ] = True

    # --------------------------------------------------
    # Limited Common Area evidence
    # --------------------------------------------------

    if (
        "limited common area" in text
        and (
            "parking" in text
            or "car parking" in text
        )
    ):
        data[
            "limited_common_area_defined"
        ] = True

    # --------------------------------------------------
    # Parking restriction evidence
    # --------------------------------------------------

    restriction_phrases = [
        "only for parking",
        "not be used for storage",
        "old tyres",
        "helpers",
        "drivers",
        "shall not have any right",
        "shall not",
        "only in the parking space"
    ]

    if any(
        phrase in text
        for phrase in restriction_phrases
    ):
        data[
            "usage_restrictions_present"
        ] = True

    return data

def merge_agreement_results(
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:

    merged = {
        "exclusive_right": False,

        "slot_number_present": False,
        "slot_number_value": None,

        "parking_slot_reference_present": False,

        "basement_or_level_present": False,
        "basement_or_level_value": None,

        "limited_common_area_defined": False,

        "usage_restrictions_present": False,

        "supporting_quotes": []
    }

    for data in results:

        if not isinstance(data, dict):
            continue

        # --------------------------------------------------
        # BOOLEAN FIELDS
        # TRUE ON ANY PAGE = TRUE IN MERGED RESULT
        # --------------------------------------------------

        merged["exclusive_right"] = (
            merged["exclusive_right"]
            or bool(data.get("exclusive_right", False))
        )

        merged["parking_slot_reference_present"] = (
            merged["parking_slot_reference_present"]
            or bool(
                data.get(
                    "parking_slot_reference_present",
                    False
                )
            )
        )

        merged["slot_number_present"] = (
            merged["slot_number_present"]
            or bool(
                data.get(
                    "slot_number_present",
                    False
                )
            )
        )

        merged["basement_or_level_present"] = (
            merged["basement_or_level_present"]
            or bool(
                data.get(
                    "basement_or_level_present",
                    False
                )
            )
        )

        merged["limited_common_area_defined"] = (
            merged["limited_common_area_defined"]
            or bool(
                data.get(
                    "limited_common_area_defined",
                    False
                )
            )
        )

        merged["usage_restrictions_present"] = (
            merged["usage_restrictions_present"]
            or bool(
                data.get(
                    "usage_restrictions_present",
                    False
                )
            )
        )

        # --------------------------------------------------
        # SLOT NUMBER
        # Only take an actual non-empty value
        # --------------------------------------------------

        slot = data.get(
            "slot_number_value"
        )

        if slot is not None:

            slot = str(slot).strip()

            if (
                slot
                and slot.upper()
                not in {
                    "NONE",
                    "NULL",
                    "N/A",
                    "NA",
                    "-"
                }
            ):

                merged["slot_number_value"] = slot
                merged["slot_number_present"] = True

        # --------------------------------------------------
        # BASEMENT / LEVEL
        # --------------------------------------------------

        level = data.get(
            "basement_or_level_value"
        )

        if level is not None:

            level = str(level).strip()

            if level:

                if (
                    merged["basement_or_level_value"]
                    is None
                ):
                    merged[
                        "basement_or_level_value"
                    ] = level

        # --------------------------------------------------
        # SUPPORTING QUOTES
        # --------------------------------------------------

        quotes = data.get(
            "supporting_quotes",
            []
        )

        if isinstance(quotes, list):

            for quote in quotes:

                if not quote:
                    continue

                quote = str(
                    quote
                ).strip()

                if (
                    quote
                    and quote
                    not in merged[
                        "supporting_quotes"
                    ]
                ):

                    merged[
                        "supporting_quotes"
                    ].append(
                        quote
                    )

    # Maximum 5 evidence quotes
    merged[
        "supporting_quotes"
    ] = merged[
        "supporting_quotes"
    ][:5]

    return merged

# ============================================================
# SCREENSHOTS
# ============================================================
def save_parking_screenshots(
    siteplan_pdf_path,
    screenshot_dir,
    session_id,
    zoom=5,
):
    """
    Save Site Plan screenshots using the SAME
    rendering + rotation + resizing + cropping
    used by Qwen.
    """

    os.makedirs(
        screenshot_dir,
        exist_ok=True
    )

    saved = []

    # --------------------------------------------------------
    # OPEN SITE PLAN
    # --------------------------------------------------------

    doc = fitz.open(
        siteplan_pdf_path
    )
    print(
        f"[PARKING DEBUG] Opened PDF: {siteplan_pdf_path}"
    )
    print(
        f"[PARKING DEBUG] Number of pages: {len(doc)}"
    )
    try:

        if len(doc) == 0:
            return []

        page = doc.load_page(0)

        # ----------------------------------------------------
        # RENDER
        # ----------------------------------------------------

        pix = page.get_pixmap(
            matrix=fitz.Matrix(
                zoom,
                zoom
            ),
            alpha=False
        )

        image = Image.frombytes(
            "RGB",
            (
                pix.width,
                pix.height
            ),
            pix.samples
        )

        print(
            f"[PARKING] Original Site Plan: "
            f"{image.width}x{image.height}"
        )

        # ----------------------------------------------------
        # SAME ROTATION AS QWEN
        # ----------------------------------------------------

        image = image.rotate(
            180,
            expand=True
        )

        print(
            "[PARKING] Site Plan rotated 180 degrees"
        )

        # ----------------------------------------------------
        # SAME RESIZE AS QWEN
        # ----------------------------------------------------

        image = resize_for_qwen(
            image,
            max_dimension=7000
        )

        print(
            f"[PARKING] Prepared Site Plan: "
            f"{image.width}x{image.height}"
        )

        # ----------------------------------------------------
        # SAME CROPS AS QWEN
        # ----------------------------------------------------

        crops = create_siteplan_parking_crops(
            image
        )

        # ----------------------------------------------------
        # SAVE ALL CROPS
        # ----------------------------------------------------

        for index, crop in enumerate(
            crops,
            start=1
        ):

            output_path = os.path.join(
                screenshot_dir,
                (
                    f"parking_result_"
                    f"{index}_"
                    f"{session_id}.png"
                )
            )

            crop.save(
                output_path,
                format="PNG",
                optimize=True
            )

            saved.append(
                output_path
            )

            print(
                f"✅ [PARKING] Saved Site Plan "
                f"crop {index}: {output_path}"
            )

    finally:

        doc.close()

    return saved

def clean_siteplan_result(
    data: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(data, dict):
        return {}

    # --------------------------------------------------------
    # Clean parking labels
    # --------------------------------------------------------

    labels = data.get(
        "key_labels_found",
        []
    )

    if not isinstance(labels, list):
        labels = []

    parking_keywords = [
    "parking",
    "car park",
    "car parking",
    "visitor parking",
    "parking slot",
    "parking area",
    "ramp",
    "entry",
    "exit",
    "vehicle entry",
    "vehicle exit",
    "basement parking",
    "parking level",
    "cars required",
    "cars provided",
    "total cars",
    "net total",
    "car required",
    "car provided"
]
    clean_labels = []

    for label in labels:

        label = str(label).strip()

        if not label:
            continue

        label_lower = label.lower()

        # Reject building/wing labels
        if re.match(
            r"^(wing|building|block)[\s\-]*[a-z0-9]+$",
            label_lower
        ):
            continue

        # Accept only parking-related labels
        if any(
            keyword in label_lower
            for keyword in parking_keywords
        ):

            if label not in clean_labels:

                clean_labels.append(label)

    data[
        "key_labels_found"
    ] = clean_labels[:10]

    # --------------------------------------------------------
    # Clean notes
    # --------------------------------------------------------

    notes = data.get(
        "notes",
        []
    )

    if not isinstance(notes, list):
        notes = []

    clean_notes = []

    for note in notes:

        note = str(note).strip()

        if not note:
            continue

        note_lower = note.lower()

        if any(
            keyword in note_lower
            for keyword in parking_keywords
        ):

            if note not in clean_notes:

                clean_notes.append(note)

    data[
        "notes"
    ] = clean_notes[:5]
    # --------------------------------------------------------
    # Clean parking evidence
    # --------------------------------------------------------

    evidence = data.get(
        "parking_evidence",
        []
    )

    if not isinstance(
        evidence,
        list
    ):
        evidence = []

    clean_evidence = []

    for item in evidence:

        item = str(item).strip()

        if not item:
            continue

        item_lower = item.lower()

        if any(
            keyword in item_lower
            for keyword in [
                "parking",
                "cars required",
                "cars provided",
                "car required",
                "car provided",
                "basement",
                "visitor"
            ]
        ):

            if item not in clean_evidence:
                clean_evidence.append(item)

    data[
        "parking_evidence"
    ] = clean_evidence[:10]
    return data


def merge_siteplan_results(
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:

    merged = {
        "has_parking_area_labels": False,
        "has_entry_exit_or_ramps": False,
        "has_slot_numbering": False,
        "key_labels_found": [],
        "notes": [],
        "parking_evidence": []
    }

    for data in results:

        if not isinstance(data, dict):
            continue

        # ====================================================
        # BOOLEAN EVIDENCE
        # TRUE ON ANY TILE = TRUE IN MERGED RESULT
        # ====================================================

        merged[
            "has_parking_area_labels"
        ] = (
            merged[
                "has_parking_area_labels"
            ]
            or bool(
                data.get(
                    "has_parking_area_labels",
                    False
                )
            )
        )

        merged[
            "has_entry_exit_or_ramps"
        ] = (
            merged[
                "has_entry_exit_or_ramps"
            ]
            or bool(
                data.get(
                    "has_entry_exit_or_ramps",
                    False
                )
            )
        )

        merged[
            "has_slot_numbering"
        ] = (
            merged[
                "has_slot_numbering"
            ]
            or bool(
                data.get(
                    "has_slot_numbering",
                    False
                )
            )
        )

        # ====================================================
        # KEY PARKING LABELS
        # ====================================================

        labels = data.get(
            "key_labels_found",
            []
        )

        if isinstance(labels, list):

            for label in labels:

                if label is None:
                    continue

                label = str(label).strip()

                if not label:
                    continue

                # Avoid duplicate labels
                if label not in merged[
                    "key_labels_found"
                ]:

                    merged[
                        "key_labels_found"
                    ].append(label)

        # ====================================================
        # PARKING NOTES
        # ====================================================

        notes = data.get(
            "notes",
            []
        )

        if isinstance(notes, list):

            for note in notes:

                if note is None:
                    continue

                note = str(note).strip()

                if not note:
                    continue

                # Avoid duplicate notes
                if note not in merged[
                    "notes"
                ]:

                    merged[
                        "notes"
                    ].append(note)

        # ====================================================
        # PARKING EVIDENCE
        # ====================================================

        parking_evidence = data.get(
            "parking_evidence",
            []
        )

        if isinstance(
            parking_evidence,
            list
        ):

            for evidence in parking_evidence:

                if evidence is None:
                    continue

                evidence = str(
                    evidence
                ).strip()

                if not evidence:
                    continue

                # Avoid duplicate evidence
                if evidence not in merged[
                    "parking_evidence"
                ]:

                    merged[
                        "parking_evidence"
                    ].append(
                        evidence
                    )

    # ========================================================
    # LIMIT OUTPUT SIZE
    # ========================================================

    merged[
        "key_labels_found"
    ] = merged[
        "key_labels_found"
    ][:10]

    merged[
        "notes"
    ] = merged[
        "notes"
    ][:10]

    merged[
        "parking_evidence"
    ] = merged[
        "parking_evidence"
    ][:10]

    return merged

def create_siteplan_parking_crops(
    image: Image.Image
) -> List[Image.Image]:

    """
    Create targeted crops for parking analysis.

    The site plan contains a dense parking statement/table.
    A dedicated crop is created for that region in addition
    to broader fallback crops.
    """

    image = image.convert("RGB")

    # --------------------------------------------------------
    # SAFETY RESIZE
    # --------------------------------------------------------

    MAX_SITEPLAN_DIMENSION = 7000

    w, h = image.size

    if max(w, h) > MAX_SITEPLAN_DIMENSION:

        scale = (
            MAX_SITEPLAN_DIMENSION
            / max(w, h)
        )

        new_size = (
            max(1, int(w * scale)),
            max(1, int(h * scale))
        )


        image = image.resize(
            new_size,
            Image.Resampling.LANCZOS
        )

    w, h = image.size

    crops = []

    # ========================================================
    # CROP 1
    # ORIGINAL TOP-LEFT / SITE PLAN
    # ========================================================

    crops.append(
        image.crop(
            (
                0,
                0,
                int(w * 0.52),
                int(h * 0.52)
            )
        )
    )

    # ========================================================
    # CROP 2
    # ORIGINAL TOP-RIGHT / SITE PLAN
    # ========================================================

    crops.append(
        image.crop(
            (
                int(w * 0.45),
                0,
                w,
                int(h * 0.52)
            )
        )
    )

    # ========================================================
    # CROP 3
    # PARKING TABLE - IMPORTANT
    #
    # This is the important crop for your document.
    # ========================================================

    parking_crop = image.crop(
        (
            int(w * 0.45),
            int(h * 0.55),
            int(w * 0.85),
            int(h * 0.92)
        )
    )

    crops.append(
        parking_crop
    )


    # ========================================================
    # CROP 4
    # LOWER LEFT SUPPORTING TABLES
    # ========================================================

    crops.append(
        image.crop(
            (
                0,
                int(h * 0.45),
                int(w * 0.55),
                int(h * 0.90)
            )
        )
    )

    # ========================================================
    # CROP 5
    # LOWER RIGHT SUPPORTING AREA
    # ========================================================

    crops.append(
        image.crop(
            (
                int(w * 0.65),
                int(h * 0.45),
                w,
                h
            )
        )
    )

    for i, crop in enumerate(
        crops,
        1
    ):

        print(
            f"[PARKING] Crop {i}: "
            f"{crop.width}x{crop.height} "
            f"({crop.width * crop.height:,} pixels)"
        )

    return crops

# ============================================================
# MAIN PARKING WRAPPER
# ============================================================

def run_parking_wrapper(
    agreement_pdf_path: str,
    siteplan_pdf_path: str,
    tesseract_cmd: Optional[str] = None,
    render_zoom: float = RENDER_ZOOM,
    agreement_max_pages: Optional[int] = AGREEMENT_MAX_PAGES,
    siteplan_max_pages: int = 1,
    session_id: str = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    if not os.path.exists(agreement_pdf_path):
        raise FileNotFoundError(
            f"Agreement PDF not found: {agreement_pdf_path}"
        )

    if not os.path.exists(siteplan_pdf_path):
        raise FileNotFoundError(
            f"Siteplan PDF not found: {siteplan_pdf_path}"
        )

    # ========================================================
    # TESSERACT
    # ========================================================

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    

    # ========================================================
    # SITE PLAN SCREENSHOTS ONLY
    # ========================================================

    if screenshot_dir and session_id:

        try:

            paths = save_parking_screenshots(
                siteplan_pdf_path=siteplan_pdf_path,
                screenshot_dir=screenshot_dir,
                session_id=session_id,
                zoom=2.0
            )

            for path in paths:

                print(
                    f"Saved PARKING Site Plan screenshot → "
                    f"{path}"
                )

        except Exception as e:

            print(
                f"Failed to save PARKING Site Plan "
                f"screenshots: {e}"
            )
        

    # ========================================================
    # FIND AGREEMENT PARKING PAGES
    # ========================================================

    page_numbers = find_parking_page_numbers(
        agreement_pdf_path
    )

    if agreement_max_pages is not None:

        page_numbers = [
            p
            for p in page_numbers
            if p < agreement_max_pages
        ]

    # ========================================================
    # FALLBACK
    # ========================================================

    if not page_numbers:

        print(
            "[PARKING] No parking pages found "
            "from PDF text."
        )


        page_numbers = [0]


    # ========================================================
    # AGREEMENT QWEN EXTRACTION
    # ========================================================

    agreement_results = []

    doc = fitz.open(
        agreement_pdf_path
    )

    for index, page_no in enumerate(
        page_numbers,
        start=1
    ):


        page = doc.load_page(
            page_no
        )

        pix = page.get_pixmap(
            matrix=fitz.Matrix(
                render_zoom,
                render_zoom
            ),
            alpha=False
        )

        image = Image.frombytes(
            "RGB",
            (
                pix.width,
                pix.height
            ),
            pix.samples
        )

        try:

            data = qwen_vision_json_extract(
                AGREEMENT_PROMPT,
                image
            )

            if data:

                # Normalize evidence before merging
                data = normalize_agreement_evidence(
                    data
                )

                agreement_results.append(
                    data
                )

        except Exception as e:

            print(
                f"[ERROR] Qwen agreement "
                f"page {page_no + 1} failed: {e}"
            )

    doc.close()

    if not agreement_results:

        raise RuntimeError(
            "Qwen Vision could not extract "
            "any agreement parking data."
        )

    # ========================================================
    # MERGE AGREEMENT RESULTS
    # ========================================================

    merged_agreement = merge_agreement_results(
        agreement_results
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "MERGED QWEN AGREEMENT DATA"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            merged_agreement,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        "=" * 70
    )

    # ========================================================
    # SITE PLAN RENDER
    # ========================================================

    site_imgs = render_pdf_pages(
        siteplan_pdf_path,
        zoom=5,
        max_pages=siteplan_max_pages
    )

    if not site_imgs:

        raise RuntimeError(
            "Could not render site plan PDF."
        )

    # Site plan is scanned upside down.
    site_imgs[0] = site_imgs[0].rotate(
        180,
        expand=True
    )

    # Prevent extremely large architectural images from
    # reaching Image.crop()
    site_imgs[0] = resize_for_qwen(
        site_imgs[0],
        max_dimension=7000
    )

    print(
        f"[PARKING] Site plan prepared for cropping: "
        f"{site_imgs[0].width}x{site_imgs[0].height}"
    )

    # ========================================================
    # SITE PLAN TILING
    # ========================================================


    site_tiles = create_siteplan_parking_crops(
        site_imgs[0]
    )



    # ========================================================
    # QWEN SITE PLAN EXTRACTION
    # ========================================================

    site_results = []

    for idx, tile in enumerate(
        site_tiles,
        start=1
    ):

        try:

            # Dedicated parking-table crop
            if idx == 3:

                parking_prompt = SITEPLAN_PROMPT + """

    ============================================================
    SPECIAL INSTRUCTION - PARKING TABLE CROP
    ============================================================

    This image is the dedicated PARKING TABLE crop.

    Inspect this crop extremely carefully.

    Look specifically for:

    - PARKING
    - Total Cars Required
    - Cars Required
    - Net Total Cars Required
    - Total Cars Provided
    - Visitor Parking
    - Basement parking
    - Lower Basement
    - Upper Basement
    - parking quantities
    - car counts

    If these are visibly readable, you MUST extract them.

    A parking table is valid parking evidence even if
    individual parking slot numbers are not visible.

    Do NOT return all false merely because this is a
    table rather than a graphical parking layout.
    """

            else:

                parking_prompt = SITEPLAN_PROMPT

            data = qwen_vision_json_extract(
                parking_prompt,
                tile
            )

            if data:

                data = clean_siteplan_result(
                    data
                )

                site_results.append(
                    data
                )


        except Exception as e:

            print(
                f"[ERROR] Qwen site plan tile "
                f"{idx} failed: {e}"
            )
    # ========================================================
    # MERGE SITE PLAN RESULTS
    # ========================================================

    if not site_results:

        raise RuntimeError(
            "Qwen Vision could not extract "
            "any siteplan parking data."
        )

    site_data = merge_siteplan_results(
        site_results
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "MERGED QWEN SITE PLAN DATA"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            site_data,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        "=" * 70
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    agreement_extract = AgreementParkingExtract(
        **merged_agreement
    )

    siteplan_extract = SitePlanParkingExtract(
        **site_data
    )

    # ========================================================
    # DETERMINISTIC SCORE
    # ========================================================

    deterministic = compute_risk_score(
        agreement_extract,
        siteplan_extract
    )

    # ========================================================
    # CLAUDE SCORE
    # ========================================================

    llm_stable = claude_llm_stable_score(
        agreement_extract,
        siteplan_extract
    )

    # ========================================================
    # COMBINED SCORE
    # ========================================================

    combined = int(
        round(
            WEIGHT_DETERMINISTIC
            * deterministic.total_score
            +
            WEIGHT_LLM
            * llm_stable.llm_score_0_100
        )
    )

    combined = max(
        0,
        min(
            100,
            combined
        )
    )

    # ========================================================
    # RISK SCORES
    # ========================================================

    deterministic_risk = (
        risk_score_from_safety(
            deterministic.total_score
        )
    )

    llm_risk = (
        risk_score_from_safety(
            llm_stable.llm_score_0_100
        )
    )

    combined_risk = (
        risk_score_from_safety(
            combined
        )
    )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    return {

        "document_type":
            "PARKING",

        "pages_analyzed":
            [
                p + 1
                for p in page_numbers
            ],

        "extracted":
            CombinedExtract(
                agreement=agreement_extract,
                siteplan=siteplan_extract
            ).model_dump(),

        "deterministic_score":
            deterministic.total_score,

        "deterministic_risk_score":
            deterministic_risk,

        "llm_score":
            llm_stable.llm_score_0_100,

        "llm_risk_score":
            llm_risk,

        "combined_score":
            combined,

        "combined_risk_score":
            combined_risk,

        "risk_interpretation":
            interp_from_score(
                combined
            ),

        "llm_reasoning":
            llm_stable.llm_reasoning_bullets
    }
# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    AGREEMENT_PDF = (
        r"D:\aasthiv2\Aasthi\wrappercode"
        r"\input\parking\Agreement to Sell.pdf"
    )

    SITEPLAN_PDF = (
        r"D:\aasthiv2\Aasthi\wrappercode"
        r"\input\parking\Site Plan.PDF"
    )

    SCREENSHOT_DIR = (
        r"D:\aasthiv2\Aasthi\riskwrapper\screenshots"
    )

    SESSION_ID = datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    result = run_parking_wrapper(
        agreement_pdf_path=AGREEMENT_PDF,
        siteplan_pdf_path=SITEPLAN_PDF,
        tesseract_cmd=None,
        session_id=SESSION_ID,
        screenshot_dir=SCREENSHOT_DIR,
    )

    print(
        "\n"
        + "=" * 70
    )
    print("FINAL PARKING RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str
        )
    )