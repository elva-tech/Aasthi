import os
import re
import time
import requests
from urllib.parse import urlparse, unquote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException


class KarnatakaRERAWrapper:
    def __init__(self, project_name, download_dir="downloads", timeout=40):
        self.project_name = project_name
        self.download_dir = download_dir
        self.timeout = timeout

        os.makedirs(self.download_dir, exist_ok=True)

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")

        prefs = {
            "download.default_directory": os.path.abspath(self.download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        }
        options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, self.timeout)

    # -------------------------------------------------
    # CORE NAVIGATION
    # -------------------------------------------------
    def open_project(self):
        self.driver.get("https://rera.karnataka.gov.in/viewAllProjects")

        project_input = self.wait.until(
            EC.presence_of_element_located((By.ID, "projectName"))
        )
        project_input.clear()
        project_input.send_keys(self.project_name)
        time.sleep(1)
        project_input.send_keys(Keys.ENTER)

        self.wait.until(EC.presence_of_element_located((By.XPATH, "//table/tbody/tr[1]")))
        view_btn = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//table/tbody/tr[1]//a"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", view_btn)
        self.driver.execute_script("arguments[0].click();", view_btn)

    # -------------------------------------------------
    # COMPLETION DETAILS (OC / CC)
    # -------------------------------------------------
    def download_completion_documents(self):
        print("Opening Completion Details tab...")
        completion_tab = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(.,'Completion Details')]"))
        )
        self.driver.execute_script("arguments[0].click();", completion_tab)
        time.sleep(2)

        def find_doc_links_for(name_text: str):
            nodes = self.driver.find_elements(
                By.XPATH,
                f"//*[contains(normalize-space(), 'Name') and contains(normalize-space(), '{name_text}')]"
            )
            out = []
            for n in nodes:
                candidates = n.find_elements(By.XPATH, "following::a[contains(@href,'download')][1]")
                if candidates:
                    a = candidates[0]
                    t = (a.text or "").strip().lower()
                    if "not" in t and "app" in t:
                        continue
                    out.append(a)
            return out

        oc_links = find_doc_links_for("Occupancy Certificate")
        cc_links = find_doc_links_for("Completion certificate") or find_doc_links_for("Completion Certificate")

        picked = oc_links + cc_links

        seen = set()
        unique = []
        for a in picked:
            href = a.get_attribute("href")
            if href and href not in seen:
                seen.add(href)
                unique.append(a)

        print(f"Found {len(unique)} matching document(s) (OC/CC)")
        for a in unique:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
            time.sleep(0.3)
            self._download_pdf(a)

        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.6)

    # -------------------------------------------------
    # TAB CLICK (RELIABLE)
    # -------------------------------------------------
    def _click_tab_reliably(self, tab_name: str, attempts: int = 4):
        tab_xpath = f"//a[normalize-space()='{tab_name}']"
        last_err = None

        for _ in range(attempts):
            try:
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.4)

                tab = self.wait.until(EC.presence_of_element_located((By.XPATH, tab_xpath)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                time.sleep(0.2)

                try:
                    tab.click()
                except Exception:
                    pass
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(0.8)

                # if this selector doesn't exist on some pages, it won't block downloads
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".tab-pane.active")))
                except Exception:
                    pass

                return
            except Exception as e:
                last_err = e
                time.sleep(0.8)

        raise TimeoutException(f"Could not activate tab: {tab_name}. Last error: {last_err}")

    # -------------------------------------------------
    # DOWNLOAD BY LABEL ANYWHERE ON PAGE (ROW-SAFE)
    # -------------------------------------------------
    def _download_by_label_page(self, label_text: str, max_scroll_steps: int = 80):
        label_upper = re.sub(r"\s+", " ", label_text.strip()).upper()

        def is_visible(el):
            try:
                return el.is_displayed()
            except Exception:
                return False

        def get_visible_roots():
            """
            Karnataka RERA tabs are inconsistent. Try common containers and pick the one visible.
            """
            roots = []
            selectors = [
                ".tab-content",
                ".tab-pane.active",
                ".tab-pane.show.active",
                "div[role='tabpanel']",
                "#tabs-1", "#tabs-2", "#tabs-3", "#tabs-4", "#tabs-5",  # sometimes ids
                "body",
            ]
            for sel in selectors:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for e in els:
                        if is_visible(e):
                            roots.append(e)
                except Exception:
                    pass

            # fallback: body always exists
            if not roots:
                roots = [self.driver.find_element(By.TAG_NAME, "body")]
            return roots

        # case-insensitive contains match
        label_xpath = (
            ".//*[contains(translate(normalize-space(.),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
            f"'{label_upper}')]"
        )

        for _ in range(max_scroll_steps):
            roots = get_visible_roots()

            # search label in any visible root
            label_el = None
            for root in roots:
                try:
                    candidates = [e for e in root.find_elements(By.XPATH, label_xpath) if is_visible(e)]
                    if candidates:
                        # pick smallest (most specific)
                        label_el = min(
                            candidates,
                            key=lambda e: self.driver.execute_script(
                                "return arguments[0].getBoundingClientRect().height || 999999;", e
                            )
                        )
                        break
                except Exception:
                    continue

            if label_el:
                # ✅ nearest link AFTER label in the DOM
# ... after label_el is found

# 1) Try normal href links first
                links = label_el.find_elements(
                    By.XPATH,
                    "following::a[contains(@href,'download') or contains(translate(@href,'PDF','pdf'),'.pdf')]"
                )

                good = []
                for a in links:
                    if not is_visible(a):
                        continue
                    href = a.get_attribute("href") or ""
                    if not href:
                        continue
                    t = (a.text or "").strip().lower()
                    if "not" in t and "app" in t:
                        continue
                    good.append(a)

                if good:
                    # (same logic as before)
                    a = good[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
                    time.sleep(0.2)
                    self._download_pdf(a, fallback_prefix=label_text)
                    return

                # 2) ✅ Fallback: look for clickable download controls near the label (onclick / button)
                row = label_el
                for _ in range(8):  # climb a few parents to get the row container
                    try:
                        # candidates that might trigger download
                        candidates = row.find_elements(By.XPATH, ".//a[@onclick] | .//button[@onclick] | .//a[contains(@class,'download')] | .//button[contains(@class,'download')]")
                        candidates = [c for c in candidates if is_visible(c)]
                        if candidates:
                            # click each candidate; wait; detect new link or new file in download_dir
                            for c in candidates:
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
                                    time.sleep(0.2)
                                    self.driver.execute_script("arguments[0].click();", c)
                                    time.sleep(1.5)

                                    # After click, sometimes an <a href="...download..."> appears
                                    new_links = row.find_elements(By.XPATH, ".//a[contains(@href,'download')]")
                                    new_links = [a for a in new_links if is_visible(a) and (a.get_attribute("href") or "")]
                                    if new_links:
                                        self._download_pdf(new_links[0], fallback_prefix=label_text)
                                        return

                                    # Or the browser directly downloaded (if portal triggers file download)
                                    # In that case, you can just return and rely on Chrome download prefs.
                                    # But since you use requests download, we need a URL.
                                    # If no URL appears, continue trying other candidates.
                                except Exception:
                                    continue

                        row = row.find_element(By.XPATH, "..")
                    except Exception:
                        break

                print(f"⚠️ '{label_text}' found but no downloadable link/control near it. Skipping.")
                return


    # -------------------------------------------------
    # UPLOADED DOCUMENTS: download multiple label-based docs
    # -------------------------------------------------
    def download_uploaded_documents(self):
        print("Opening Uploaded Documents tab...")
        self._click_tab_reliably("Uploaded Documents")
        time.sleep(2)
        for label in ["Approved Layout Plan", "Proforma of Agreement for Sale"]:
            print(f"Downloading by label: {label}")
            self._download_by_label_page(label)

    def download_enquired_documents(self):
        print("Opening Uploaded Documents tab...")
        self._click_tab_reliably("Uploaded Documents")
        time.sleep(2)
        for label in ["All NOCs from Authority", "Encumbrance Certificate"]:
            print(f"Downloading by label: {label}")
            self._download_by_label_page(label)


    # -------------------------------------------------
    # REQUESTS SESSION WITH SELENIUM COOKIES
    # -------------------------------------------------
    def _requests_session_from_selenium(self):
        s = requests.Session()
        try:
            ua = self.driver.execute_script("return navigator.userAgent;")
            s.headers.update({"User-Agent": ua})
        except Exception:
            pass

        for c in self.driver.get_cookies():
            s.cookies.set(c["name"], c["value"])
        return s

    # -------------------------------------------------
    # SAFE FILENAME
    # -------------------------------------------------
    @staticmethod
    def _safe_filename(name: str) -> str:
        name = (name or "").strip()
        name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name).strip()
        if not name:
            name = "document"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return name

    # -------------------------------------------------
    # PDF DOWNLOADER (USE REAL FILENAME)
    # -------------------------------------------------
    def _download_pdf(self, link_element, fallback_prefix: str = "document"):
        pdf_url = link_element.get_attribute("href")
        if not pdf_url:
            return

        s = self._requests_session_from_selenium()
        resp = s.get(pdf_url, timeout=60)
        resp.raise_for_status()

        # ✅ Real filename usually comes from Content-Disposition
        cd = resp.headers.get("Content-Disposition", "") or resp.headers.get("content-disposition", "")
        filename = None
        if "filename=" in cd.lower():
            # handle filename="abc.pdf" and filename=abc.pdf
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\r\n]+)"?', cd, flags=re.IGNORECASE)
            if m:
                filename = m.group(1).strip()

        if not filename:
            # fallback: anchor text OR URL basename OR fallback_prefix
            anchor_text = (link_element.text or "").strip()
            if anchor_text:
                filename = anchor_text
            else:
                path = urlparse(pdf_url).path
                filename = os.path.basename(path) or fallback_prefix

        filename = unquote(filename)
        filename = self._safe_filename(filename)

        # Avoid overwriting (NOC.pdf etc.)
        base, ext = os.path.splitext(filename)
        if not ext:
            ext = ".pdf"
        out_path = os.path.join(self.download_dir, base + ext)
        i = 2
        while os.path.exists(out_path):
            out_path = os.path.join(self.download_dir, f"{base}_{i}{ext}")
            i += 1

        print(f"Downloading: {os.path.basename(out_path)}")
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"✅ Saved: {out_path}")

    # -------------------------------------------------
    # CLEANUP
    # -------------------------------------------------
    def close(self):
        time.sleep(1)
        self.driver.quit()


if __name__ == "__main__":
    bot = KarnatakaRERAWrapper("Prestige Lakeside Habitat", download_dir="downloads", timeout=50)
    try:
        print("🔹 RERA Automation")
        bot.open_project()
        bot.download_completion_documents()
        bot.download_uploaded_documents()
        bot.download_enquired_documents()
    finally:
        bot.close()
