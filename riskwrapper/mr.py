"""
mr.py – Mutation Register (MR) Risk Scorer — works for ANY property
Usage: python mr.py --file "path.png" --survey-no 117 --hissa-no 1
Safety-first blend: final = MAX(rule, LLM)
"""

import base64
from email.mime import image
import io
import os, json, re, time, argparse
from PIL import Image
import pymupdf

from anthropic import Anthropic
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY not found.")

client = Anthropic(api_key=API_KEY)


def call_claude_with_retry(contents, max_retries=4):

    last_error = None

    for attempt in range(max_retries):

        try:
            claude_content = []

            items = contents if isinstance(contents, list) else [contents]

            for item in items:

                # Text
                if isinstance(item, str):
                    claude_content.append({
                        "type": "text",
                        "text": item
                    })

                # PIL Image
                elif isinstance(item, Image.Image):

                    buffer = io.BytesIO()
                    item.save(buffer, format="PNG")

                    image_base64 = base64.b64encode(
                        buffer.getvalue()
                    ).decode("utf-8")

                    claude_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64
                        }
                    })

                else:
                    raise TypeError(
                        f"Unsupported content type: {type(item)}"
                    )

            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": claude_content
                    }
                ]
            )

            return response

        except Exception as e:

            last_error = e
            err_str = str(e).lower()

            if (
                "429" in err_str
                or "529" in err_str
                or "overloaded" in err_str
                or "rate limit" in err_str
                or "temporarily unavailable" in err_str
            ):
                wait = 5 * (2 ** attempt)

                print(
                    f"  ⚠️ Claude temporarily unavailable, "
                    f"retry in {wait}s..."
                )

                time.sleep(wait)

            else:
                print(f"  ⚠️ Claude error: {e}")
                break

    raise RuntimeError(
        f"All Claude attempts failed. Last: {last_error}"
    )

def ensure_png(path, page=0):
    if not path.lower().endswith(".pdf"):
        return path
    print(f"  📄 Converting PDF → PNG: {path}")
    import pymupdf
    doc = pymupdf.open(path)
    pg = doc.load_page(page)
    pix = pg.get_pixmap(dpi=200)
    out = path.replace(".pdf", f"_p{page}.png")
    pix.save(out)
    print(f"  ✅ Saved: {out} ({pix.width}x{pix.height})")
    return out


def parse_json(text):
    if not text:
        return {}
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def extract_mr_details(image_path, survey, hissa):
    image_path = ensure_png(image_path)
    image = Image.open(image_path)

    prompt = f"""Analyze this Karnataka Mutation Register (MR) document carefully.

TARGET PROPERTY: Survey No. {survey}, Hissa No. {hissa}

The MR is a table listing mutation entries. Each row usually contains:
- Affected Survey Nos (in format like "117/*/3", "117/*/5", "118/*/1")
- Mutation Year
- Mutation Number / MR Number
- Mutation Type (Kannada text like "ಖಾತೆ ಬದಲಾವಣೆ" = Account change)
- Acquisition Type ("ಪೌತಿ" = Partition, "ವೀರಸ್" = Caveat)
- Tahsildar Approved Date

Return ONLY valid JSON with these fields:
{{
  "target_survey": "{survey}",
  "target_hissa": "{hissa}",
  "target_found": "Yes or No — Does an entry exist specifically for Survey {survey}, Hissa {hissa}?",
  "unique_survey_nos_in_mr": ["list every affected survey number that appears, e.g. 117/3, 117/5"],
  "all_entries": [
    {{
      "survey_no": "",
      "year": "",
      "mutation_no": "",
      "mutation_type": "",
      "acquisition_type": "",
      "date": ""
    }}
  ],
  "caveat_present": "Yes or No — Does the word ವೀರಸ್ appear anywhere?",
  "caveat_survey_nos": ["list of survey numbers with caveat"],
  "possession_entries_present": "Yes or No",
  "recent_mutation_year": "Most recent year in the MR",
  "current_owner": "Name of current owner if visible, else empty",
  "previous_owner": "Name of previous owner if visible, else empty",
  "title_chain_visible": "Yes if you can see a clear chain of owners, else No",
  "raw_notes": "Any other observations"
}}

CRITICAL RULES:
1. If target {survey}/{hissa} is NOT in MR, set target_found = "No".
2. List ALL survey numbers that DO appear in unique_survey_nos_in_mr.
3. Detect any ವೀರಸ್ (caveat) and record which survey numbers.
4. Detect any ಆಕ್ಕು ಮತ್ತು ಮಣಿ ಆಧಾರ (possession) entries.
5. Preserve Kannada text as-is.
6. Return ONLY the JSON object."""

    response = call_claude_with_retry([prompt, image])

    response_text = "".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    )

    return parse_json(response_text)


def llm_mr_risk(data, survey, hissa):
    prompt = f"""# ROLE
Senior Indian Title Chain Examiner and Property Due Diligence Lawyer.

# TARGET PROPERTY
Survey No: {survey}
Hissa No:  {hissa}

# TASK
Assess BUYER LEGAL RISK (0-100) based ONLY on the MR data.

# RISK SCALE
0 = No risk, 100 = Extreme risk

# CRITICAL GUIDELINES

HIGHEST RISK (70-100):
- Target {survey}/{hissa} is MISSING from MR → title chain is BROKEN
- Caveat (ವೀರಸ್) present on target OR any adjacent sub-division

MODERATE RISK (40-70):
- Recent mutation (< 2 years) without prior chain
- Possession entries without ownership transfer
- Missing current/previous owner names
- Only adjacent sub-divisions appear, not target

LOW RISK (0-40):
- Target appears with clear chain
- No caveat, no possession disputes
- Current owner clearly visible

# IMPORTANT
If target {survey}/{hissa} is missing but other sub-divisions appear,
this indicates the mutation for the target was either never done or done
long ago. This is a TITLE CHAIN GAP and MUST be flagged HIGH risk.

# MR DATA
{json.dumps(data, indent=2, ensure_ascii=False)}

# OUTPUT (Return ONLY valid JSON)
{{
  "risk_score": 0,
  "risk_level": "LOW|MEDIUM|HIGH",
  "confidence": 0.0,
  "major_risks": ["...", "..."],
  "positive_findings": ["...", "..."],
  "reasoning": ["...", "..."],
  "recommendations": ["...", "..."],
  "summary": ""
}}

Return ONLY valid JSON."""
    response = call_claude_with_retry(prompt)

    response_text = "".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    )

    return parse_json(response_text)

def yes(s):
    return str(s).strip().lower() in ("yes", "y", "true", "1", "ಹೌದು", "present")


def calculate_mr_risk(d, survey, hissa):
    score = 0
    reasons = []

    target_found = yes(d.get("target_found", ""))
    caveat = yes(d.get("caveat_present", ""))
    possession = yes(d.get("possession_entries_present", ""))
    caveat_surveys = d.get("caveat_survey_nos", [])
    unique_surveys = d.get("unique_survey_nos_in_mr", [])

    if not target_found:
        score += 70
        reasons.append(
            f"TARGET {survey}/{hissa} not found in MR — title chain is BROKEN. "
            f"Only sub-divisions {unique_surveys} appear."
        )

    if caveat:
        score += 40
        reasons.append(f"Caveat (ವೀರಸ್) present on: {caveat_surveys}")

    if possession:
        score += 20
        reasons.append("Possession entries (ಆಕ್ಕು ಮತ್ತು ಮಣಿ ಆಧಾರ) present")

    try:
        y = int(str(d.get("recent_mutation_year", "0")).split("-")[0])
        if 2023 <= y <= 2026:
            score += 10
            reasons.append(f"Very recent mutation: {d.get('recent_mutation_year')}")
    except Exception:
        pass

    if not d.get("current_owner"):
        score += 15
        reasons.append("Current owner not visible in MR")
    if not d.get("previous_owner"):
        score += 10
        reasons.append("Previous owner not visible in MR")

    if str(d.get("title_chain_visible", "")).lower() in ("no", "false"):
        score += 15
        reasons.append("Title chain not visible in MR")

    score = min(score, 100)
    level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")

    if not reasons:
        reasons.append("No critical issues found in MR")

    return {"risk_score": score, "risk_level": level, "reasons": reasons}


def blend_scores(rule_score, llm_score):
    final = max(rule_score, llm_score)
    if rule_score >= 60 and llm_score >= 60:
        final = min(100, final + 5)
    level = "HIGH" if final >= 70 else ("MEDIUM" if final >= 40 else "LOW")
    return {"risk_score": round(final, 2), "risk_level": level}


def analyze_mr(
    image_path,
    survey,
    hissa,
    output_path=None,
    session_id=None,
    screenshot_dir=None,
):
    print(f"\n📜 Analyzing {image_path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")

    # Save MR evidence screenshot
    if screenshot_dir and session_id:
        os.makedirs(screenshot_dir, exist_ok=True)

        try:
            screenshot_path = os.path.join(
                screenshot_dir,
                f"mr_result_1_{session_id}.png"
            )

            Image.open(image_path).save(screenshot_path)

            print(
                f"Saved MR screenshot → {screenshot_path}"
            )

        except Exception as e:
            print(f"Failed to save MR screenshot: {e}")

    data = extract_mr_details(image_path, survey, hissa)
    print(f"  ✅ Target found in MR: {data.get('target_found', '?')}")
    print(f"  ✅ Surveys in MR: {data.get('unique_survey_nos_in_mr', [])}")
    print(f"  ✅ Caveat present: {data.get('caveat_present', '?')}")
    print(f"  ✅ Possession entries: {data.get('possession_entries_present', '?')}")

    rule_risk = calculate_mr_risk(data, survey, hissa)
    print(f"  ✅ Rule score: {rule_risk['risk_score']} ({rule_risk['risk_level']})")

    try:
        llm_risk = llm_mr_risk(data, survey, hissa)
        print(f"  ✅ LLM score: {llm_risk.get('risk_score', '?')} ({llm_risk.get('risk_level', '?')})")
        final = blend_scores(rule_risk["risk_score"], llm_risk.get("risk_score", 0))
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        llm_risk = {"error": str(e)}
        final = {"risk_score": rule_risk["risk_score"], "risk_level": rule_risk["risk_level"]}

    result = {
        "doc_type": "MR",
        "file": image_path,
        "target": {"survey_no": survey, "hissa_no": hissa},
        "data": data,
        "rule_risk": rule_risk,
        "llm_risk": llm_risk,
        "final": final,
    }

    if output_path is None:
        base = os.path.splitext(os.path.basename(image_path))[0]
        output_path = f"risk_{base}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {output_path}")
    return result


def print_summary(result):
    rule = result["rule_risk"]
    llm = result["llm_risk"]
    final = result["final"]

    print("\n" + "=" * 60)
    print("📋 MR RISK SUMMARY")
    print("=" * 60)
    print(f"Target     : Survey {result['target']['survey_no']}, Hissa {result['target']['hissa_no']}")
    print(f"Rule score : {rule['risk_score']}  ({rule['risk_level']})")
    print(f"LLM score  : {llm.get('risk_score', '?')}  ({llm.get('risk_level', '?')})")
    print(f"FINAL      : {final['risk_score']}  ({final['risk_level']})  [MAX, safety-first]")
    print("-" * 60)
    print("Rule reasons:")
    for r in rule["reasons"]:
        print(f"  • {r}")
    if llm.get("summary"):
        print(f"\nLLM summary:\n  {llm['summary']}")
    if llm.get("major_risks"):
        print(f"\nMajor risks flagged by LLM:")
        for r in llm["major_risks"]:
            print(f"  ⚠️  {r}")
    if llm.get("recommendations"):
        print(f"\nRecommendations:")
        for rec in llm["recommendations"]:
            print(f"  • {rec}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MR Risk Scorer")
    parser.add_argument("--file", required=True)
    parser.add_argument("--survey-no", required=True)
    parser.add_argument("--hissa-no", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = analyze_mr(args.file, args.survey_no, args.hissa_no, args.output)
    print_summary(result)