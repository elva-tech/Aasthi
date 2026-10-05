"""
court.py – Court Case Risk Scorer — works for ANY property
Usage: python court.py --file "path.png" --survey-no 117 --hissa-no 1
"""

import base64
from email.mime import image
import io
import os, json, re, time, argparse
from PIL import Image
import pymupdf

import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY not found.")

from anthropic import Anthropic

client = Anthropic(api_key=API_KEY)


def call_claude_with_retry(contents, max_retries=4):
    last_error = None

    for attempt in range(max_retries):
        try:
            claude_content = []

            items = contents if isinstance(contents, list) else [contents]

            for item in items:

                # Text content
                if isinstance(item, str):
                    claude_content.append({
                        "type": "text",
                        "text": item
                    })

                # PIL image content
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
            s = str(e).lower()

            if (
                "429" in s
                or "529" in s
                or "overloaded" in s
                or "rate limit" in s
                or "temporarily unavailable" in s
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


def extract_court_details(image_path, survey, hissa):
    image_path = ensure_png(image_path)
    image = Image.open(image_path)
    prompt = f"""Extract from this Indian eCourt / RCCMS / Bhoomi Maps RCCMS tab screenshot.
TARGET PROPERTY: Survey No. {survey}, Hissa No. {hissa}

Return ONLY valid JSON with these fields (empty string if not visible):
{{
  "no_cases_message": "",
  "case_type": "", "filing_number": "", "registration_number": "",
  "cnr_number": "", "filing_date": "", "registration_date": "",
  "first_hearing_date": "", "decision_date": "",
  "case_status": "", "nature_of_disposal": "",
  "court_name": "", "petitioner": "", "respondent": "",
  "act": "", "pending": false
}}

RULES:
- no_cases_message → copy the exact text if it says "There are no Revenue Court Cases" or similar. Else empty.
- pending → true if case_status contains "Pending", else false.
- Preserve original text. Return ONLY valid JSON."""
    response = call_claude_with_retry([prompt, image])

    response_text = "".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    )

    return parse_json(response_text)


def llm_court_risk(data, survey, hissa):
    prompt = f"""# ROLE
Senior Indian Property Litigation Lawyer.

# TARGET PROPERTY
Survey No: {survey}, Hissa No: {hissa}

# TASK
Assess BUYER LEGAL RISK (0-100) based ONLY on the case information.

# GUIDELINES
- If "no_cases_message" is set (e.g. "There are no Revenue Court Cases") → LOW (0-15)
- Pending title / partition / injunction suit → HIGH (70+)
- Specific performance / execution petition → HIGH
- High Court / Supreme Court litigation → HIGH
- Pending civil suit → MEDIUM (40-70)
- Disposed / dismissed / withdrawn → LOW (<40)
- No case data → LOW with LOW confidence

# CASE DATA
{json.dumps(data, indent=2, ensure_ascii=False)}

# OUTPUT (Return ONLY valid JSON)
{{
  "risk_score": 0, "risk_level": "LOW|MEDIUM|HIGH", "confidence": 0.0,
  "major_risks": ["..."], "positive_findings": ["..."],
  "reasoning": ["..."], "recommendations": ["..."], "summary": ""
}}

Return ONLY valid JSON."""
    response = call_claude_with_retry(prompt)

    response_text = "".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    )

    return parse_json(response_text)


def calculate_court_risk(d, survey, hissa):
    score, reasons = 0, []

    no_cases = str(d.get("no_cases_message", "")).strip()
    if no_cases and ("no " in no_cases.lower() or "ಇಲ್ಲ" in no_cases):
        reasons.append(f"Explicit no-case message: '{no_cases[:80]}'")
        return {"risk_score": 5, "risk_level": "LOW", "reasons": reasons}

    status = str(d.get("case_status", "")).upper()
    ctype = str(d.get("case_type", "")).upper()
    disposal = str(d.get("nature_of_disposal", "")).upper()
    court = str(d.get("court_name", "")).upper()

    if "PENDING" in status or d.get("pending") is True:
        score += 60; reasons.append("Case is still pending")
    elif any(k in status for k in ("DISPOSED", "CLOSED", "DISMISSED")):
        score += 5; reasons.append("Case disposed / dismissed")
    elif "STAYED" in status:
        score += 40; reasons.append("Case stayed")
    elif "WITHDRAWN" in status:
        score += 10; reasons.append("Case withdrawn")
    else:
        score += 20; reasons.append("Case status unclear")

    if any(k in ctype for k in ("TITLE", "PARTITION", "INJUNCTION")):
        score += 30; reasons.append(f"High-risk case type: {ctype}")
    if "EXECUTION" in ctype:
        score += 20; reasons.append("Execution petition filed")
    if any(k in ctype for k in ("CIVIL", "SUIT")):
        score += 10; reasons.append("Civil suit")
    if "TRANSFERRED" in disposal:
        score += 5; reasons.append("Case transferred")
    if "HIGH COURT" in court or "SUPREME" in court:
        score += 20; reasons.append(f"High court litigation: {court}")

    score = min(score, 100)
    level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
    if not reasons:
        reasons.append("No critical issues found")
    return {"risk_score": score, "risk_level": level, "reasons": reasons}


def blend_scores(rule_score, llm_score):
    final = max(rule_score, llm_score)
    if rule_score >= 60 and llm_score >= 60:
        final = min(100, final + 5)
    level = "HIGH" if final >= 70 else ("MEDIUM" if final >= 40 else "LOW")
    return {"risk_score": round(final, 2), "risk_level": level}


def analyze_court(
    path,
    survey,
    hissa,
    session_id=None,
    output_path=None,
    screenshot_dir=None,
):
    print(f"\n⚖️  Analyzing {path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")

    # Save RCCMS evidence screenshot
    if screenshot_dir and session_id:
        os.makedirs(screenshot_dir, exist_ok=True)

        try:
            screenshot_path = os.path.join(
                screenshot_dir,
                f"rccms_result_1_{session_id}.png"
            )

            if str(path).lower().endswith(".pdf"):
                doc = pymupdf.open(path)
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                pix.save(screenshot_path)
                doc.close()
            else:
                Image.open(path).save(screenshot_path)

            print(
                f"Saved RCCMS screenshot → {screenshot_path}"
            )

        except Exception as e:
            print(f"Failed to save RCCMS screenshot: {e}")

    data = extract_court_details(path, survey, hissa)
    print(f"  ✅ Extracted: type='{data.get('case_type', '?')}', "
          f"status='{data.get('case_status', '?')}', "
          f"no_cases='{str(data.get('no_cases_message', ''))[:40]}'")

    rule_risk = calculate_court_risk(data, survey, hissa)
    print(f"  ✅ Rule score: {rule_risk['risk_score']} ({rule_risk['risk_level']})")

    try:
        llm_risk = llm_court_risk(data, survey, hissa)
        print(f"  ✅ LLM score: {llm_risk.get('risk_score', '?')} ({llm_risk.get('risk_level', '?')})")
        final = blend_scores(rule_risk["risk_score"], llm_risk.get("risk_score", 0))
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        llm_risk = {"error": str(e)}
        final = {"risk_score": rule_risk["risk_score"], "risk_level": rule_risk["risk_level"]}

    result = {
        "doc_type": "COURT", "file": path,
        "target": {"survey_no": survey, "hissa_no": hissa},
        "data": data, "rule_risk": rule_risk, "llm_risk": llm_risk, "final": final,
    }

    if output_path is None:
        base = os.path.splitext(os.path.basename(path))[0]
        output_path = f"risk_{base}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {output_path}")
    return result


def print_summary(result):
    rule, llm, final = result["rule_risk"], result["llm_risk"], result["final"]
    print("\n" + "=" * 60)
    print("📋 COURT RISK SUMMARY")
    print("=" * 60)
    print(f"Target     : Survey {result['target']['survey_no']}, Hissa {result['target']['hissa_no']}")
    print(f"Rule score : {rule['risk_score']}  ({rule['risk_level']})")
    print(f"LLM score  : {llm.get('risk_score', '?')}  ({llm.get('risk_level', '?')})")
    print(f"FINAL      : {final['risk_score']}  ({final['risk_level']})  [MAX, safety-first]")
    print("-" * 60)
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
    parser = argparse.ArgumentParser(description="Court Case Risk Scorer")
    parser.add_argument("--file", required=True)
    parser.add_argument("--survey-no", required=True)
    parser.add_argument("--hissa-no", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = analyze_court(args.file, args.survey_no, args.hissa_no, args.output)
    print_summary(result)