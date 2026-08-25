# ekhata.py — BBMP Citizen Core eKhata download
# pip install selenium

import argparse
import glob
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC




class EKhataBot:
    import glob

#def clear_old_downloads(self):

 #       for file in glob.glob(
  #          os.path.join(self.download_dir, "*.pdf")
   #     ):
    #        try:
    #            os.remove(file)
    #        except Exception:
    #              pass 
    def __init__(self):

        BASE_DIR = r"D:\aasthiv2\Aasthi\wrappercode"

        self.download_dir = os.path.join(
            BASE_DIR,
            "input",
            "ekhata"
        )

        os.makedirs(self.download_dir, exist_ok=True)

        options = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--start-maximized")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 30)

    def run(self, search_type="epid", search_value="", wait_seconds=60):
        driver = self.driver
        wait = self.wait

        try:
           # self.clear_old_downloads()
            driver.get("https://bbmpeaasthi.karnataka.gov.in/citizen_core/")
            print("Citizen Core opened")

            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Welcome to Faceless')]")
                )
            )

            radio_map = {
                "ward": "Ward Name or Ward Number",
                "epid": "Property ePID",
                "sas": "SAS Property Tax ID",
            }

            radio_text = radio_map[search_type.lower()]

            radio_btn = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//span[contains(text(),'{radio_text}')]")
                )
            )

            driver.execute_script("arguments[0].click();", radio_btn)
            print("Selected:", radio_text)

            search_box = wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='text']"))
            )
            search_box.clear()
            search_box.send_keys(search_value)
            print("Entered:", search_value)

            search_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(.,'Search')]")
                )
            )
            driver.execute_script("arguments[0].click();", search_btn)
            print("Search clicked")
            time.sleep(2)

            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//table//tbody//tr")
                )
            )
            print("Results loaded")
            time.sleep(3)
            # --------------------------------------------------
            # Click eKhata button
            # --------------------------------------------------

            ekhata_btn = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//tbody//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ekhata')]"
                    )
                )
            )

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                ekhata_btn
            )

            driver.execute_script("arguments[0].click();", ekhata_btn)

            print("eKhata clicked")
           
            # --------------------------------------------------
            # Wait for PDF dialog
            # --------------------------------------------------
            
            iframe = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "iframe[title='PDF Viewer']")
                )
            )

            print("PDF dialog opened")

            # give viewer time to load
            time.sleep(5)

            # --------------------------------------------------
            # Switch into iframe
            # --------------------------------------------------

            driver.switch_to.frame(iframe)

            time.sleep(5)

            # --------------------------------------------------
            # Click Download button inside Chrome PDF viewer
            # --------------------------------------------------

            download_clicked = driver.execute_script("""
            function findDownloadButton() {

                const viewer = document.querySelector('pdf-viewer');
                if (!viewer) return null;

                const viewerRoot = viewer.shadowRoot;
                if (!viewerRoot) return null;

                const toolbar = viewerRoot.querySelector('viewer-toolbar');
                if (!toolbar) return null;

                const toolbarRoot = toolbar.shadowRoot;
                if (!toolbarRoot) return null;

                const downloads =
                    toolbarRoot.querySelector('viewer-download-controls');
                if (!downloads) return null;

                const downloadsRoot = downloads.shadowRoot;
                if (!downloadsRoot) return null;

                return downloadsRoot.querySelector('#save');
            }

            const btn = findDownloadButton();

            if (btn) {
                btn.click();
                return true;
            }

            return false;
            """)

            print("Download clicked:", download_clicked)

            # --------------------------------------------------
            # Back to main page
            # --------------------------------------------------

            driver.switch_to.default_content()

            # --------------------------------------------------
            # Wait for download
            # --------------------------------------------------

            print("Waiting for PDF download...")

            timeout = time.time() + 60

            while time.time() < timeout:

                pdfs = [
                    f for f in os.listdir(self.download_dir)
                    if f.lower().endswith(".pdf")
                ]

                if pdfs:

                    latest_pdf = max(
                        [os.path.join(self.download_dir, f) for f in pdfs],
                        key=os.path.getmtime
                    )

                    print("Downloaded PDF:", latest_pdf)
                    return latest_pdf

                time.sleep(1)

            print("PDF not downloaded")

        except Exception as e:
            print("General Error:", e)
            raise

    def close(self):
        self.driver.quit()


def main():
    parser = argparse.ArgumentParser(description="BBMP eKhata automation")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search property and open eKhata")
    search.add_argument(
        "--search-type",
        choices=["epid", "sas", "ward"],
        default="epid",
    )
    search.add_argument("--search-value", required=True)
    search.add_argument("--wait-seconds", type=int, default=60)

    args = parser.parse_args()

    if args.command == "search":
        bot = EKhataBot()
        try:
            bot.run(
                search_type=args.search_type,
                search_value=args.search_value,
                wait_seconds=args.wait_seconds,
            )
        finally:
            bot.close()


if __name__ == "__main__":
    main()
