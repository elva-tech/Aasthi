#!/usr/bin/env python
"""
MR (Mutation Register) Fetcher – Dynamic Row Selection
Workflow: MR page → District → Taluk → Hobli → Village → Survey No
          → Fetch Details → Find row matching target survey/hissa → Select
          → Preview → Full-page screenshot
Saves to: input/MR folder
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


class MRFetcher:
    def __init__(self, output_dir, headless=False):
        self.download_dir = os.path.abspath(output_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        print(f"📁 Screenshots will be saved to: {self.download_dir}")

        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_experimental_option('prefs', {
            'download.default_directory': self.download_dir,
            'download.prompt_for_download': False,
        })
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)

    # ------------------------------------------------------------------
    def get_dropdown(self, label_text):
        xpaths = [
            f"//span[normalize-space(text())='{label_text}']/following-sibling::select[1]",
            f"//label[contains(text(), '{label_text}')]/following-sibling::select[1]",
            f"//*[contains(text(), '{label_text}')]/following::select[1]",
        ]
        for xp in xpaths:
            try:
                el = self.driver.find_element(By.XPATH, xp)
                if el.tag_name == 'select':
                    return el
            except:
                continue
        return None

    def select_dropdown_by_label(self, label_text, value, retries=5):
        for attempt in range(retries):
            try:
                el = self.get_dropdown(label_text)
                if not el:
                    print(f"❌ Could not find dropdown for: {label_text}")
                    time.sleep(2)
                    continue
                self.wait.until(lambda d: not el.get_attribute("disabled"))
                self.wait.until(lambda d: len(Select(el).options) > 1)
                select = Select(el)
                try:
                    select.select_by_visible_text(value)
                    print(f"✅ Selected '{value}' in {label_text}")
                    time.sleep(3)
                    return True
                except:
                    for opt in select.options:
                        if value.upper() in opt.text.upper():
                            opt.click()
                            print(f"✅ Selected '{opt.text}' in {label_text}")
                            time.sleep(3)
                            return True
                    avail = [o.text for o in select.options if o.text.strip()]
                    print(f"❌ Could not find '{value}' in {label_text}. Available: {avail}")
                    return False
            except StaleElementReferenceException:
                print(f"⚠️ Stale element on {label_text}, retry {attempt+1}/{retries}")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"⚠️ Error on {label_text}: {e}")
                time.sleep(2)
                continue
        return False

    def enter_survey_number(self, survey_no, retries=5):
        for attempt in range(retries):
            try:
                time.sleep(1)
                locators = [
                    (By.XPATH, "//input[contains(@placeholder, 'Survey')]"),
                    (By.XPATH, "//input[contains(@id, 'Survey')]"),
                    (By.XPATH, "//input[contains(@name, 'Survey')]"),
                ]
                for by, loc in locators:
                    try:
                        els = self.driver.find_elements(by, loc)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                el.clear()
                                el.send_keys(str(survey_no))
                                self.driver.execute_script("""
                                    var element = arguments[0];
                                    ['input','change','keyup','blur'].forEach(function(evt){
                                        element.dispatchEvent(new Event(evt,{bubbles:true}));
                                    });
                                """, el)
                                print(f"✅ Entered '{survey_no}' and triggered change events")
                                time.sleep(3)
                                return True
                    except:
                        continue
            except StaleElementReferenceException:
                time.sleep(2)
                continue
        print("❌ Could not find Survey Number input.")
        return False

    def click_fetch_details(self, timeout=25):
        print(f"⏳ Waiting up to {timeout}s for Fetch Details button...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                buttons = self.driver.find_elements(By.XPATH,
                    "//input[@value='Fetch Details' or @value='Fetch details']")
                if not buttons:
                    buttons = self.driver.find_elements(By.XPATH,
                        "//button[contains(text(), 'Fetch')]")
                if buttons and buttons[0].is_enabled():
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", buttons[0])
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", buttons[0])
                    print("✅ Clicked 'Fetch Details'")
                    time.sleep(5)
                    return True
            except StaleElementReferenceException:
                pass
            except Exception as e:
                print(f"   ...error: {e}")
            time.sleep(2)
        try:
            btn = self.driver.find_element(By.XPATH,
                "//input[@value='Fetch Details' or @value='Fetch details']")
            self.driver.execute_script("arguments[0].removeAttribute('disabled');", btn)
            self.driver.execute_script("arguments[0].click();", btn)
            print("⚠️ Force-enabled and clicked")
            time.sleep(5)
            return True
        except Exception as e:
            print(f"❌ Force failed: {e}")
            return False

    # ------------------------------------------------------------------
    # DYNAMIC: Find row matching target survey/hissa
    # ------------------------------------------------------------------
    def select_row_by_target(self, survey_no, hissa_no, timeout=20):
        """
        Find and click the 'Select' link on the row matching target survey/hissa.
        Rows can appear as: "117/*/1", "117/1", "117/*", etc.
        Falls back to first row if no match found.
        """
        print(f"🔘 Looking for row with Survey {survey_no}, Hissa {hissa_no}...")

        # Possible patterns for the Survey No column
        target_patterns = [
            f"{survey_no}/*/{hissa_no}",   # e.g., 117/*/1
            f"{survey_no}/{hissa_no}",      # e.g., 117/1
            f"{survey_no}/*{hissa_no}",     # e.g., 117/* 1 (no space)
        ]

        start = time.time()
        matched = False
        rows_dumped = False

        while time.time() - start < timeout:
            try:
                # Find all rows in the Mutation Details table
                rows = self.driver.find_elements(By.XPATH, "//table//tr[td]")

                if rows and not rows_dumped:
                    print(f"  📋 Scanning {len(rows)} row(s)...")

                for row in rows:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if not cells:
                            continue

                        # Build a text blob of this row
                        row_text = " | ".join(c.text.strip() for c in cells)
                        # Normalize whitespace
                        row_text_normalized = " ".join(row_text.split())

                        # Check if any target pattern matches
                        for pattern in target_patterns:
                            if pattern in row_text_normalized:
                                print(f"  ✅ Match found! Pattern '{pattern}' in row")
                                # Find Select link in this row
                                select_link = row.find_element(By.XPATH,
                                    ".//a[contains(text(),'Select')]")
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});", select_link)
                                time.sleep(0.5)
                                self.driver.execute_script(
                                    "arguments[0].click();", select_link)
                                print(f"  ✅ Clicked 'Select' on row matching Survey {survey_no}/{hissa_no}")
                                time.sleep(3)
                                return True
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        continue

                # If we've scanned all rows and no match found, dump them
                if rows and not rows_dumped and (time.time() - start > 5):
                    print(f"  ⚠️ No exact match for Survey {survey_no}, Hissa {hissa_no}")
                    print(f"  📋 Available rows in table:")
                    for r in rows:
                        try:
                            cells = r.find_elements(By.TAG_NAME, "td")
                            if cells:
                                summary = " | ".join(c.text.strip()[:25] for c in cells[:4])
                                print(f"    • {summary}")
                        except:
                            continue
                    rows_dumped = True

            except Exception as e:
                print(f"  ⚠️ Scan error: {e}")

            time.sleep(2)

        # FALLBACK: No match found → select first row anyway
        print(f"  ⚠️ Target {survey_no}/{hissa_no} not found in MR")
        print(f"  ℹ️ Falling back to first row (for reference)")
        return self._select_first_row_fallback(timeout=10)

    def _select_first_row_fallback(self, timeout=10):
        """Fallback: click Select on first row of table."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                select_links = self.driver.find_elements(By.XPATH,
                    "//table//a[normalize-space(text())='Select']")
                if not select_links:
                    select_links = self.driver.find_elements(By.XPATH,
                        "//table//a[contains(text(),'Select')]")
                if select_links:
                    target = select_links[0]
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", target)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", target)
                    print("  ✅ Clicked 'Select' on first row (fallback)")
                    time.sleep(3)
                    return True
            except:
                pass
            time.sleep(2)
        print("  ❌ No 'Select' links found")
        return False

    def click_preview(self, timeout=20):
        print("🔘 Looking for 'Preview' button...")
        handles_before = set(self.driver.window_handles)

        start = time.time()
        while time.time() - start < timeout:
            try:
                btns = self.driver.find_elements(By.XPATH, "//input[@value='Preview']")
                if not btns:
                    btns = self.driver.find_elements(By.XPATH,
                        "//button[normalize-space()='Preview']")
                for btn in btns:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.5)
                            self.driver.execute_script("arguments[0].click();", btn)
                            print("  ✅ Clicked 'Preview'")

                            for _ in range(20):
                                time.sleep(0.5)
                                if len(self.driver.window_handles) > len(handles_before):
                                    new_tab = list(set(self.driver.window_handles) - handles_before)[0]
                                    self.driver.switch_to.window(new_tab)
                                    time.sleep(4)
                                    print(f"  ✅ NEW TAB! URL: {self.driver.current_url[:80]}")
                                    return True
                            time.sleep(3)
                            return True
                    except:
                        continue
            except Exception as e:
                print(f"  ⚠️ Preview error: {e}")
            time.sleep(1)
        print("  ❌ Preview button not found")
        return False

    def save_fullpage_screenshot(self, filename):
        print("📸 Taking full-page screenshot...")

        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
            time.sleep(3)

        print(f"  📍 URL: {self.driver.current_url[:100]}")
        print("  ⏳ Waiting for content (10s)...")
        time.sleep(10)

        print("  📜 Scrolling to bottom...")
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            print(f"    Total: {total_height}, Viewport: {viewport_height}")
            current = 0
            while current < total_height:
                self.driver.execute_script(f"window.scrollTo(0, {current});")
                current += viewport_height
                time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Scroll error: {e}")

        try:
            print("  📷 Capturing via CDP...")
            result = self.driver.execute_cdp_cmd('Page.captureScreenshot', {
                'format': 'png',
                'captureBeyondViewport': True,
                'fromSurface': True,
            })
            png_data = base64.b64decode(result['data'])
            filepath = os.path.join(self.download_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(png_data)
            size = os.path.getsize(filepath)
            print(f"  ✅ Screenshot: {filepath} ({size} bytes)")
            return size > 5000
        except Exception as e:
            print(f"  ❌ CDP failed: {e}")
            try:
                filepath = os.path.join(self.download_dir, filename)
                self.driver.save_screenshot(filepath)
                size = os.path.getsize(filepath)
                print(f"  ✅ Screenshot (fallback): {filepath} ({size} bytes)")
                return size > 5000
            except Exception as e2:
                print(f"  ❌ Fallback failed: {e2}")
                return False

    # ------------------------------------------------------------------
    def fetch(self, district, taluk, hobli, village, survey_no, hissa_no):
        url = "https://landrecords.karnataka.gov.in/Service11/MR_MutationExtract.aspx"
        print(f"🔄 Opening MR page: {url}")
        print(f"🎯 Target: Survey {survey_no}, Hissa {hissa_no}")
        self.driver.get(url)
        time.sleep(6)

        try:
            en_btn = self.driver.find_element(By.XPATH, "//input[@value='English']")
            en_btn.click()
            print("✅ Switched to English")
            time.sleep(4)
        except:
            pass

        print("📝 Selecting District...")
        if not self.select_dropdown_by_label("District", district):
            self.driver.quit(); return
        time.sleep(4)

        print("📝 Selecting Taluk...")
        if not self.select_dropdown_by_label("Taluk", taluk):
            self.driver.quit(); return
        time.sleep(4)

        print("📝 Selecting Hobli...")
        if not self.select_dropdown_by_label("Hobli", hobli):
            self.driver.quit(); return
        time.sleep(4)

        print("📝 Selecting Village...")
        if not self.select_dropdown_by_label("Village", village):
            self.driver.quit(); return
        time.sleep(4)

        print("📝 Entering Survey Number...")
        if not self.enter_survey_number(survey_no):
            self.driver.quit(); return
        time.sleep(3)

        print("🔘 Clicking Fetch Details...")
        if not self.click_fetch_details(timeout=25):
            print("⚠️ Could not click Fetch Details.")

        print("⏳ Waiting for Mutation Details table (6s)...")
        time.sleep(6)

        # NEW: Dynamic row selection based on target survey/hissa
        if not self.select_row_by_target(survey_no, hissa_no, timeout=20):
            print("❌ Could not select any row")
            self.driver.save_screenshot("mr_no_select.png")
            self.driver.quit(); return

        time.sleep(3)

        if not self.click_preview(timeout=20):
            print("❌ Could not click Preview")
            self.driver.save_screenshot("mr_no_preview.png")
            self.driver.quit(); return

        time.sleep(5)

        # Save full-page screenshot
        filename = f"MR_{survey_no}_{hissa_no}.png"
        if self.save_fullpage_screenshot(filename):
            print(f"✅ MR screenshot saved: {os.path.join(self.download_dir, filename)}")
        else:
            print("❌ Screenshot failed")

        input("Press Enter to close browser...")
        self.driver.quit()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch MR from Bhoomi Portal")
    parser.add_argument("--district", required=True)
    parser.add_argument("--taluk", required=True)
    parser.add_argument("--hobli", required=True)
    parser.add_argument("--village", required=True)
    parser.add_argument("--survey-no", required=True, type=int)
    parser.add_argument("--hissa-no", required=True, type=int,
                        help="Target hissa number (e.g., 1)")

    default_output = r"C:\Users\tarun\Aasthi\wrappercode\input\MR"
    parser.add_argument("--output-dir", default=default_output)
    args = parser.parse_args()

    fetcher = MRFetcher(output_dir=args.output_dir)
    fetcher.fetch(
        args.district, args.taluk, args.hobli, args.village,
        args.survey_no, args.hissa_no
    )