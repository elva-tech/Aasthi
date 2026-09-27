# ekhata.py — BBMP Bengaluru e-Khata Downloader (Fixed draft handling + polling wait)
# pip install selenium

import argparse
import glob
import os
import time
import base64
import pickle
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

class EKhataBot:
    def __init__(self):
        BASE_DIR = r"D:\desktop\ML project(elva)\aasthiv2\aasthiv2\Aasthi\wrappercode"
        self.download_dir = os.path.join(BASE_DIR, "input", "ekhata")
        self.cookie_file = os.path.join(BASE_DIR, "bbmp_cookies.pkl")
        os.makedirs(self.download_dir, exist_ok=True)
        self.clear_old_downloads()

        options = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": False,
            "profile.default_content_settings.popups": 0,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 30)

    def clear_old_downloads(self):
        for f in glob.glob(os.path.join(self.download_dir, "*.pdf")):
            try: os.remove(f)
            except: pass
        for f in glob.glob(os.path.join(self.download_dir, "*.crdownload")):
            try: os.remove(f)
            except: pass

    def save_cookies(self):
        cookies = self.driver.get_cookies()
        with open(self.cookie_file, 'wb') as f:
            pickle.dump(cookies, f)
        print("   ✅ Cookies saved.")

    def load_cookies(self):
        if os.path.exists(self.cookie_file):
            with open(self.cookie_file, 'rb') as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            print("   ✅ Cookies loaded.")
            return True
        return False

    def perform_login(self):
        print("\n🔐 Login required. Clicking 'Login using mobile & OTP'...")
        try:
            login_elem = self.driver.find_element(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mobile')]")
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", login_elem)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", login_elem)
            print("   ✅ Login link clicked.")
            print("   📱 Please enter your mobile number and OTP in the browser.")
            print("   ⏳ Waiting 60 seconds for login to complete...")
            time.sleep(60)
            self.save_cookies()
            return True
        except Exception as e:
            print(f"   ❌ Could not find login link: {e}")
            return False

    def click_draft_link(self, row=None):
        """
        Click the 'Click Here for draft ekhata' link/button belonging to THIS
        property's results row.

        IMPORTANT: earlier versions searched the whole page ("//*[...]") for
        any element containing both 'draft' and 'ekhata'. That is unsafe —
        it can match a sitewide nav link or heading unrelated to this
        specific property (e.g. a generic 'Draft eKhata Search' tool), which
        routes into BBMP's Property Correction / eKYC Verification workflow
        instead of the actual PDF viewer. Whenever we have the table `row`
        for this property (passed in from search_and_open_ekhata), we search
        ONLY inside that row so we can't click the wrong link.
        """
        search_root = row if row is not None else self.driver
        prefix = "." if row is not None else ""

        try:
            # Exclude nav/header/menu ancestors — these hold sitewide links
            # (like the Property Correction tool) that can falsely match
            # 'draft'+'ekhata' text and hijack navigation away from this
            # specific property's PDF.
            xpath = (
                f"{prefix}//*[not(ancestor::nav) and not(ancestor::header) "
                "and not(contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nav')) "
                "and not(contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'menu')) "
                "and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'draft') "
                "and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ekhata')]"
            )
            elem = search_root.find_element(By.XPATH, xpath)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", elem)
            print("   ✅ Clicked draft eKhata link.")
            return True
        except:
            pass

        # Fallback: look for "click here" + "draft", still scoped to this row
        try:
            xpath = ".//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'click here') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'draft')]"
            elem = search_root.find_element(By.XPATH, xpath)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", elem)
            print("   ✅ Clicked draft eKhata link.")
            return True
        except:
            pass

        # Fallback: look for "click here" + "draft"
        try:
            xpath = "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'click here') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'draft')]"
            elem = self.driver.find_element(By.XPATH, xpath)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", elem)
            print("   ✅ Clicked 'Click Here for draft' link.")
            return True
        except:
            pass

        print("   ⚠️ No draft link found.")
        return False

    def click_view_khata(self, row=None):
        """
        Click the 'VIEW KHATA' link belonging to THIS property's results row
        (appears after login).

        On some property pages (e.g. BBMP South zone, "eKhata already issued"
        properties) the 'Download eKhata' cell contains THREE separate links
        in one cell: VIEW KHATA / PREVIOUS LEGAL PRINT / LATEST LEGAL PRINT.
        A generic "//*[contains(text(),'view khata')]" xpath grabs the whole
        wrapping cell (whose combined text also contains 'view khata') instead
        of the actual clickable <a> tag, so the click silently does nothing.
        We restrict to anchor/button elements, scoped to this row when
        possible, and try several strategies.
        """
        search_root = row if row is not None else self.driver
        prefix = "." if row is not None else ""

        candidates = [
            # Anchor tag whose OWN text (not a parent's concatenated text) is "VIEW KHATA"
            f"{prefix}//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view khata')]",
            # Same but for buttons/spans, in case it's not an <a>
            f"{prefix}//*[self::button or self::span][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view khata')]",
            # Fallback: any leaf anchor node containing just 'view khata' with no children
            f"{prefix}//a[not(*)][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view khata')]",
        ]
        for xpath in candidates:
            try:
                elems = search_root.find_elements(By.XPATH, xpath)
                for elem in elems:
                    if elem.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", elem)
                        print(f"   ✅ VIEW KHATA clicked (xpath: {xpath[:40]}...).")
                        return True
            except Exception:
                continue
        print("   ⚠️ VIEW KHATA button not found.")
        return False

    def is_login_page(self):
        """Check if current page contains login prompt."""
        return "Login using mobile & OTP" in self.driver.page_source

    def is_bbmp_homepage(self):
        """
        Detect if we've been bounced back to the BBMP homepage (this happens
        when a property's eKhata requires authenticated login — clicking
        VIEW KHATA without being logged in redirects here instead of to an
        error, silently losing your search).
        """
        try:
            return self.driver.find_elements(By.XPATH, "//input[@placeholder='Mobile Number']") != []
        except Exception:
            return False

    def perform_manual_login_on_homepage(self):
        """
        This property's page requires actual mobile+OTP login via an inline
        form (Mobile Number field + math captcha) on the BBMP homepage —
        not a clickable 'login' link. The captcha and OTP must be entered by
        a human, so we just pause and wait for the person running the script
        to complete it in the visible browser window.
        """
        print("\n🔐 This property requires mobile + OTP login (captcha form).")
        print("   📱 Please enter your mobile number, solve the captcha, and complete OTP")
        print("      verification in the browser window now.")
        print("   ⏳ Waiting 90 seconds for manual login...")
        time.sleep(90)
        self.save_cookies()

    def search_and_open_ekhata(self, search_type, search_value):
        """
        Runs the full search -> results -> click eKhata -> click view/draft
        sequence. Pulled out of run() so it can be re-invoked after a manual
        login bounces us back to the homepage (the site does not preserve
        search state across login).
        """
        driver = self.driver
        wait = self.wait

        driver.get("https://bbmpeaasthi.karnataka.gov.in/citizen_core/")
        print("✅ BBMP Citizen Core opened")
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Welcome to Faceless')]")))
        print("✅ Page loaded")

        self.load_cookies()

        radio_map = {"ward":"Ward Name or Ward Number","epid":"Property ePID","sas":"SAS Property Tax ID"}
        radio_btn = wait.until(EC.presence_of_element_located((By.XPATH, f"//span[contains(text(),'{radio_map[search_type.lower()]}')]")))
        driver.execute_script("arguments[0].click();", radio_btn)
        print(f"✅ Selected: {radio_map[search_type.lower()]}")

        search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text']")))
        search_box.clear()
        search_box.send_keys(search_value)
        print(f"✅ Entered: {search_value}")

        search_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Search')]")))
        driver.execute_script("arguments[0].click();", search_btn)
        print("✅ Search clicked")
        time.sleep(3)

        wait.until(EC.presence_of_element_located((By.XPATH, "//table//tbody//tr")))
        print("✅ Results loaded")
        time.sleep(2)

        ekhata_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//tbody//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ekhata')]")
        ))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ekhata_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", ekhata_btn)
        print("✅ eKhata button clicked")

        print("⏳ Waiting for page to load...")
        time.sleep(5)

        # Snapshot the info page BEFORE we click anything on it. If the
        # upcoming click lands us somewhere wrong again, this pre-click
        # snapshot shows exactly what links were actually available, so we
        # can target the real one instead of guessing with broad text match.
        self.save_debug_snapshot(f"{search_value}_prelick", label="pre-click info page")

        view_clicked = self.click_view_khata()
        if not view_clicked:
            draft_clicked = self.click_draft_link()
            if not draft_clicked:
                print("   ❌ Could not find draft link or VIEW KHATA.")
                print("   💡 Please manually click the draft link or VIEW KHATA.")
                print("   ⏳ Waiting 30 seconds for manual navigation...")
                time.sleep(30)

    def run(self, search_type, search_value):
        driver = self.driver
        wait = self.wait

        try:
            print(f"\n{'='*60}")
            print(f"🏙️ BBMP BENGALURU e-KHATA DOWNLOAD")
            print(f"{'='*60}")
            print(f"Search Type: {search_type}")
            print(f"Search Value: {search_value}")
            print(f"{'='*60}\n")

            self.search_and_open_ekhata(search_type, search_value)

            # Wait for PDF viewer to load (poll instead of a blind fixed sleep)
            print("\n⏳ Waiting for PDF viewer to load...")
            found_iframe = self.wait_for_pdf_iframe(timeout=45)

            if not found_iframe:
                # Did we get bounced back to the BBMP homepage? This happens
                # when the property's eKhata requires authenticated mobile+OTP
                # login (see is_bbmp_homepage docstring).
                if self.is_bbmp_homepage():
                    print("   🔐 Landed on homepage — this property needs mobile+OTP login.")
                    self.perform_manual_login_on_homepage()
                    print("   🔄 Redoing search now that we should be logged in...")
                    self.search_and_open_ekhata(search_type, search_value)
                    print("\n⏳ Waiting for PDF viewer to load (post-login)...")
                    found_iframe = self.wait_for_pdf_iframe(timeout=45)

                if not found_iframe:
                    self.save_debug_snapshot(search_value, label="no PDF iframe found")

            downloaded = None

            # Method 1: Fetch blob
            print("\n📥 Method 1: Fetch blob...")
            downloaded = self.fetch_pdf_blob(search_value)
            if downloaded:
                return downloaded

            # Method 2: XHR
            print("\n📥 Method 2: XHR request...")
            downloaded = self.fetch_pdf_xhr(search_value)
            if downloaded:
                return downloaded

            # Method 3: Click download button
            print("\n📥 Method 3: Click download button...")
            if self.click_download_button():
                time.sleep(5)
                pdf_files = glob.glob(os.path.join(self.download_dir, "*.pdf"))
                if pdf_files:
                    downloaded = max(pdf_files, key=os.path.getmtime)
                    return self.rename_file(downloaded, search_value)

            # Method 4: Ctrl+S
            print("\n📥 Method 4: Keyboard shortcut (Ctrl+S)...")
            if self.save_as_keyboard():
                time.sleep(5)
                pdf_files = glob.glob(os.path.join(self.download_dir, "*.pdf"))
                if pdf_files:
                    downloaded = max(pdf_files, key=os.path.getmtime)
                    return self.rename_file(downloaded, search_value)

            # Method 5: Page source extraction
            print("\n📥 Method 5: Extract from page source...")
            downloaded = self.extract_pdf_from_page(search_value)
            if downloaded:
                return downloaded

            # Final retry: sometimes the iframe just needed more time than the
            # poll above allowed for (slow network / slow render on BBMP's side)
            print("\n📥 Final retry: blob fetch after extra wait...")
            time.sleep(15)
            downloaded = self.fetch_pdf_blob(search_value) or self.fetch_pdf_xhr(search_value)
            if downloaded:
                return downloaded

            # Fallback: wait for manual download
            print("\n❌ All automatic methods failed.")
            print("💡 The PDF may be visible in the browser window.")
            print("   You can manually save it using the download button or right-click.")
            print(f"   📁 Download folder: {self.download_dir}")
            print("\n⏳ Waiting 30 seconds for manual download...")
            time.sleep(30)

            pdf_files = glob.glob(os.path.join(self.download_dir, "*.pdf"))
            if pdf_files:
                downloaded = max(pdf_files, key=os.path.getmtime)
                return self.rename_file(downloaded, search_value)

            return None

        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self.driver.quit()
            print("\n🔒 Browser closed")

    # ---- Helper methods ----
    def wait_for_pdf_iframe(self, timeout=45, poll=2):
        """
        Poll until an iframe with a blob: src shows up, instead of a blind sleep.
        This replaces the old fixed `time.sleep(10)` which was too short and
        caused inconsistent success between runs.
        """
        print(f"   ⏳ Polling up to {timeout}s for PDF iframe to load...")
        start_time = time.time()
        end_time = start_time + timeout
        while time.time() < end_time:
            try:
                blob_url = self.driver.execute_script("""
                    var iframes = document.querySelectorAll('iframe');
                    for (var i=0; i<iframes.length; i++) {
                        var src = iframes[i].src;
                        if (src && src.indexOf('blob:') === 0) return src;
                    }
                    return null;
                """)
                if blob_url:
                    elapsed = round(time.time() - start_time, 1)
                    print(f"   ✅ Blob iframe found after {elapsed}s")
                    return True
            except Exception:
                pass
            time.sleep(poll)
        print("   ⚠️ Timed out waiting for blob iframe.")
        return False

    def save_debug_snapshot(self, search_value, label=""):
        """
        Save a screenshot + HTML of whatever page we're currently on. Lets
        you see WHY something went wrong (wrong link clicked, an extra
        confirmation step, a popup, etc.) without re-running interactively.
        `label` is just for the printed message, to say what point in the
        flow this snapshot was taken at.
        """
        try:
            ts = int(time.time())
            png_path = os.path.join(self.download_dir, f"debug_{search_value}_{ts}.png")
            html_path = os.path.join(self.download_dir, f"debug_{search_value}_{ts}.html")
            self.driver.save_screenshot(png_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            tag = f" ({label})" if label else ""
            print(f"   🐞 Debug snapshot saved{tag}:\n      {png_path}\n      {html_path}")
        except Exception as e:
            print(f"   Debug snapshot error: {e}")

    def fetch_pdf_blob(self, search_value):
        try:
            result = self.driver.execute_async_script("""
                var callback = arguments[arguments.length - 1];
                var iframes = document.querySelectorAll('iframe');
                for (var i=0; i<iframes.length; i++) {
                    var src = iframes[i].src;
                    if (src && src.indexOf('blob:') === 0) {
                        fetch(src)
                            .then(r => r.arrayBuffer())
                            .then(buffer => {
                                var binary='', bytes=new Uint8Array(buffer);
                                for (var j=0; j<bytes.length; j++) binary += String.fromCharCode(bytes[j]);
                                callback(btoa(binary));
                            })
                            .catch(() => callback(null));
                        return;
                    }
                }
                callback(null);
            """)
            if result:
                return self.save_pdf(result, search_value)
        except Exception as e:
            print(f"   Blob fetch error: {e}")
        return None

    def fetch_pdf_xhr(self, search_value):
        try:
            blob_url = self.driver.execute_script("""
                var iframes = document.querySelectorAll('iframe');
                for (var i=0; i<iframes.length; i++) {
                    var src = iframes[i].src;
                    if (src && src.indexOf('blob:') === 0) return src;
                }
                return null;
            """)
            if not blob_url:
                return None
            result = self.driver.execute_async_script("""
                var blobUrl = arguments[0];
                var callback = arguments[arguments.length - 1];
                var xhr = new XMLHttpRequest();
                xhr.open('GET', blobUrl, true);
                xhr.responseType = 'arraybuffer';
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        var buffer = xhr.response;
                        var bytes = new Uint8Array(buffer);
                        var binary='';
                        for (var i=0; i<bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                        callback(btoa(binary));
                    } else callback(null);
                };
                xhr.onerror = function() { callback(null); };
                xhr.send();
            """, blob_url)
            if result:
                return self.save_pdf(result, search_value)
        except Exception as e:
            print(f"   XHR error: {e}")
        return None

    def click_download_button(self):
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    selectors = [
                        "button#download",
                        "button[aria-label='Download']",
                        "button[title='Download']",
                        "cr-icon-button#download",
                        "button[class*='download']",
                        "div[role='button'][aria-label='Download']"
                    ]
                    for sel in selectors:
                        try:
                            btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                            if btn.is_displayed():
                                self.driver.execute_script("arguments[0].click();", btn)
                                self.driver.switch_to.default_content()
                                return True
                        except:
                            continue
                    self.driver.switch_to.default_content()
                except:
                    self.driver.switch_to.default_content()
                    continue
        except:
            pass
        return False

    def save_as_keyboard(self):
        try:
            self.driver.find_element(By.TAG_NAME, 'body').click()
            time.sleep(1)
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
            time.sleep(2)
            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            return True
        except:
            return False

    def extract_pdf_from_page(self, search_value):
        try:
            page = self.driver.page_source
            match = re.search(r'data:application/pdf;base64,([^"\']+)', page)
            if match:
                return self.save_pdf(match.group(1), search_value)
            match = re.search(r'pdf_data["\']?\s*[:=]\s*["\']([^"\']+)["\']', page)
            if match:
                return self.save_pdf(match.group(1), search_value)
        except Exception as e:
            print(f"   Page extraction error: {e}")
        return None

    def save_pdf(self, base64_data, search_value):
        try:
            pdf_data = base64.b64decode(base64_data)
            if len(pdf_data) < 1000:
                return None
            filename = os.path.join(self.download_dir, f"ekhata_{search_value}_{int(time.time())}.pdf")
            with open(filename, 'wb') as f:
                f.write(pdf_data)
            print(f"   ✅ PDF saved: {filename}")
            return filename
        except Exception as e:
            print(f"   Save error: {e}")
            return None

    def rename_file(self, old_path, search_value):
        new_name = os.path.join(self.download_dir, f"ekhata_{search_value}_{int(time.time())}.pdf")
        try:
            os.rename(old_path, new_name)
            print(f"   ✅ File renamed: {new_name}")
            return new_name
        except:
            return old_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-type", choices=["epid","sas","ward"], default="epid")
    parser.add_argument("--search-value", required=True)
    args = parser.parse_args()
    bot = EKhataBot()
    result = bot.run(args.search_type, args.search_value)
    if result:
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS! PDF saved to:\n   {result}")
        print(f"{'='*60}")
    else:
        print("\n❌ Failed to download. Please try manually.")