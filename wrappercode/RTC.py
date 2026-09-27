#!/usr/bin/env python
"""
RTC Fetcher – Bhoomi Maps (same as Survey Map, only button changed to "RTC Info")
"""

import time
import os
import glob
import shutil
import argparse
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

try:
    import pyautogui
    PY_AUTO_GUI = True
except ImportError:
    PY_AUTO_GUI = False
    print("ℹ️  Install pyautogui for auto-print: pip install pyautogui")


class RTCFetcher:
    def __init__(self, output_dir, headless=False):
        self.download_dir = os.path.abspath(output_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        print(f"📁 PDFs will be saved to: {self.download_dir}")

        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--kiosk-printing')
        options.add_experimental_option('prefs', {
            'download.default_directory': self.download_dir,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'plugins.always_open_pdf_externally': True,
            'printing.default_destination_selection_rules': {
                'kind': 'local',
                'namePattern': 'Microsoft Print to PDF'
            },
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
        return False

    def change_dropdown(self, label_text, value):
        print(f"📝 Changing {label_text} → '{value}'...")
        for attempt in range(5):
            try:
                el = self.driver.find_element(By.XPATH,
                    f"//*[contains(text(),'{label_text}')]/following::select[1]")
                if el.tag_name != 'select':
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

    def select_surnoc_and_hissa(self, surnoc="*", hissa="1"):
        print("📝 Waiting for Information panel...")
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'Information') or contains(text(),'ಮಾಹಿತಿ')]")
            ))
            print("  ✅ Information panel visible")
        except TimeoutException:
            print("  ⚠️ Information panel not detected")
        time.sleep(2)

        # Surnoc
        print("  → Selecting Surnoc...")
        surnoc_done = False
        for attempt in range(20):
            try:
                for sel in self.driver.find_elements(By.XPATH, "//select"):
                    try:
                        s = Select(sel)
                        current = s.first_selected_option.text.strip()
                        if "surnoc" in current.lower() or "ಸರ್ನೋಕ್" in current:
                            for opt in s.options:
                                if opt.text.strip() == surnoc:
                                    try:
                                        opt.click()
                                    except:
                                        self.driver.execute_script("arguments[0].click();", opt)
                                    print(f"    ✅ Selected Surnoc = '{opt.text}'")
                                    surnoc_done = True
                                    break
                            if surnoc_done:
                                break
                    except:
                        continue
                if surnoc_done:
                    break
            except:
                pass
            time.sleep(0.5)

        if not surnoc_done:
            print("  ❌ Surnoc not selected")
            return False

        # Hissa
        print("  → Selecting Hissa...")
        hissa_done = False
        for attempt in range(40):
            try:
                for sel in self.driver.find_elements(By.XPATH, "//select"):
                    try:
                        s = Select(sel)
                        opts = [o.text.strip() for o in s.options]
                        if hissa in opts and len(opts) >= 2:
                            if opts == ['Select Surnoc', '*']:
                                continue
                            for opt in s.options:
                                if opt.text.strip() == hissa:
                                    try:
                                        opt.click()
                                    except:
                                        self.driver.execute_script("arguments[0].click();", opt)
                                    print(f"    ✅ Selected Hissa = '{hissa}'")
                                    hissa_done = True
                                    break
                            if hissa_done:
                                break
                    except:
                        continue
                if hissa_done:
                    break
            except:
                pass
            time.sleep(0.5)

        if surnoc_done and hissa_done:
            print("  ✅ Surnoc and Hissa selected")
            return True
        return surnoc_done and hissa_done

    # ------------------------------------------------------------------
    # THE ONLY CHANGE: "RTC Info" instead of "Digitized Sketch"
    # ------------------------------------------------------------------
    def click_rtc_info(self, timeout=30):
        print("🔘 Looking for 'RTC Info' button...")

        handles_before = set(self.driver.window_handles)
        print(f"  Tabs before click: {len(handles_before)}")

        start = time.time()
        while time.time() - start < timeout:
            xpaths = [
                "//button[contains(normalize-space(.),'RTC Info')]",
                "//button[contains(normalize-space(.),'ಆರ್ ಟಿ ಸಿ ಮಾಹಿತಿ')]",
                "//a[contains(normalize-space(.),'RTC Info')]",
                "//a[contains(normalize-space(.),'ಆರ್ ಟಿ ಸಿ ಮಾಹಿತಿ')]",
                "//div[contains(normalize-space(.),'RTC Info')]",
                "//span[contains(normalize-space(.),'RTC Info')]",
                "//input[@value='RTC Info']",
                "//*[@onclick and contains(., 'RTC Info')]",
                "//*[@onclick and contains(., 'ಆರ್ ಟಿ ಸಿ')]",
            ]

            for xp in xpaths:
                try:
                    elems = self.driver.find_elements(By.XPATH, xp)
                except:
                    continue

                for elem in elems:
                    try:
                        if not (elem.is_displayed() and elem.is_enabled()):
                            continue
                        txt = (elem.text or elem.get_attribute('value') or '').strip()
                        if "Advanced" in txt or "ವಿಸ್ತೃತ" in txt:
                            continue

                        print(f"  Trying element: '{txt[:50]}'")
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", elem)
                        time.sleep(0.5)

                        try:
                            elem.click()
                            print("    → Selenium click sent")
                        except:
                            pass
                        for _ in range(6):
                            time.sleep(0.5)
                            if len(self.driver.window_handles) > len(handles_before):
                                new_tab = list(set(self.driver.window_handles) - handles_before)[0]
                                self.driver.switch_to.window(new_tab)
                                time.sleep(3)
                                print(f"    ✅ NEW TAB OPENED! URL: {self.driver.current_url[:80]}")
                                return True

                        try:
                            self.driver.execute_script("arguments[0].click();", elem)
                            print("    → JS click sent")
                        except:
                            pass
                        for _ in range(6):
                            time.sleep(0.5)
                            if len(self.driver.window_handles) > len(handles_before):
                                new_tab = list(set(self.driver.window_handles) - handles_before)[0]
                                self.driver.switch_to.window(new_tab)
                                time.sleep(3)
                                print(f"    ✅ NEW TAB OPENED! URL: {self.driver.current_url[:80]}")
                                return True

                        try:
                            parent = elem.find_element(By.XPATH, "./..")
                            self.driver.execute_script("arguments[0].click();", parent)
                            print("    → Parent click sent")
                        except:
                            pass
                        for _ in range(6):
                            time.sleep(0.5)
                            if len(self.driver.window_handles) > len(handles_before):
                                new_tab = list(set(self.driver.window_handles) - handles_before)[0]
                                self.driver.switch_to.window(new_tab)
                                time.sleep(3)
                                print(f"    ✅ NEW TAB OPENED! URL: {self.driver.current_url[:80]}")
                                return True
                    except:
                        continue

            time.sleep(1)

        print("  ❌ Could not trigger new tab from RTC Info")
        return False

    def save_pdf(self, filename, timeout=40):
        print("📄 Saving PDF...")

        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
            time.sleep(3)

        print(f"  📍 URL: {self.driver.current_url}")
        print(f"  📍 Title: {self.driver.title}")

        print("  → Looking for Print button...")
        print_clicked = False
        try:
            result = self.driver.execute_script("""
                var els = document.querySelectorAll('input, button, a, i, span');
                for (var i = 0; i < els.length; i++) {
                    var val = (els[i].value || els[i].textContent || els[i].id || '').trim();
                    if (val === 'btnPrint' ||
                        val === 'Print' ||
                        val === 'ಮುದ್ರಿಸಿ' ||
                        val === 'ಡೌನ್‌ಲೋಡ್' ||
                        val === 'Download') {
                        els[i].scrollIntoView({block:'center'});
                        els[i].click();
                        return val;
                    }
                }
                return null;
            """)
            if result:
                print(f"    ✅ Clicked: '{result}'")
                print_clicked = True
        except Exception as e:
            print(f"    ⚠️ Print error: {e}")

        if print_clicked:
            time.sleep(5)
            if PY_AUTO_GUI:
                try:
                    pyautogui.press('enter')
                    print("    ✅ Enter pressed on print dialog")
                    time.sleep(8)
                except Exception as e:
                    print(f"    ⚠️ pyautogui failed: {e}")
            else:
                time.sleep(8)
            if self._wait_for_download(filename, timeout=20):
                return True
            print("  ⚠️ Print approach didn't save, using CDP...")

        print("  → Using CDP Page.printToPDF...")
        try:
            result = self.driver.execute_cdp_cmd('Page.printToPDF', {
                'landscape': False,
                'printBackground': True,
                'paperWidth': 8.27,
                'paperHeight': 11.69,
                'marginTop': 0.3, 'marginBottom': 0.3,
                'marginLeft': 0.3, 'marginRight': 0.3,
            })
            pdf_data = base64.b64decode(result['data'])
            filepath = os.path.join(self.download_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(pdf_data)
            print(f"  ✅ PDF saved (CDP): {filepath}")
            return True
        except Exception as e:
            print(f"  ❌ CDP failed: {e}")
            return False

    def _wait_for_download(self, desired_name, timeout=30):
        print(f"  ⏳ Waiting for file...")
        existing = set(glob.glob(os.path.join(self.download_dir, "*")))
        start = time.time()
        while time.time() - start < timeout:
            current = set(glob.glob(os.path.join(self.download_dir, "*")))
            new_files = current - existing
            new_pdfs = [f for f in new_files if not f.endswith(".crdownload")]
            if new_pdfs:
                time.sleep(1)
                latest = max(new_pdfs, key=os.path.getctime)
                desired_path = os.path.join(self.download_dir, desired_name)
                try:
                    if os.path.exists(desired_path):
                        os.remove(desired_path)
                    shutil.move(latest, desired_path)
                    print(f"    ✅ Renamed → {desired_name}")
                    return True
                except:
                    return False
            time.sleep(1)
        return False

    def fetch(self, search_text, district, taluk, hobli, village,
              survey_no, hissa_no=1, surnoc="*"):
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

        print("⏳ Waiting for map & Information panel (15s)...")
        time.sleep(15)

        self.select_surnoc_and_hissa(surnoc=surnoc, hissa=str(hissa_no))

        # ---- Click "RTC Info" (was "Digitized Sketch" in map_fetcher.py) ----
        if not self.click_rtc_info(timeout=30):
            print("❌ RTC Info not opened"); self.driver.quit(); return

        filename = f"RTC_{survey_no}_{hissa_no}.pdf"
        if self.save_pdf(filename):
            print(f"✅ RTC saved: {os.path.join(self.download_dir, filename)}")
        else:
            print("❌ Save failed")

        input("Press Enter to close browser...")
        self.driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTC Fetcher via Bhoomi Maps")
    parser.add_argument("--search-text", required=True)
    parser.add_argument("--district", required=True)
    parser.add_argument("--taluk", required=True)
    parser.add_argument("--hobli", required=True)
    parser.add_argument("--village", required=True)
    parser.add_argument("--survey-no", required=True, type=int)
    parser.add_argument("--hissa-no", default=1, type=int)
    parser.add_argument("--surnoc", default="*")
    parser.add_argument("--output-dir",
                        default=r"C:\Users\tarun\Aasthi\wrappercode\input\RTC")
    args = parser.parse_args()

    fetcher = RTCFetcher(output_dir=args.output_dir)
    fetcher.fetch(
        search_text=args.search_text,
        district=args.district,
        taluk=args.taluk,
        hobli=args.hobli,
        village=args.village,
        survey_no=args.survey_no,
        hissa_no=args.hissa_no,
        surnoc=args.surnoc,
    )