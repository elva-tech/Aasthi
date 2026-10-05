#!/usr/bin/env python
"""
Akarband Fetcher – Bhoomi Mojini Portal (Correct IDs)
URL: https://bhoomojini.karnataka.gov.in/service39/
Saves to: input/Akarband folder
"""

import time
import os
import argparse
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


class AkarbandFetcher:
    def __init__(self, output_dir, headless=False):
        self.download_dir = os.path.abspath(output_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        print(f"📁 PDFs will be saved to: {self.download_dir}")
        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_experimental_option('prefs', {
            'download.default_directory': self.download_dir,
            'download.prompt_for_download': False,
        })
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)

    # ------------------------------------------------------------------
    # Select dropdown by ID with retries
    # ------------------------------------------------------------------
    def select_by_id(self, element_id, value, retries=5, wait_options=True):
        for attempt in range(retries):
            try:
                el = self.driver.find_element(By.ID, element_id)
                self.wait.until(lambda d: not el.get_attribute("disabled"))
                if wait_options:
                    try:
                        self.wait.until(lambda d: len(Select(el).options) > 1)
                    except TimeoutException:
                        print(f"⚠️ {element_id} options not loaded yet")
                        time.sleep(2)
                        continue
                select = Select(el)
                # Exact match
                try:
                    select.select_by_visible_text(value)
                    print(f"✅ Selected '{value}' in {element_id}")
                    time.sleep(3)
                    return True
                except:
                    # Partial match
                    for opt in select.options:
                        if value.upper() in opt.text.upper():
                            opt.click()
                            print(f"✅ Selected '{opt.text}' in {element_id}")
                            time.sleep(3)
                            return True
                    avail = [o.text for o in select.options if o.text.strip()]
                    print(f"❌ '{value}' not in {element_id}. Available: {avail}")
                    return False
            except StaleElementReferenceException:
                print(f"⚠️ Stale element on {element_id}, retry {attempt+1}/{retries}")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"⚠️ Error on {element_id}: {e}")
                time.sleep(2)
                continue
        print(f"❌ Failed to select {element_id}")
        return False

    # ------------------------------------------------------------------
    # Click View Akarband button
    # ------------------------------------------------------------------
    def click_view_akarband(self, timeout=20):
        print(f"⏳ Waiting up to {timeout}s for View Akarband button...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                btns = self.driver.find_elements(By.XPATH, "//input[@value='ಆಕಾರಬಂದ್ ವೀಕ್ಷಿಸಿ']")
                if not btns:
                    btns = self.driver.find_elements(By.XPATH, "//button[contains(text(),'ಆಕಾರಬಂದ್')]")
                if btns:
                    btn = btns[0]
                    if btn.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", btn)
                        print("✅ Clicked View Akarband")
                        time.sleep(5)
                        return True
                    else:
                        print("   ...button still disabled")
            except StaleElementReferenceException:
                pass
            except Exception as e:
                print(f"   ...error: {e}")
            time.sleep(2)

        print("⚠️ Force-enabling View Akarband...")
        try:
            btn = self.driver.find_element(By.XPATH, "//input[@value='ಆಕಾರಬಂದ್ ವೀಕ್ಷಿಸಿ']")
            self.driver.execute_script("arguments[0].removeAttribute('disabled');", btn)
            self.driver.execute_script("arguments[0].click();", btn)
            print("⚠️ Force-enabled and clicked")
            time.sleep(5)
            return True
        except Exception as e:
            print(f"❌ Force failed: {e}")
            self.driver.save_screenshot("akarband_no_button.png")
            with open("akarband_page_source.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            return False

    # ------------------------------------------------------------------
    # Save PDF using CDP
    # ------------------------------------------------------------------
    def save_pdf_via_cdp(self, filename):
        try:
            opts = {
                'landscape': False,
                'displayHeaderFooter': False,
                'printBackground': True,
                'preferCSSPageSize': True,
                'paperWidth': 8.27, 'paperHeight': 11.69,
                'marginTop': 0.4, 'marginBottom': 0.4,
                'marginLeft': 0.4, 'marginRight': 0.4,
            }
            result = self.driver.execute_cdp_cmd('Page.printToPDF', opts)
            pdf_data = base64.b64decode(result['data'])
            filepath = os.path.join(self.download_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(pdf_data)
            print(f"✅ PDF saved: {filepath}")
            return True
        except Exception as e:
            print(f"❌ PDF save failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Main workflow
    # ------------------------------------------------------------------
    def fetch(self, district, taluk, hobli, village, survey_no, surnoc="*", hissa_no=1):
        url = "https://bhoomojini.karnataka.gov.in/service39/"
        print(f"🔄 Opening Akarband page: {url}")
        self.driver.get(url)
        time.sleep(6)

        # ---------- District ----------
        print("📝 Selecting District...")
        if not self.select_by_id("mstAKBDistLst", district):
            print("❌ Failed at District.")
            self.driver.quit()
            return
        time.sleep(4)

        # ---------- Taluk ----------
        print("📝 Selecting Taluk...")
        if not self.select_by_id("mstAKBTlkLst", taluk):
            print("❌ Failed at Taluk.")
            self.driver.quit()
            return
        time.sleep(4)

        # ---------- Hobli ----------
        print("📝 Selecting Hobli...")
        if not self.select_by_id("mstAKBHobliLst", hobli):
            print("❌ Failed at Hobli.")
            self.driver.quit()
            return
        time.sleep(4)

        # ---------- Village ----------
        print("📝 Selecting Village...")
        if not self.select_by_id("mstAKBVillageLst", village):
            print("❌ Failed at Village.")
            self.driver.quit()
            return
        time.sleep(4)

        # ---------- Survey Number (this is a DROPDOWN!) ----------
        print("📝 Selecting Survey Number...")
        if not self.select_by_id("SyNoLst", str(survey_no)):
            print("❌ Failed at Survey No.")
            self.driver.quit()
            return
        time.sleep(3)

        # ---------- Surnoc ----------
        print("📝 Selecting Surnoc...")
        if not self.select_by_id("SurnocLst", surnoc, wait_options=False):
            print("⚠️ Could not select Surnoc, continuing...")
        time.sleep(3)

        # ---------- Hissa ----------
        print("📝 Selecting Hissa...")
        if not self.select_by_id("HissaLst", str(hissa_no), wait_options=False):
            print("⚠️ Could not select Hissa, continuing...")
        time.sleep(3)

        # ---------- Click View Akarband ----------
        print("🔘 Clicking View Akarband...")
        self.click_view_akarband(timeout=25)

        # ---------- Wait for results ----------
        print("⏳ Waiting for Akarband details...")
        time.sleep(10)

        self.driver.save_screenshot("akarband_page.png")
        print("📸 Screenshot: akarband_page.png")

        filename = f"Akarband_{survey_no}_{hissa_no}.pdf"
        if self.save_pdf_via_cdp(filename):
            print(f"✅ Akarband PDF saved: {os.path.join(self.download_dir, filename)}")
        else:
            print("❌ Akarband PDF save failed.")

        input("Press Enter to close browser...")
        self.driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Akarband from Bhoomi Mojini Portal")
    parser.add_argument("--district", required=True)
    parser.add_argument("--taluk", required=True)
    parser.add_argument("--hobli", required=True)
    parser.add_argument("--village", required=True)
    parser.add_argument("--survey-no", required=True, type=int)
    parser.add_argument("--hissa-no", required=True, type=int, default=1)
    parser.add_argument("--surnoc", default="*")

    default_output = r"D:\aasthiv2\Aasthi\wrappercode\input\Akarband"
    parser.add_argument("--output-dir", default=default_output)
    args = parser.parse_args()

    fetcher = AkarbandFetcher(output_dir=args.output_dir)
    fetcher.fetch(
        args.district, args.taluk, args.hobli, args.village,
        args.survey_no, surnoc=args.surnoc, hissa_no=args.hissa_no
    )