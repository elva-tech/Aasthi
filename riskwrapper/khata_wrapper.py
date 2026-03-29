#!/usr/bin/env python3
"""
khata_wrapper.py  (Wrapper version of your KHATA VERIFICATION SYSTEM - UNIFIED)

Exports:
  run_khata_wrapper(
      pid_number: str,
      owner_name_prefix: str,
      expected_owner_name: str = "",
      application_number: str | None = None,
      export_excel: bool = True,
      output_file: str = "khata_report.xlsx",
      use_ai: bool = True,
      force: bool = False,
      cache_dir: str = "khata_output",
      headless: bool = False,
      timeout: int = 40,
  ) -> dict

Wrapper features:
- No hardcoded PID / owner in code
- Optional cache (per PID+app+prefix) to avoid reruns
- Returns dict result (like your other wrappers)
- Optional Excel report generation
- Gemini key via env var (NO hardcoded API key):
    GEMINI_KHATA_KEY=xxxx
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv
load_dotenv()


import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.select import Select


# ================================
# DEFAULTS
# ================================
BBMP_URL = "https://bbmptax.karnataka.gov.in/"


# ================================
# CONFIG (WRAPPER STYLE)
# ================================
@dataclass
class Config:
    PID_NUMBER: str
    OWNER_NAME_PREFIX: str
    EXPECTED_OWNER_NAME: str = ""
    APPLICATION_NUMBER: str = ""
    OUTPUT_FILE: str = "khata_report.xlsx"
    BBMP_URL: str = BBMP_URL
    TIMEOUT: int = 40

    # AI (Gemini)
    USE_AI: bool = True
    GEMINI_API_KEY_ENV: str = "GEMINI_KHATA_KEY"  # set this in .env


# =========================
# UTILS: CACHE
# =========================
def _safe_mkdir(p: str) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def _cache_path(cache_dir: str) -> Path:
    return Path(cache_dir) / "._khata_cache.json"


def _make_input_hash(pid: str, prefix: str, app: str, expected: str) -> str:
    raw = f"{pid}|{prefix}|{app}|{expected}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def load_cached(cache_dir: str) -> Optional[dict]:
    p = _cache_path(cache_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cached(cache_dir: str, input_hash: str, report: dict) -> None:
    try:
        payload = {"input_hash": input_hash, "report": report}
        _cache_path(cache_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


# =========================
# DATA EXTRACTION CLASS
# =========================
class BBMPDataExtractor:
    def __init__(self, config: Config, headless: bool = False, session_id: str = None, screenshot_dir: str = None):
        self.config = config
        self.headless = headless
        self.session_id = session_id
        self.screenshot_dir = screenshot_dir
        self.driver = None
        self.wait = None
        self.property_data: Dict[str, Any] = {}
        self.payment_data: pd.DataFrame = pd.DataFrame()

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, self.config.TIMEOUT)

    def extract_property_details(self):
        try:
            time.sleep(1)

            property_info = {
                "PID": self.config.PID_NUMBER,
                "Application_Number": self.config.APPLICATION_NUMBER,
                "Owner_Name_Search": self.config.OWNER_NAME_PREFIX,
                "Expected_Owner_Name": self.config.EXPECTED_OWNER_NAME,
                "Extraction_Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Owner extraction (your strategies)
            owner_name_found = "Not found"
            try:
                owner_elements = self.driver.find_elements(
                    By.XPATH,
                    "//td[contains(text(),'Owner') or contains(text(),'NAME')]/following-sibling::td[1]"
                )
                if owner_elements:
                    owner_name_found = owner_elements[0].text.strip()

                if owner_name_found == "Not found" or not owner_name_found:
                    rows = self.driver.find_elements(By.XPATH, "//tr")
                    for row in rows:
                        text = row.text.upper()
                        if "OWNER" in text or "NAME" in text:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            if len(cells) >= 2:
                                owner_name_found = cells[1].text.strip()
                                break

                if owner_name_found == "Not found" or not owner_name_found:
                    all_text = self.driver.find_element(By.TAG_NAME, "body").text
                    lines = all_text.split("\n")
                    for line in lines:
                        if self.config.OWNER_NAME_PREFIX[:3].upper() in line.upper():
                            words = line.strip().split()
                            for i, word in enumerate(words):
                                if self.config.OWNER_NAME_PREFIX[:3].upper() in word.upper():
                                    potential_name = " ".join(words[i:min(i + 4, len(words))])
                                    if len(potential_name) > 3:
                                        owner_name_found = potential_name
                                        break
                            if owner_name_found != "Not found":
                                break
            except Exception:
                pass

            property_info["Owner_Name_Portal"] = owner_name_found

            # Address extraction
            address_found = "Not found"
            try:
                address_elements = self.driver.find_elements(
                    By.XPATH,
                    "//td[contains(text(),'Address') or contains(text(),'ADDRESS')]/following-sibling::td[1]"
                )
                if address_elements:
                    address_found = address_elements[0].text.strip()
            except Exception:
                pass
            property_info["Address"] = address_found

            # Khata extraction (no assumptions)
            khata_info_found = "Not found on portal (Manual verification required)"
            khata_type = "Not found"
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.upper()
                if any(x in page_text for x in ["A KHATA", "A-KHATA", "KHATA A", "TYPE A"]):
                    khata_type = "A"
                    khata_info_found = "A Khata (Legally Approved) (as per portal text)"
                elif any(x in page_text for x in ["B KHATA", "B-KHATA", "KHATA B", "TYPE B"]):
                    khata_type = "B"
                    khata_info_found = "B Khata (Unapproved) (as per portal text)"
            except Exception:
                pass

            property_info["Khata_Info"] = khata_info_found
            property_info["Khata_Type"] = khata_type

            self.property_data = property_info

        except Exception:
            self.property_data = {
                "PID": self.config.PID_NUMBER,
                "Owner_Name_Search": self.config.OWNER_NAME_PREFIX,
                "Expected_Owner_Name": self.config.EXPECTED_OWNER_NAME,
                "Owner_Name_Portal": "Not found",
                "Extraction_Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def scrape_bbmp_portal(self) -> Tuple[bool, str]:
        try:
            self.setup_driver()
            self.driver.get(self.config.BBMP_URL)
            time.sleep(2)

            # PID
            pid_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_txtddlno"))
            )
            pid_input.clear()
            pid_input.send_keys(self.config.PID_NUMBER)

            # Owner prefix (first 3 letters)
            owner_prefix = (self.config.OWNER_NAME_PREFIX or "")[:3].upper()
            owner_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_txtname"))
            )
            owner_input.clear()
            owner_input.send_keys(owner_prefix)

            # Retrieve
            retrieve_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@value='Retrieve' or contains(@id,'btnRetrieve')]"))
            )
            self.driver.execute_script("arguments[0].click();", retrieve_button)
            time.sleep(2)

            # Confirm
            confirm_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[contains(@class,'btn-success') or @value='Confirm']"))
            )
            self.driver.execute_script("arguments[0].click();", confirm_button)
            time.sleep(1)

            # Extract property details
            self.extract_property_details()

            # click here
            click_here = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'click here')]")))
            self.driver.execute_script("arguments[0].click();", click_here)
            time.sleep(1)

            # select application number
            try:
                dropdown = self.wait.until(EC.presence_of_element_located((By.XPATH, "//select")))
                try:
                    Select(dropdown).select_by_visible_text("Application Number")
                except Exception:
                    pass
            except Exception:
                pass

            app_no = self.config.APPLICATION_NUMBER or self.config.PID_NUMBER

            app_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[contains(@class,'form-control') or contains(@id,'txt')]"))
            )
            app_input.clear()
            app_input.send_keys(app_no)
            app_input.send_keys("\t")
            time.sleep(0.5)

            retrieve2 = self.wait.until(
                EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_Button1"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", retrieve2)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", retrieve2)

            self.wait.until(EC.presence_of_element_located((By.XPATH, "//th[contains(text(),'SAS App. No')]")))
            time.sleep(1)

            # extract table
            table = self.driver.find_element(By.XPATH, "//table[.//th[contains(text(),'SAS App. No')]]")
            headers = [h.text.strip() for h in table.find_elements(By.XPATH, ".//th")]
            rows = table.find_elements(By.XPATH, ".//tr")[1:]

            rows_data = []
            for row in rows:
                cells = row.find_elements(By.XPATH, ".//td")
                rows_data.append([c.text.strip() for c in cells])

            self.payment_data = pd.DataFrame(rows_data, columns=headers)
            if self.payment_data.empty:
                return False, "Payment table found but empty"

            return True, "OK"
        except Exception as e:
            return False, f"Scraping failed: {e}"

        finally:
            if self.driver:
                try:
                    # Capture screenshot unconditionally if possible
                    if self.screenshot_dir and self.session_id:
                        os.makedirs(self.screenshot_dir, exist_ok=True)
                        path = os.path.join(self.screenshot_dir, f"khata_result_{self.session_id}.png")
                        self.driver.save_screenshot(path)
                        print(f"DEBUG: Saved KHATA screenshot to {path}")
                except Exception as e_shot:
                    print(f"DEBUG: Failed to save KHATA screenshot: {e_shot}")
                finally:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass


# =========================
# SIGNAL BUILDER
# =========================
class SignalBuilder:
    @staticmethod
    def build_signals(payment_df: pd.DataFrame, property_data: dict) -> dict:
        signals: Dict[str, Any] = {}

        signals["pid_valid"] = len(payment_df) > 0
        signals["total_payment_records"] = len(payment_df)

        years = []
        colname = None
        for c in payment_df.columns:
            if "Payment Year" in c and "Form" in c:
                colname = c
                break

        if colname:
            for val in payment_df[colname]:
                match = re.search(r"(\d{4})-(\d{4})", str(val))
                if match:
                    years.append(match.group(1))

        signals["years_present"] = years
        signals["latest_assessment_year"] = years[0] if years else None

        unpaid_count = 0
        if "Paid status" in payment_df.columns:
            for status in payment_df["Paid status"]:
                s = str(status).lower()
                if ("receipt generated" not in s) and ("paid" not in s):
                    unpaid_count += 1
        signals["unpaid_years"] = unpaid_count

        signals["payment_consistency"] = len(years) / max(len(payment_df), 1)
        signals["recent_payment"] = years[0] if years else None

        signals["khata_type"] = property_data.get("Khata_Type", "Not found")
        signals["khata_info"] = property_data.get("Khata_Info", "Not found")

        signals["owner_name_match"] = SignalBuilder.calculate_owner_match(
            property_data.get("Expected_Owner_Name", ""),
            property_data.get("Owner_Name_Portal", ""),
        )

        # =========================
        # ✅ Option A: Owner match interpretation
        # =========================
        expected_raw = str(property_data.get("Expected_Owner_Name", "") or "").strip()
        portal_raw = str(property_data.get("Owner_Name_Portal", "") or "").strip()

        expected_clean = re.sub(r"[^A-Za-z0-9 ]", " ", expected_raw).upper().split()
        portal_clean = re.sub(r"[^A-Za-z0-9 ]", " ", portal_raw).upper().split()

        expected_join = " ".join(expected_clean)
        portal_join = " ".join(portal_clean)

        is_exact = bool(expected_join and portal_join and expected_join == portal_join)

        matched_token = None
        for w in expected_clean:
            if len(w) < 3:
                continue
            for pw in portal_clean:
                if w in pw or pw in w:
                    matched_token = w
                    break
            if matched_token:
                break

        if is_exact:
            signals["owner_match_mode"] = "EXACT"
            signals["owner_match_reason"] = "Exact full-name match after normalization."
        elif float(signals.get("owner_name_match", 0) or 0) >= 0.9:
            signals["owner_match_mode"] = "PARTIAL_SUBSTRING"
            signals["owner_match_reason"] = (
                f"High score is likely from substring/prefix match "
                f"(e.g., '{matched_token or 'token'}' found inside portal name). "
                f"Not a strict full-name equality check."
            )
        else:
            signals["owner_match_mode"] = "WEAK_OR_NONE"
            signals["owner_match_reason"] = "Low/uncertain match between expected and portal owner names."

        # keep your existing fields
        signals["owner_search_prefix"] = property_data.get("Owner_Name_Search", "")
        signals["owner_expected"] = property_data.get("Expected_Owner_Name", "")
        signals["owner_portal"] = property_data.get("Owner_Name_Portal", "")

        # ✅ also fix this small bug (recommended)
        signals["khata_info_available"] = (
            "not found" not in str(property_data.get("Khata_Info", "")).lower()
        )

        signals["address_available"] = property_data.get("Address", "Not found") != "Not found"
        signals["pid_verified"] = signals["pid_valid"] and signals["khata_type"] in ["A", "B"]
        return signals

    @staticmethod
    def calculate_owner_match(expected_name: str, portal_name: str) -> float:
        if not expected_name or not portal_name or portal_name == "Not found":
            return 0.0

        expected_clean = expected_name.upper().strip().replace(".", "").replace(",", "")
        portal_clean = portal_name.upper().strip().replace(".", "").replace(",", "")

        if expected_clean == portal_clean:
            return 1.0

        if expected_clean in portal_clean or portal_clean in expected_clean:
            return 1.0

        expected_words = expected_clean.split()
        portal_words = portal_clean.split()

        for exp_word in expected_words:
            if len(exp_word) < 2:
                continue
            for portal_word in portal_words:
                if exp_word in portal_word or portal_word in exp_word:
                    return 1.0
            if exp_word in portal_clean:
                return 1.0

        if expected_words and portal_words:
            word_overlap = len(set(expected_words) & set(portal_words))
            word_total = len(set(expected_words) | set(portal_words))
            word_match = word_overlap / max(word_total, 1)

            if word_match >= 0.7:
                return 0.85
            elif word_match >= 0.5:
                return 0.7

        char_overlap = len(set(expected_clean) & set(portal_clean))
        char_total = len(set(expected_clean) | set(portal_clean))
        return (char_overlap / max(char_total, 1)) * 0.3


# =========================
# RISK ENGINE
# =========================
class RiskEngine:
    @staticmethod
    def calculate_risk(signals: dict) -> dict:
        score = 0
        reasons = []
        breakdown = {}

        # 1) PID valid
        if signals["pid_valid"]:
            pid_score = 25
            score += pid_score
            reasons.append("✅ PID exists in BBMP records")
            breakdown["PID_Valid"] = pid_score
        else:
            breakdown["PID_Valid"] = 0
            return {
                "risk_score": 0,
                "risk_level": "HIGH",
                "reasons": ["❌ PID not found in BBMP records"],
                "breakdown": breakdown,
            }

        # 2) Khata type
        khata_type = signals.get("khata_type", "Not found")
        if khata_type == "A":
            khata_score = 25
            reasons.append("✅ A Khata - Legally approved property")
        elif khata_type == "B":
            khata_score = 10
            reasons.append("⚠️  B Khata - Unapproved property")
        elif khata_type == "Unknown":
            khata_score = 5
            reasons.append("⚠️  Khata type unclear")
        else:
            khata_score = 0
            reasons.append("⚠️  Khata type not found on portal - Manual verification required")

        score += khata_score
        breakdown["Khata_Type"] = khata_score

        # 3) Owner match
        owner_match = float(signals.get("owner_name_match", 0) or 0)
        if owner_match >= 0.9:
            owner_score = 20
            reasons.append("✅ Owner name matches exactly")
        elif owner_match >= 0.6:
            owner_score = 12
            reasons.append("⚠️  Owner name partially matches")
        else:
            owner_score = 5
            reasons.append("⚠️  Owner name match unclear")

        score += owner_score
        breakdown["Owner_Match"] = owner_score

        # 4) Payment compliance
        unpaid = int(signals.get("unpaid_years", 0) or 0)
        if unpaid == 0:
            payment_score = 20
            reasons.append("✅ No unpaid tax records")
        elif unpaid == 1:
            payment_score = 12
            reasons.append("⚠️  1 unpaid tax record found")
        else:
            payment_score = 5
            reasons.append(f"❌ {unpaid} unpaid tax records found")

        score += payment_score
        breakdown["Payment_Compliance"] = payment_score

        # 5) Recent activity
        if signals.get("latest_assessment_year"):
            recent_score = 10
            reasons.append(f"✅ Recent tax payment: {signals['latest_assessment_year']}")
        else:
            recent_score = 0
            reasons.append("❌ No recent payment records")
        score += recent_score
        breakdown["Recent_Activity"] = recent_score
        score = min(score, 100)

        safety_score = int(score)
        risk_score = 100 - safety_score

        if risk_score <= 25:
            level = "LOW"
        elif risk_score <= 50:
            level = "MEDIUM"
        else:
            level = "HIGH"

        return {
            "safety_score": safety_score,
            "risk_score": risk_score,   # ← real risk now
            "risk_level": level,
            "reasons": reasons,
            "breakdown": breakdown,
        }



# =========================
# AI ANALYSIS (Gemini)
# =========================
class AIAnalyzer:
    @staticmethod
    def _call_gemini(prompt: str, api_key: str) -> dict:
        import requests, json, re

        # ✅ correct endpoint + modern model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 2048,
            },
        }

        r = requests.post(url, headers=headers, json=data, timeout=30)
        r.raise_for_status()
        result = r.json()

        text = result["candidates"][0]["content"]["parts"][0]["text"]

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        return json.loads(text)


    
    @staticmethod
    def analyze(signals: dict, property_data: dict, risk_result: dict, config: Config) -> dict:
        # IMPORTANT:
        # risk_result MUST now contain:
        #   risk_result["safety_score"]
        #   risk_result["risk_score"]  (100 - safety)
        # If you haven't changed RiskEngine yet, do that first.

        def _risk_level_from_risk(risk_score: int) -> str:
            if risk_score <= 25:
                return "LOW"
            elif risk_score <= 50:
                return "MEDIUM"
            else:
                return "HIGH"

        # If AI disabled / missing key: just pass through rule-based safety/risk
        if not config.USE_AI:
            return {
                "ai_safety_score": risk_result["safety_score"],
                "ai_risk_score": risk_result["risk_score"],
                "ai_risk_level": risk_result["risk_level"],
                "ai_explanation": "Rule-based evaluation only (AI disabled)",
                "khata_verification_status": "VERIFIED" if signals.get("khata_type") == "A" else "PARTIAL",
                "ownership_concerns": [],
                "recommended_actions": [],
                "ai_used": False,
                "final_safety_score": risk_result["safety_score"],
                "final_risk_score": risk_result["risk_score"],
                "final_risk_level": risk_result["risk_level"],
            }

        api_key = os.getenv(config.GEMINI_API_KEY_ENV, "").strip()
        if not api_key:
            return {
                "ai_safety_score": risk_result["safety_score"],
                "ai_risk_score": risk_result["risk_score"],
                "ai_risk_level": risk_result["risk_level"],
                "ai_explanation": f"Rule-based evaluation only (missing env var {config.GEMINI_API_KEY_ENV})",
                "khata_verification_status": "VERIFIED" if signals.get("khata_type") == "A" else "PARTIAL",
                "ownership_concerns": [],
                "recommended_actions": [],
                "ai_used": False,
                "final_safety_score": risk_result["safety_score"],
                "final_risk_score": risk_result["risk_score"],
                "final_risk_level": risk_result["risk_level"],
            }

        try:
            prompt = f"""You are an expert BBMP property verification analyst.

    IMPORTANT SCORING RULE (FOLLOW STRICTLY):
    - Return an "ai_safety_score" from 0 to 100 where:
    - 100 = VERY SAFE / LOWEST RISK
    - 0   = VERY RISKY / HIGHEST RISK
    This is a SAFETY score (higher is better). Do NOT invert it.

    PROPERTY DETAILS:
    - PID Number: {property_data.get('PID')}
    - Expected Owner: {signals.get('owner_expected')}
    - Portal Owner: {signals.get('owner_portal')}
    - Owner Match Score: {signals.get('owner_name_match', 0):.0%}
    - Owner Match Mode: {signals.get('owner_match_mode')}
    - Owner Match Reason: {signals.get('owner_match_reason')}
    - Khata Type: {signals.get('khata_type')} ({signals.get('khata_info')})
    - Address Available: {signals.get('address_available')}

    PAYMENT COMPLIANCE:
    - Total Payment Records: {signals.get('total_payment_records')}
    - Latest Payment Year: {signals.get('latest_assessment_year')}
    - Unpaid Records: {signals.get('unpaid_years')}
    - Payment Years: {', '.join(signals.get('years_present', [])[:5])}
    - Payment Consistency: {signals.get('payment_consistency', 0):.0%}

    RULE-BASED REFERENCE (SAFETY):
    - Safety Score: {risk_result['safety_score']}/100
    - Risk Score (for reference only): {risk_result['risk_score']}/100
    - Risk Level: {risk_result['risk_level']}
    - Key Findings: {'; '.join(risk_result['reasons'][:3])}

    Return ONLY valid JSON in this exact format:
    {{
    "ai_safety_score": <number 0-100>,
    "ai_risk_level": "<LOW|MEDIUM|HIGH>",
    "ai_explanation": "<2-3 sentence professional analysis>",
    "khata_verification_status": "<VERIFIED|PARTIAL|FAILED>",
    "ownership_concerns": ["<concern1>", "<concern2>"],
    "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }}"""

            ai_response = AIAnalyzer._call_gemini(prompt, api_key)

            ai_safety = int(ai_response.get("ai_safety_score", risk_result["safety_score"]))
            ai_safety = max(0, min(100, ai_safety))
            ai_risk = 100 - ai_safety

            # Blend SAFETY scores, then convert to risk
            final_safety = int(risk_result["safety_score"] * 0.6 + ai_safety * 0.4)
            final_safety = max(0, min(100, final_safety))
            final_risk = 100 - final_safety
            final_level = _risk_level_from_risk(final_risk)

            return {
                **ai_response,
                "ai_safety_score": ai_safety,
                "ai_risk_score": ai_risk,
                "ai_used": True,
                "final_safety_score": final_safety,
                "final_risk_score": final_risk,
                "final_risk_level": final_level,
            }

        except Exception as e:
            return {
                "ai_safety_score": risk_result["safety_score"],
                "ai_risk_score": risk_result["risk_score"],
                "ai_risk_level": risk_result["risk_level"],
                "ai_explanation": f"Rule-based evaluation (AI error: {str(e)[:120]})",
                "khata_verification_status": "VERIFIED" if signals.get("khata_type") == "A" else "PARTIAL",
                "ownership_concerns": [],
                "recommended_actions": [],
                "ai_used": False,
                "final_safety_score": risk_result["safety_score"],
                "final_risk_score": risk_result["risk_score"],
                "final_risk_level": risk_result["risk_level"],
            }


# =========================
# REPORT GENERATOR (Excel)
# =========================
class ReportGenerator:
    @staticmethod
    def generate_excel_report(payment_df, property_data, signals, risk_result, ai_result, output_file):
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            owner_match_pct = f"{signals.get('owner_name_match', 0)*100:.0f}%"
            summary_data = {
                "Metric": [
                        "PID Number",
                        "Search Prefix Used",
                        "Expected Owner Name",
                        "Portal Owner Name",
                        "Owner Match Score",
                        "Khata Type",
                        "Khata Info",
                        "Total Payment Records",
                        "Unpaid Records",
                        "Latest Payment Year",
                        "",
                        "SAFETY SCORE (Rule-based)",
                        "RISK SCORE (Rule-based) = 100 - Safety",
                        "RISK LEVEL (Rule-based)",
                        "AI Safety Score",
                        "AI Risk Score = 100 - AI Safety",
                        "AI Risk Level",
                        "AI Used",
                        "FINAL SAFETY SCORE (Blend)",
                        "FINAL RISK SCORE (Blend) = 100 - Final Safety",
                        "FINAL RISK LEVEL",
                        "",
                        "Report Generated",
                    ],
                        "Value": [
                        property_data.get("PID", "N/A"),
                        property_data.get("Owner_Name_Search", "N/A"),
                        property_data.get("Expected_Owner_Name", "N/A"),
                        property_data.get("Owner_Name_Portal", "N/A"),
                        owner_match_pct,
                        signals.get("khata_type", "N/A"),
                        signals.get("khata_info", "N/A"),
                        signals.get("total_payment_records", 0),
                        signals.get("unpaid_years", 0),
                        signals.get("latest_assessment_year", "N/A"),
                        "",
                        risk_result.get("safety_score", "N/A"),
                        risk_result.get("risk_score", "N/A"),
                        risk_result.get("risk_level", "N/A"),
                        ai_result.get("ai_safety_score", "N/A"),
                        ai_result.get("ai_risk_score", "N/A"),
                        ai_result.get("ai_risk_level", "N/A"),
                        "Yes (Gemini)" if ai_result.get("ai_used") else "No",
                        ai_result.get("final_safety_score", risk_result.get("safety_score", "N/A")),
                        ai_result.get("final_risk_score", risk_result.get("risk_score", "N/A")),
                        ai_result.get("final_risk_level", risk_result.get("risk_level", "N/A")),
                        "",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ],

            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name="Executive Summary", index=False)
            pd.DataFrame([property_data]).to_excel(writer, sheet_name="Property Details", index=False)
            payment_df.to_excel(writer, sheet_name="Payment History", index=False)
            pd.DataFrame([{"Factor": k, "Points (Safety)": v} for k, v in risk_result.get("breakdown", {}).items()]).to_excel(
                            writer, sheet_name="Safety Breakdown", index=False
                        )

            pd.DataFrame({"Finding": risk_result.get("reasons", [])}).to_excel(writer, sheet_name="Findings", index=False)
            pd.DataFrame([signals]).to_excel(writer, sheet_name="Technical Signals", index=False)

            if ai_result.get("ai_explanation"):
                ai_data = {
                    "Metric": [
                        "AI Used",
                        "AI Model",
                        "AI Safety Score",
                        "AI Risk Score",
                        "AI Risk Level",
                        "Khata Verification Status",
                        "",
                        "AI Explanation",
                        "",
                        "Ownership Concerns",
                        "",
                        "Recommended Actions",
                    ],
                    "Value": [
                        "Yes (Gemini API)" if ai_result.get("ai_used") else "No",
                        "Gemini 2.5 Flash" if ai_result.get("ai_used") else "N/A",
                        ai_result.get("ai_safety_score", "N/A"),
                        ai_result.get("ai_risk_score", "N/A"),
                        ai_result.get("ai_risk_level", "N/A"),
                        ai_result.get("khata_verification_status", "N/A"),
                        "",
                        ai_result.get("ai_explanation", "N/A"),
                        "",
                        "; ".join(ai_result.get("ownership_concerns", [])) if ai_result.get("ownership_concerns") else "None",
                        "",
                        "; ".join(ai_result.get("recommended_actions", [])) if ai_result.get("recommended_actions") else "None",
                    ],

                }
                pd.DataFrame(ai_data).to_excel(writer, sheet_name="AI Analysis", index=False)

        return output_file


# =========================
# WRAPPER ENTRYPOINT
# =========================
def run_khata_wrapper(
    pid_number: str,
    owner_name_prefix: str,
    expected_owner_name: str = "",
    application_number: str | None = None,
    export_excel: bool = True,
    output_file: str = "khata_report.xlsx",
    use_ai: bool = True,
    force: bool = False,
    cache_dir: str = "khata_output",
    headless: bool = False,
    timeout: int = 40,
    session_id: str = None,
    screenshot_dir: str = None
) -> dict:
    """
    Wrapper: scrape -> signals -> rule risk -> AI risk -> optional excel -> return dict
    """
    _safe_mkdir(cache_dir)

    app_no = application_number or pid_number
    input_hash = _make_input_hash(pid_number, owner_name_prefix, app_no, expected_owner_name)

    cached = load_cached(cache_dir)
    if (not force) and cached and cached.get("input_hash") == input_hash:
        report = cached.get("report", {})
        # If user wants excel and it's missing, regenerate only excel from cached data if possible
        return report

    config = Config(
        PID_NUMBER=pid_number,
        OWNER_NAME_PREFIX=owner_name_prefix,
        EXPECTED_OWNER_NAME=expected_owner_name,
        APPLICATION_NUMBER=application_number or "",
        OUTPUT_FILE=output_file,
        TIMEOUT=timeout,
        USE_AI=use_ai
    )
    extractor = BBMPDataExtractor(config, headless=headless, session_id=session_id, screenshot_dir=screenshot_dir)
    ok, msg = extractor.scrape_bbmp_portal()
    if not ok:
        report = {
            "document_type": "KHATA",
            "status": "FAILED",
            "error": msg,
            "input": {
                "pid_number": pid_number,
                "owner_name_prefix": owner_name_prefix,
                "expected_owner_name": expected_owner_name,
                "application_number": app_no,
            },
            "generated_at": datetime.now().isoformat(),
        }
        save_cached(cache_dir, input_hash, report)
        return report

    payment_df = extractor.payment_data
    property_data = extractor.property_data

    signals = SignalBuilder.build_signals(payment_df, property_data)
    risk_result = RiskEngine.calculate_risk(signals)
    ai_result = AIAnalyzer.analyze(signals, property_data, risk_result, config)

    excel_path = None
    if export_excel:
        excel_path = str(Path(cache_dir) / output_file)
        ReportGenerator.generate_excel_report(
            payment_df=payment_df,
            property_data=property_data,
            signals=signals,
            risk_result=risk_result,
            ai_result=ai_result,
            output_file=excel_path,
        )

    report = {
        "document_type": "KHATA",
        "status": "OK",
        "report_metadata": {
            "generated_date": datetime.now().isoformat(),
            "source": config.BBMP_URL,
            "ai_used": bool(ai_result.get("ai_used")),
        },
        "input": {
            "pid_number": pid_number,
            "owner_name_prefix": owner_name_prefix,
            "expected_owner_name": expected_owner_name,
            "application_number": app_no,
        },
        "property_data": property_data,
        "signals": signals,
        "rule_based_risk": risk_result,
        "ai_analysis": ai_result,
        "final_assessment": {
                "final_safety_score": ai_result.get("final_safety_score", risk_result.get("safety_score")),
                "final_risk_score": ai_result.get("final_risk_score", risk_result.get("risk_score")),
                "final_risk_level": ai_result.get("final_risk_level", risk_result.get("risk_level")),
            },

        "exports": {
            "excel_report_path": excel_path,
        },
    }

    save_cached(cache_dir, input_hash, report)
    return report


# =========================
# OPTIONAL CLI
# =========================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="KHATA Verification Wrapper CLI")
    parser.add_argument("--pid", required=True, help="PID number")
    parser.add_argument("--prefix", required=True, help="Owner name prefix (first 3 letters used)")
    parser.add_argument("--expected", default="", help="Expected owner full name (optional)")
    parser.add_argument("--app", default=None, help="Application number (optional; default=PID)")
    parser.add_argument("--outdir", default="khata_output", help="Output/cache directory")
    parser.add_argument("--excel", action="store_true", help="Export Excel report")
    parser.add_argument("--excel-name", default="khata_report.xlsx", help="Excel filename")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI")
    parser.add_argument("--force", action="store_true", help="Ignore cache")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless")
    args = parser.parse_args()

    report = run_khata_wrapper(
        pid_number=args.pid,
        owner_name_prefix=args.prefix,
        expected_owner_name=args.expected,
        application_number=args.app,
        export_excel=args.excel,
        output_file=args.excel_name,
        use_ai=not args.no_ai,
        force=args.force,
        cache_dir=args.outdir,
        headless=args.headless,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
