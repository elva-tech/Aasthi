"""
rtc.py – RTC (Pahani) Risk Scorer — works for ANY property
Usage: python rtc.py --file "path.pdf" --survey-no 117 --hissa-no 1
"""

import os, json, re, time, argparse
from PIL import Image
import pymupdf


API_KEY = os.getenv("GEMINI_API_KEY")
MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash",
                 "gemini-3.8-flash", "gemini-3.5-flash-lite"]

if not API_KEY:
    raise RuntimeError('GEMINI_API_KEY not found. Set: $env:GEMINI_API_KEY="AIzaSy..."')

from google import genai
client = genai.Client(api_key=API_KEY)


def call_gemini_with_retry(contents, max_retries=4):
    last_error = None
    for model_name in MODELS_TO_TRY:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(model=model_name, contents=contents)
                if model_name != MODELS_TO_TRY[0]:
                    print(f"  ℹ️ Used fallback model: {model_name}")
                return response
            except Exception as e:
                last_error = e
                s = str(e)
                if "503" in s or "UNAVAILABLE" in s or "high demand" in s:
                    wait = 5 * (2 ** attempt)
                    print(f"  ⚠️ {model_name} overloaded, retry in {wait}s...")
                    time.sleep(wait)
                elif "404" in s or "NOT_FOUND" in s:
                    print(f"  ⚠️ {model_name} unavailable, trying next...")
                    break
                else:
                    print(f"  ⚠️ {model_name} error: {e}")
                    break
    raise RuntimeError(f"All models failed. Last: {last_error}")


def ensure_png(path, page=0):
    if not path.lower().endswith(".pdf"):
        return path
    print(f"  📄 Converting PDF → PNG: {path}")
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


def extract_rtc_details(image_path, survey, hissa):
    image_path = ensure_png(image_path)
    image = Image.open(image_path)
    prompt = f"""Extract from this Karnataka RTC (Pahani) document.
TARGET PROPERTY: Survey No. {survey}, Hissa No. {hissa}

Return ONLY valid JSON with these fields (empty string if not visible):
{{
  "survey_no": "", "hissa_no": "", "village": "", "hobli": "",
  "taluk": "", "district": "", "owner_name": "", "owner_category": "",
  "gov_restriction": "", "court_stay": "", "alienated": "",
  "ongoing_mutation": "", "acquisition_type": "", "total_extent": "",
  "kharab_extent": "", "net_extent": "", "land_revenue": "",
  "soil_type": "", "period": "",
  "government_category_visible": "",
  "saguvali_chit_mentioned": "",
  "ptcl_mentioned": ""
}}

RULES:
- gov_restriction, court_stay, alienated, ongoing_mutation → "Yes" or "No"
- owner_category → usually "Private / ಖಾಸಗಿ" or "Government / ಸರ್ಕಾರಿ"
- government_category_visible → "Yes" if "ಸರ್ಕಾರಿ" or "Government" appears anywhere
- saguvali_chit_mentioned → "Yes" if "ಸಾಗುವಳಿ ಚೀಟಿ" / "Saguvali" / "Grant" appears
- ptcl_mentioned → "Yes" if PTCL or "Prohibition of Transfer" appears
- Preserve Kannada text as-is. Return ONLY valid JSON."""
    response = call_gemini_with_retry([prompt, image])
    return parse_json(response.text)


def llm_rtc_risk(data, survey, hissa):
    prompt = f"""# ROLE
Senior Indian Property Due Diligence Lawyer.

# TARGET PROPERTY
Survey No: {survey}, Hissa No: {hissa}

# TASK
Assess BUYER LEGAL RISK (0-100) based ONLY on the RTC data.

# GUIDELINES
- Court stay / gov restriction / alienated → HIGH (70+)
- Owner category = "Government/ಸರ್ಕಾರಿ" without Saguvali Chit → HIGH (70+)
- PTCL mentioned → HIGH
- Ongoing mutation → MEDIUM-HIGH (50+)
- High kharab (>25%) → MEDIUM (40+)
- Missing owner/extent → MEDIUM
- Clean private land → LOW (<40)

# RTC DATA
{json.dumps(data, indent=2, ensure_ascii=False)}

# OUTPUT (Return ONLY valid JSON)
{{
  "risk_score": 0, "risk_level": "LOW|MEDIUM|HIGH", "confidence": 0.0,
  "major_risks": ["..."], "positive_findings": ["..."],
  "reasoning": ["..."], "recommendations": ["..."], "summary": ""
}}

Return ONLY valid JSON."""
    response = call_gemini_with_retry(prompt)
    return parse_json(response.text)


def num(s):
    try:
        parts = str(s).replace(",", "").split(".")
        if len(parts) >= 2:
            return float(parts[0]) + float(parts[1]) / 40.0
        return float(s)
    except Exception:
        return 0.0


def yes(s):
    return str(s).strip().lower() in ("yes", "y", "true", "1", "ಹೌದು", "present")


def calculate_rtc_risk(d, survey, hissa):
    score, reasons = 0, []
    cat = str(d.get("owner_category", "")).lower()
    gov_visible = yes(d.get("government_category_visible", ""))
    saguvali = yes(d.get("saguvali_chit_mentioned", ""))
    ptcl = yes(d.get("ptcl_mentioned", ""))

    if "govt" in cat or "gov" in cat or "ಸರ್ಕಾರಿ" in cat or gov_visible:
        if saguvali:
            score += 45
            reasons.append("Government land with Saguvali Chit — verify PTCL")
        else:
            score += 75
            reasons.append("Government (ಸರ್ಕಾರಿ) land WITHOUT Saguvali Chit — severe title risk")

    if yes(d.get("gov_restriction", "")):
        score += 50; reasons.append("Government restriction present")
    if yes(d.get("court_stay", "")):
        score += 70; reasons.append("Court stay order on land")
    if yes(d.get("alienated", "")):
        score += 30; reasons.append("Land is alienated")
    if yes(d.get("ongoing_mutation", "")):
        score += 30; reasons.append("Ongoing mutation")
    if ptcl:
        score += 40; reasons.append("PTCL Act mentioned")

    total = num(d.get("total_extent", ""))
    kharab = num(d.get("kharab_extent", ""))
    net = num(d.get("net_extent", ""))
    if total > 0 and kharab / total > 0.25:
        score += 20; reasons.append(f"High kharab ({kharab}/{total})")
    if net <= 0 and total > 0:
        score += 40; reasons.append("Net cultivable extent is zero")

    if not d.get("owner_name"):
        score += 20; reasons.append("Owner name not visible")
    if not d.get("total_extent"):
        score += 15; reasons.append("Total extent missing")
    if "purchased" in str(d.get("acquisition_type", "")).lower():
        score += 5; reasons.append("Acquired by purchase")

    extracted = str(d.get("survey_no", "")).strip()
    if extracted and extracted != str(survey):
        score += 30
        reasons.append(f"RTC survey '{extracted}' ≠ target '{survey}'")

    score = min(score, 100)
    level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
    if not reasons:
        reasons.append("No critical issues found in RTC")
    return {"risk_score": score, "risk_level": level, "reasons": reasons}


def blend_scores(rule_score, llm_score):
    final = max(rule_score, llm_score)
    if rule_score >= 60 and llm_score >= 60:
        final = min(100, final + 5)
    level = "HIGH" if final >= 70 else ("MEDIUM" if final >= 40 else "LOW")
    return {"risk_score": round(final, 2), "risk_level": level}


def analyze_rtc(
    image_path,
    survey,
    hissa,
    output_path=None,
    session_id=None,
    screenshot_dir=None,
):
    print(f"\n📄 Analyzing {image_path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")
    # Save RTC evidence screenshots
    if screenshot_dir and session_id:
        os.makedirs(screenshot_dir, exist_ok=True)

        try:
            if str(image_path).lower().endswith(".pdf"):
                doc = pymupdf.open(image_path)

                # Save up to 2 important RTC pages
                for page_no in range(min(2, len(doc))):
                    page = doc.load_page(page_no)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))

                    screenshot_path = os.path.join(
                        screenshot_dir,
                        f"rtc_result_{page_no + 1}_{session_id}.png"
                    )

                    pix.save(screenshot_path)
                    print(
                        f"Saved RTC screenshot → {screenshot_path}"
                    )

                doc.close()

            else:
                screenshot_path = os.path.join(
                    screenshot_dir,
                    f"rtc_result_1_{session_id}.png"
                )

                Image.open(image_path).save(screenshot_path)
                print(
                    f"Saved RTC screenshot → {screenshot_path}"
                )

        except Exception as e:
            print(f"Failed to save RTC screenshots: {e}")

    data = extract_rtc_details(image_path, survey, hissa)
    print(f"  ✅ Extracted: owner='{data.get('owner_name', '?')}', "
          f"survey={data.get('survey_no', '?')}/{data.get('hissa_no', '?')}, "
          f"cat='{data.get('owner_category', '?')}'")

    rule_risk = calculate_rtc_risk(data, survey, hissa)
    print(f"  ✅ Rule score: {rule_risk['risk_score']} ({rule_risk['risk_level']})")

    try:
        llm_risk = llm_rtc_risk(data, survey, hissa)
        print(f"  ✅ LLM score: {llm_risk.get('risk_score', '?')} ({llm_risk.get('risk_level', '?')})")
        final = blend_scores(rule_risk["risk_score"], llm_risk.get("risk_score", 0))
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        llm_risk = {"error": str(e)}
        final = {"risk_score": rule_risk["risk_score"], "risk_level": rule_risk["risk_level"]}

    result = {
        "doc_type": "RTC", "file": image_path,
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
    print("📋 RTC RISK SUMMARY")
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
    parser = argparse.ArgumentParser(description="RTC Risk Scorer")
    parser.add_argument("--file", required=True)
    parser.add_argument("--survey-no", required=True)
    parser.add_argument("--hissa-no", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = analyze_rtc(args.file, args.survey_no, args.hissa_no, args.output)
    print_summary(result)