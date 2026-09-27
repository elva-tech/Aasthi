"""
map.py – Map (Form 16A) Risk Scorer — works for ANY property
Usage: python map.py --file "path.pdf" --survey-no 117 --hissa-no 1
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


def extract_map_details(image_path, survey, hissa):
    image_path = ensure_png(image_path)
    image = Image.open(image_path)
    prompt = f"""Extract from this Karnataka land Map (Form 16A / Digitized Sketch / Overlay).
TARGET PROPERTY: Survey No. {survey}, Hissa No. {hissa}

Return ONLY valid JSON with these fields (empty string if not visible):
{{
  "survey_no": "", "hissa_no": "", "village": "", "hobli": "",
  "taluk": "", "district": "", "olc_code": "", "latitude": "", "longitude": "",
  "owner_name": "", "extent": "",
  "sketch_present": "", "overlay_present": "",
  "boundary_measurements": "", "road_access": "", "date_generated": ""
}}

RULES:
- sketch_present → "Yes" if a Digitized Sketch is visible
- overlay_present → "Yes" if an Overlay Map on satellite is visible
- road_access → "Yes" if a road/path is visible
- boundary_measurements → comma-separated numbers in meters
- Preserve Kannada text. Return ONLY valid JSON."""
    response = call_gemini_with_retry([prompt, image])
    return parse_json(response.text)


def llm_map_risk(data, survey, hissa):
    prompt = f"""# ROLE
Senior Indian Land Surveyor and Property Due Diligence Consultant.

# TARGET PROPERTY
Survey No: {survey}, Hissa No: {hissa}

# TASK
Assess BUYER LEGAL RISK (0-100) based ONLY on the Map data.

# GUIDELINES
- No Digitized Sketch → MEDIUM
- No Overlay Map → MEDIUM
- No road access → MEDIUM (potential landlocked)
- Missing OLC / GPS → LOW-MEDIUM
- Boundary measurements missing → MEDIUM
- Complete sketch + overlay + GPS + road → LOW

# MAP DATA
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


def yes(s):
    return str(s).strip().lower() in ("yes", "y", "true", "1", "ಹೌದು", "present")


def calculate_map_risk(d, survey, hissa):
    score, reasons = 0, []
    if not d.get("olc_code"):
        score += 15; reasons.append("OLC code missing")
    if not d.get("latitude") or not d.get("longitude"):
        score += 10; reasons.append("GPS coordinates missing")
    if not yes(d.get("sketch_present", "")):
        score += 25; reasons.append("Digitized Sketch not present")
    if not yes(d.get("overlay_present", "")):
        score += 20; reasons.append("Overlay Map not present")
    if not yes(d.get("road_access", "")):
        score += 15; reasons.append("No clear road access")
    if not d.get("boundary_measurements"):
        score += 15; reasons.append("Boundary measurements missing")

    extracted = str(d.get("survey_no", "")).strip()
    if extracted and extracted != str(survey):
        score += 30
        reasons.append(f"Map survey '{extracted}' ≠ target '{survey}'")

    score = min(score, 100)
    level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
    if not reasons:
        reasons.append("No critical issues found in Map")
    return {"risk_score": score, "risk_level": level, "reasons": reasons}


def blend_scores(rule_score, llm_score):
    final = max(rule_score, llm_score)
    if rule_score >= 60 and llm_score >= 60:
        final = min(100, final + 5)
    level = "HIGH" if final >= 70 else ("MEDIUM" if final >= 40 else "LOW")
    return {"risk_score": round(final, 2), "risk_level": level}


def analyze_map(image_path, survey, hissa, output_path=None):
    print(f"\n🗺️ Analyzing {image_path}")
    print(f"  🎯 Target: Survey {survey}, Hissa {hissa}")

    data = extract_map_details(image_path, survey, hissa)
    print(f"  ✅ Extracted: survey={data.get('survey_no', '?')}, OLC={data.get('olc_code', '?')}")

    rule_risk = calculate_map_risk(data, survey, hissa)
    print(f"  ✅ Rule score: {rule_risk['risk_score']} ({rule_risk['risk_level']})")

    try:
        llm_risk = llm_map_risk(data, survey, hissa)
        print(f"  ✅ LLM score: {llm_risk.get('risk_score', '?')} ({llm_risk.get('risk_level', '?')})")
        final = blend_scores(rule_risk["risk_score"], llm_risk.get("risk_score", 0))
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        llm_risk = {"error": str(e)}
        final = {"risk_score": rule_risk["risk_score"], "risk_level": rule_risk["risk_level"]}

    result = {
        "doc_type": "MAP", "file": image_path,
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
    print("📋 MAP RISK SUMMARY")
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
    parser = argparse.ArgumentParser(description="Map Risk Scorer")
    parser.add_argument("--file", required=True)
    parser.add_argument("--survey-no", required=True)
    parser.add_argument("--hissa-no", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = analyze_map(args.file, args.survey_no, args.hissa_no, args.output)
    print_summary(result)