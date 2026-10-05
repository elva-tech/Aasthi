"""
akarband.py – Akarband Risk Scorer — works for ANY property
Usage: python akarband.py --file "path.pdf" --survey-no 117 --hissa-no 1
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

                # Text content
                if isinstance(item, str):
                    claude_content.append({
                        "type": "text",
                        "text": item
                    })

                # Image content
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


def extract_akarband_details(image_path, survey, hissa):
    image_path = ensure_png(image_path)
    image = Image.open(image_path)
    prompt = f"""Extract from this Karnataka Akarband (survey record).
TARGET PROPERTY: Survey No. {survey}, Hissa No. {hissa}

Return ONLY valid JSON with these fields (empty string if not visible):
{{
  "survey_no": "", "hissa_no": "", "village": "", "hobli": "",
  "taluk": "", "district": "",
  "total_extent": "", "cultivable_extent": "", "kharab_extent": "",
  "classification": "", "assessment": "", "owner_name": ""
}}

RULES:
- classification examples: "Dry / ಖುಷ್ಕಿ", "Wet / ತರಿ", "Garden / ತೋಟ", "Government / ಸರ್ಕಾರಿ", "Private / ಖಾಸಗಿ"
- Preserve Kannada text. Return ONLY valid JSON."""
    response = call_claude_with_retry([prompt, image])

    response_text = "".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    )

    return parse_json(response_text)


def llm_akarband_risk(data, survey, hissa):
    prompt = f"""# ROLE
Senior Indian Land Records Examiner.

# TARGET PROPERTY
Survey No: {survey}, Hissa No: {hissa}

# TASK
Assess BUYER LEGAL RISK (0-100) based ONLY on the Akarband data.

# GUIDELINES
- Government classification → HIGH (70+)
- High kharab (>25%) → MEDIUM
- Missing total extent → MEDIUM
- Missing assessment → LOW-MEDIUM
- Clean private record → LOW

# AKARBAND DATA
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


def num(s):
    try:
        parts = str(s).replace(",", "").split(".")
        if len(parts) >= 2:
            return float(parts[0]) + float(parts[1]) / 40.0
        if "-" in str(s):
            parts = str(s).split("-")
            if len(parts) == 2:
                return float(parts[0]) + float(parts[1]) / 40.0
        return float(s)
    except Exception:
        return 0.0


def calculate_akarband_risk(d, survey, hissa):
    score, reasons = 0, []
    total = num(d.get("total_extent", ""))
    kharab = num(d.get("kharab_extent", ""))

    if "govt" in str(d.get("classification", "")).lower() or "ಸರ್ಕಾರಿ" in str(d.get("classification", "")):
        score += 40; reasons.append("Classified as government land")
    if total > 0 and kharab / total > 0.25:
        score += 25; reasons.append(f"High kharab ({kharab}/{total})")
    if not d.get("total_extent"):
        score += 20; reasons.append("Total extent missing")
    if not d.get("assessment"):
        score += 10; reasons.append("Assessment value missing")

    extracted = str(d.get("survey_no", "")).strip()
    if extracted and extracted != str(survey):
        score += 30
        reasons.append(f"Akarband survey '{extracted}' ≠ target '{survey}'")

    score = min(score, 100)
    level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
    if not reasons:
        reasons.append("No critical issues found in Akarband")
    return {"risk_score": score, "risk_level": level, "reasons": reasons}


def blend_scores(rule_score, llm_score):
    final = max(rule_score, llm_score)
    if rule_score >= 60 and llm_score >= 60:
        final = min(100, final + 5)
    level = "HIGH" if final >= 70 else ("MEDIUM" if final >= 40 else "LOW")
    return {"risk_score": round(final, 2), "risk_level": level}


def analyze_akarband(
    image_path,
    survey,
    hissa,
    output_path=None,
    session_id=None,
    screenshot_dir=None,
):
    print(f"\n📊 Analyzing {image_path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")

    # Save Akarband evidence screenshots
    if screenshot_dir and session_id:
        os.makedirs(screenshot_dir, exist_ok=True)

        try:
            if str(image_path).lower().endswith(".pdf"):
                doc = pymupdf.open(image_path)

                # Save up to 2 important Akarband pages
                for page_no in range(min(2, len(doc))):
                    page = doc.load_page(page_no)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))

                    screenshot_path = os.path.join(
                        screenshot_dir,
                        f"akarband_result_{page_no + 1}_{session_id}.png"
                    )

                    pix.save(screenshot_path)
                    print(
                        f"Saved Akarband screenshot → {screenshot_path}"
                    )

                doc.close()

            else:
                screenshot_path = os.path.join(
                    screenshot_dir,
                    f"akarband_result_1_{session_id}.png"
                )

                Image.open(image_path).save(screenshot_path)
                print(
                    f"Saved Akarband screenshot → {screenshot_path}"
                )

        except Exception as e:
            print(f"Failed to save Akarband screenshots: {e}")

    data = extract_akarband_details(image_path, survey, hissa)
    print(f"  ✅ Extracted: survey={data.get('survey_no', '?')}, "
          f"extent={data.get('total_extent', '?')}, "
          f"class='{data.get('classification', '?')}'")

    rule_risk = calculate_akarband_risk(data, survey, hissa)
    print(f"  ✅ Rule score: {rule_risk['risk_score']} ({rule_risk['risk_level']})")

    try:
        llm_risk = llm_akarband_risk(data, survey, hissa)
        print(f"  ✅ LLM score: {llm_risk.get('risk_score', '?')} ({llm_risk.get('risk_level', '?')})")
        final = blend_scores(rule_risk["risk_score"], llm_risk.get("risk_score", 0))
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        llm_risk = {"error": str(e)}
        final = {"risk_score": rule_risk["risk_score"], "risk_level": rule_risk["risk_level"]}

    result = {
        "doc_type": "AKARBAND", "file": image_path,
        "target": {"survey_no": survey, "hissa_no": hissa},
        "data": data, "rule_risk": rule_risk, "llm_risk": llm_risk, "final": final,
    }

    if output_path is None:
        base = os.path.splitext(os.path.basename(image_path))[0]
        output_path = f"risk_{base}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {output_path}")
    return result


def print_summary(result):
    rule, llm, final = result["rule_risk"], result["llm_risk"], result["final"]
    print("\n" + "=" * 60)
    print("📋 AKARBAND RISK SUMMARY")
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
    parser = argparse.ArgumentParser(description="Akarband Risk Scorer")
    parser.add_argument("--file", required=True)
    parser.add_argument("--survey-no", required=True)
    parser.add_argument("--hissa-no", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = analyze_akarband(args.file, args.survey_no, args.hissa_no, args.output)
    print_summary(result)