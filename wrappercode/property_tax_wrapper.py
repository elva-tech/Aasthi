import os
import time
import pandas as pd
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.select import Select
from webdriver_manager.chrome import ChromeDriverManager


class BBMPPropertyTaxScraper:
   


    def __init__(self, pid_number, owner_name, timeout=40):

        self.pid_number = pid_number
        self.owner_prefix = owner_name[:3].upper()

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, timeout)

    def clear_old_screenshots(self):
        screenshot_dir = "tax_screenshots"

        os.makedirs(screenshot_dir, exist_ok=True)

        for file in glob.glob(os.path.join(screenshot_dir, "*.png")):
            try:
                os.remove(file)
                print(f"Deleted old screenshot: {os.path.basename(file)}")
            except Exception as e:
                print(f"Could not delete {file}: {e}")

    # ---------------- OPEN SITE ---------------- #
    def open_site(self):
        print("Opening BBMP Property Tax portal...")
        self.driver.get("https://bbmptax.karnataka.gov.in/")
        time.sleep(3)

    # ---------------- INITIAL RETRIEVE ---------------- #
    def retrieve_property(self):
        pid_input = self.wait.until(
            EC.presence_of_element_located(
                (By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_txtddlno")
            )
        )
        pid_input.clear()
        pid_input.send_keys(self.pid_number)

        owner_input = self.wait.until(
            EC.presence_of_element_located(
                (By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_txtname")
            )
        )
        owner_input.clear()
        owner_input.send_keys(self.owner_prefix)

        retrieve_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@value='Retrieve' or contains(@id,'btnRetrieve')]")
            )
        )
        self.driver.execute_script("arguments[0].click();", retrieve_btn)

        time.sleep(3)

        confirm_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[contains(@class,'btn-success') or @value='Confirm']")
            )
        )
        self.driver.execute_script("arguments[0].click();", confirm_btn)

    def wait_for_captcha_and_proceed(self):

        print("\n==============================")
        print("ENTER CAPTCHA MANUALLY")
        print("Waiting for Proceed button...")
        print("==============================\n")

        old_url = self.driver.current_url

        WebDriverWait(self.driver, 300).until(
            lambda d: d.current_url != old_url
        )

        print("✅ Proceed detected")
        time.sleep(10)
# ---------------- SCREENSHOTS ---------------- #
    time.sleep(5)
    def capture_full_page(self):

        screenshot_dir = "tax_screenshots"

        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        time.sleep(5)

        total_height = self.driver.execute_script(
            """
            return Math.max(
                document.body.scrollHeight,
                document.documentElement.scrollHeight
            );
            """
        )

        viewport_height = self.driver.execute_script(
            "return window.innerHeight;"
        )

        print("Total Height:", total_height)

        part = 1

        for y in range(
            0,
            total_height,
            viewport_height
        ):

            self.driver.execute_script(
                f"window.scrollTo(0,{y});"
            )

            time.sleep(2)

            filename = os.path.join(
                screenshot_dir,
                f"tax_page_{part}.png"
            )

            self.driver.save_screenshot(
                filename
            )

            print("📸", filename)

            part += 1

        self.driver.execute_script(
            "window.scrollTo(0,0);"
        )

    # ---------------- RUN ---------------- #
    def run(self):

        try:
            self.clear_old_screenshots()
            self.open_site()

            self.retrieve_property()

            self.wait_for_captcha_and_proceed()

            self.capture_full_page()


            print("✅ Screenshots completed")

        finally:

            self.driver.quit()

            print("Browser closed")
if __name__ == "__main__":

    scraper = BBMPPropertyTaxScraper(
        pid_number="1500082907",
        owner_name="RAM",
    )

    scraper.run()