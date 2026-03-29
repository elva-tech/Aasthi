import os
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class BESCOMBillScraper:

    def __init__(self, account_id):
        self.account_id = account_id
        self.url = "https://www.bescom.co.in/bescom/main/quick-payment"

        # Create folder by Account ID
        self.base_dir = os.path.join(os.getcwd(), self.account_id)
        os.makedirs(self.base_dir, exist_ok=True)

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")

        # 🔑 FORCE DOWNLOADS INTO ACCOUNT FOLDER
        prefs = {
            "download.default_directory": self.base_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 40)

    # ---------------- SAFE CLICK (CONTAINS) ---------------- #
    def safe_click_by_text(self, text):
        btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//button[.//text()[contains(.,'{text}')]]")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", btn
        )
        time.sleep(0.4)
        self.driver.execute_script("arguments[0].click();", btn)

    # ---------------- SAFE CLICK (EXACT) ---------------- #
    def safe_click_by_exact_text(self, text):
        btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//button[normalize-space()='{text}']")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", btn
        )
        time.sleep(0.4)
        self.driver.execute_script("arguments[0].click();", btn)

    # ---------------- ENTER ACCOUNT ---------------- #
    def enter_account_id(self):
        self.driver.get(self.url)

        acc_input = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@placeholder='Account No.']")
            )
        )
        acc_input.clear()
        acc_input.send_keys(self.account_id)
        print("✅ Account ID entered")

    # ---------------- CAPTCHA (MANUAL) ---------------- #
    def wait_for_manual_captcha(self):
        print("\n==============================")
        print("ENTER CAPTCHA MANUALLY")
        print("Click CONTINUE yourself")
        print("==============================\n")

        continue_btn = self.driver.find_element(
            By.XPATH, "//button[contains(text(),'Continue')]"
        )

        self.wait.until(EC.staleness_of(continue_btn))
        print("✅ CAPTCHA verified")

    # ---------------- TRANSACTION HISTORY ---------------- #
    def transaction_history(self):
        self.safe_click_by_text("View All Transaction History")

        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//h1[normalize-space()='Payments History']")
            )
        )

        all_rows = []

        while True:
            rows = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, "//table/tbody/tr[td or th]")
                )
            )

            for row in rows:
                cells = row.find_elements(By.XPATH, "./th | ./td")
                values = [c.text.strip() for c in cells]
                if len(values) == 4:
                    all_rows.append(values)

            try:
                next_btn = self.driver.find_element(
                    By.XPATH, "//a[normalize-space()='Next']"
                )

                if "disabled" in next_btn.get_attribute("class"):
                    break

                self.driver.execute_script("arguments[0].click();", next_btn)
                self.wait.until(EC.staleness_of(rows[0]))
                time.sleep(1)

            except:
                break

        df = pd.DataFrame(
            all_rows,
            columns=[
                "Payment ID",
                "Receipt ID",
                "Payment Date",
                "Payment Amount"
            ]
        )

        df.to_excel(
            os.path.join(self.base_dir, "transaction_history.xlsx"),
            index=False
        )

        print(f"📊 {len(df)} transactions saved")

        self.safe_click_by_exact_text("Close")

    # ---------------- DOWNLOAD BILL ---------------- #
    def download_bill(self):
        self.safe_click_by_exact_text("Download Bill")
        print("⬇ Bill downloaded into account folder")
        time.sleep(5)

    # ---------------- RUN ---------------- #
    def run(self):
        try:
            self.enter_account_id()
            self.wait_for_manual_captcha()
            self.transaction_history()
            self.download_bill()

        finally:
            time.sleep(2)
            self.driver.quit()
            print("✅ Browser closed")


# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    ACCOUNT_ID = "7220755000"

    bot = BESCOMBillScraper(ACCOUNT_ID)
    bot.run()
