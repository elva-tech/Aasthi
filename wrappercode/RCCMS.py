#!/usr/bin/env python
"""
RCCMS Court Cases Fetcher – via Bhoomi Maps Information Panel
URL: https://rdservices.karnataka.gov.in/BhoomiMaps/
Flow:
  1. Open Bhoomi Maps
  2. Type search text → pick first suggestion
  3. Change Taluk → Hobli → Village → Enter Survey No
  4. Click Search
  5. Wait for Information panel
  6. Click "Ongoing RCCMS" tab
  7. Read result: "There are no Revenue Court Cases" or case details
  8. Save result to input/CourtCases/RCCMS_<survey_no>.txt
"""

import time
import os
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


class RCCMSFetcher:
    def __init__(self, output_dir, headless=False):
        self.download_dir = os.path.abspath(output_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        print(f"📁 Results will be saved to: {self.download_dir}")

        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_experimental_option('prefs', {
            'download.default_directory': self.download_dir,
            'download.prompt_for_download': False,
        })
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)

    # ------------------------------------------------------------------
    def search_and_pick_first(self, search_text):
        print(f"📝 Typing: '{search_text}'")
        inp = self.wait.until(EC.presence_of_element_located(
            (By.XPATH,
             "//input[contains(@placeholder,'Search Village') or "
             "contains(@placeholder,'ಗ್ರಾಮ') or "
             "contains(@placeholder,'Village')]")
        ))
        inp.clear()
        inp.send_keys(search_text)
        time.sleep(3)

        for attempt in range(5):
            try:
                result = self.driver.execute_script("""
                    var suggestions = document.querySelectorAll(
                        '[role="option"], .ui-autocomplete li, .autocomplete-items div, ul.dropdown li'
                    );
                    if (suggestions.length > 0) {
                        suggestions[0].click();
                        return suggestions[0].textContent.trim();
                    }
                    return null;
                """)
                if result:
                    print(f"  ✅ Clicked: {result}")
                    time.sleep(5)
                    return True
            except Exception:
                pass
            time.sleep(1)
        print("  ❌ Could not pick suggestion")
        return False

    def change_dropdown(self, label_text, value):
        print(f"📝 Changing {label_text} → '{value}'...")
        for attempt in range(5):
            try:
                el = self.driver.find_element(By.XPATH,
                    f"//*[contains(text(),'{label_text}')]/following::select[1]")
                if el.tag_name != 'select':
                    print(f"  ❌ Not a select")
                    return False
                select = Select(el)
                for opt in select.options:
                    if value.lower() in opt.text.lower():
                        if not opt.is_selected():
                            try:
                                opt.click()
                            except:
                                self.driver.execute_script("arguments[0].click();", opt)
                            print(f"  ✅ Changed to '{opt.text}'")
                        else:
                            print(f"  ✅ Already '{opt.text}'")
                        time.sleep(3)
                        return True
                print(f"  ❌ '{value}' not found")
                return False
            except StaleElementReferenceException:
                time.sleep(2); continue
            except Exception:
                time.sleep(2); continue
        return False

    def enter_survey_number(self, survey_no):
        print(f"📝 Entering Survey No = {survey_no}")
        for xp in [
            "//label[contains(text(),'Survey')]/following::input[1]",
            "//span[contains(text(),'Survey')]/following::input[1]",
            "//*[contains(text(),'Survey No')]/following::input[1]",
        ]:
            try:
                inp = self.driver.find_element(By.XPATH, xp)
                if inp.is_displayed() and inp.is_enabled() and inp.get_attribute('type') == 'text':
                    inp.clear()
                    inp.send_keys(str(survey_no))
                    print(f"  ✅ Entered '{survey_no}'")
                    time.sleep(2)
                    return True
            except:
                continue
        print("  ⚠️ Survey No input not found")
        return False

    def click_search(self):
        print("🔘 Clicking Search button...")
        for attempt in range(10):
            try:
                result = self.driver.execute_script("""
                    var inputs = document.querySelectorAll('input, button');
                    for (var i = 0; i < inputs.length; i++) {
                        var val = (inputs[i].value || inputs[i].textContent || '').trim();
                        if ((val === 'ಹುಡುಕಿ/Search' ||
                             val === 'Search' ||
                             val === 'ಹುಡುಕಿ' ||
                             val.toLowerCase() === 'search') &&
                            val.toLowerCase().indexOf('advanced') === -1 &&
                            val.indexOf('ವಿಸ್ತೃತ') === -1) {
                            inputs[i].scrollIntoView({block:'center'});
                            inputs[i].click();
                            return val;
                        }
                    }
                    return null;
                """)
                if result:
                    print(f"  ✅ Clicked Search: '{result}'")
                    time.sleep(6)
                    return True
            except Exception as e:
                print(f"  ⚠️ Error: {e}")
            time.sleep(2)
        return False

    # ------------------------------------------------------------------
    # FIXED: Click "Ongoing RCCMS" tab – no \n, no invalid JS
    # ------------------------------------------------------------------
    def click_ongoing_rccms_tab(self, timeout=30):
        print("🔘 Looking for 'Ongoing RCCMS' tab in Information panel...")

        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'Information') or contains(text(),'ಮಾಹಿತಿ')]")
            ))
            print("  ✅ Information panel visible")
        except TimeoutException:
            print("  ⚠️ Information panel not visible")

        # Use a safe JavaScript string (no escaped characters)
        js_script = """
        var els = document.querySelectorAll('a, button, div, span, li, td');
        for (var i = 0; i < els.length; i++) {
            var txt = (els[i].textContent || '').trim().replace(/\\s+/g, ' ');
            if (txt === 'Ongoing RCCMS' ||
                txt === 'Ongoing  RCCMS' ||
                txt === 'RCCMS') {
                els[i].scrollIntoView({block:'center'});
                els[i].click();
                return txt;
            }
        }
        return null;
        """

        start = time.time()
        while time.time() - start < timeout:
            try:
                result = self.driver.execute_script(js_script)
                if result:
                    print(f"  ✅ Clicked '{result}'")
                    time.sleep(4)
                    return True
            except Exception as e:
                print(f"  ⚠️ Attempt error: {e}")
            time.sleep(1)

        print("  ❌ 'Ongoing RCCMS' tab not found")
        return False

    # ------------------------------------------------------------------
    # FIXED: Read result from the info panel only (not whole page)
    # ------------------------------------------------------------------
    def read_rccms_result(self, timeout=15):
        print("📖 Reading RCCMS result...")
        start = time.time()

        while time.time() - start < timeout:
            try:
                # Look for the specific message box in the info panel
                panel_result = None
                for xp in [
                    "//*[contains(text(),'There are no Revenue Court Cases')]",
                    "//*[contains(text(),'no Revenue Court Cases')]",
                    "//*[contains(text(),'ಯಾವುದೇ ಕಂದಾಯ')]",
                ]:
                    try:
                        el = self.driver.find_element(By.XPATH, xp)
                        if el.is_displayed():
                            panel_result = "No ongoing Revenue Court Cases found."
                            print(f"  ✅ {panel_result}")
                            return panel_result, self.driver.find_element(By.TAG_NAME, 'body').text
                    except:
                        continue

                # Check for actual case tables within the RCCMS panel
                # Look specifically inside the info panel div
                case_rows = self.driver.find_elements(By.XPATH,
                    "//div[contains(@class,'info') or contains(@id,'info')]//table//tr"
                    " | //div[contains(text(),'RCCMS')]/following::table//tr"
                )
                if len(case_rows) > 1:
                    result = f"Found {len(case_rows)-1} case row(s) – Manual review required."
                    print(f"  ⚠️ {result}")
                    return result, self.driver.find_element(By.TAG_NAME, 'body').text

            except Exception as e:
                print(f"  ⚠️ Error: {e}")
            time.sleep(1)

        result = "RCCMS result unclear – please verify manually."
        print(f"  ⚠️ {result}")
        return result, ""

    # ------------------------------------------------------------------
    def save_result(self, survey_no, result_text, page_text):
        filename = f"RCCMS_{survey_no}.txt"
        filepath = os.path.join(self.download_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("RCCMS (Revenue Court Case) CHECK REPORT\n")
                f.write("=" * 60 + "\n")
                f.write(f"Survey No    : {survey_no}\n")
                f.write(f"Date         : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source       : Bhoomi Maps – Ongoing RCCMS tab\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"RESULT: {result_text}\n\n")
                f.write("=" * 60 + "\n")
                f.write("FULL PAGE TEXT (for reference)\n")
                f.write("=" * 60 + "\n\n")
                f.write(page_text[:5000])
            print(f"✅ Result saved: {filepath}")
            return True
        except Exception as e:
            print(f"❌ Save failed: {e}")
            return False

    # ------------------------------------------------------------------
    def fetch(self, search_text, district, taluk, hobli, village, survey_no):
        url = "https://rdservices.karnataka.gov.in/BhoomiMaps/"
        print(f"🔄 Opening: {url}")
        self.driver.get(url)
        time.sleep(8)

        if not self.search_and_pick_first(search_text):
            print("❌ Search failed"); self.driver.quit(); return

        self.change_dropdown("Taluk", taluk); time.sleep(3)
        self.change_dropdown("Hobli", hobli); time.sleep(3)
        self.change_dropdown("Village", village); time.sleep(3)
        self.enter_survey_number(survey_no); time.sleep(3)

        if not self.click_search():
            print("❌ Could not click Search"); self.driver.quit(); return

        print("⏳ Waiting for Information panel (15s)...")
        time.sleep(15)

        if not self.click_ongoing_rccms_tab(timeout=30):
            print("⚠️ Could not click RCCMS tab. Trying to read current state...")

        time.sleep(5)

        result_text, page_text = self.read_rccms_result(timeout=15)

        self.save_result(survey_no, result_text, page_text)

        try:
            screenshot_path = os.path.join(self.download_dir, f"RCCMS_{survey_no}.png")
            self.driver.save_screenshot(screenshot_path)
            print(f"📸 Screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"⚠️ Screenshot failed: {e}")

        print("\n" + "=" * 60)
        print("📋 RCCMS CHECK SUMMARY")
        print("=" * 60)
        print(f"Survey No : {survey_no}")
        print(f"Result    : {result_text}")
        print("=" * 60)

        input("Press Enter to close browser...")
        self.driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RCCMS Check via Bhoomi Maps")
    parser.add_argument("--search-text", required=True)
    parser.add_argument("--district", required=True)
    parser.add_argument("--taluk", required=True)
    parser.add_argument("--hobli", required=True)
    parser.add_argument("--village", required=True)
    parser.add_argument("--survey-no", required=True, type=int)
    parser.add_argument("--output-dir",
                        default=r"D:\aasthiv2\Aasthi\wrappercode\input\CourtCases")
    args = parser.parse_args()

    fetcher = RCCMSFetcher(output_dir=args.output_dir)
    fetcher.fetch(
        search_text=args.search_text,
        district=args.district,
        taluk=args.taluk,
        hobli=args.hobli,
        village=args.village,
        survey_no=args.survey_no,
    )