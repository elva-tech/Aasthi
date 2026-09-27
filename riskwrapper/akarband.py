"""
akarband.py – Akarband Risk Scorer — works for ANY property
Usage: python akarband.py --file "path.pdf" --survey-no 117 --hissa-no 1
"""

import os, json, re, time, argparse
from PIL import Image

API_KEY = os.getenv("GEMINI_API_KEY")
MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash",
                 "gemini-3.8-flash", "gemini-3.5-flash-lite"]

if not API_KEY:
    raise RuntimeError('GEMINI_API_KEY not found.')

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
    response = call_gemini_with_retry([prompt, image])
    return parse_json(response.text)


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
    response = call_gemini_with_retry(prompt)
    return parse_json(response.text)


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


def analyze_akarband(image_path, survey, hissa, output_path=None):
    print(f"\n📊 Analyzing {image_path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")

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