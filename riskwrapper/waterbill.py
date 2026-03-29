import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


class WaterBillFetcher:

    def __init__(self, session_id=None, screenshot_dir=None):
        self.session_id = session_id
        self.screenshot_dir = screenshot_dir
        options = Options()
        options.add_argument("--start-maximized")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        self.wait = WebDriverWait(self.driver, 40)

    def fetch_by_rr(self, rr_number):
        try:
            self.driver.get("https://www.karnatakaone.gov.in/")

            self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[normalize-space()='Quick Pay']")
            )).click()

            self.driver.execute_script("""
                [...document.querySelectorAll('*')]
                .find(e => e.textContent.trim() === 'SELECT CITY')?.click();
            """)

            self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@class,'modal')]//a[normalize-space()='Bengaluru']")
                )
            ).click()

            panel = self.wait.until(
                EC.visibility_of_element_located((By.ID, "collapse1"))
            )

            services = panel.find_element(
                By.XPATH, ".//a[normalize-space()='Services']"
            )
            self.driver.execute_script("arguments[0].click();", services)

            water_bill = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(),'Water Bill')]")
                )
            )
            self.driver.execute_script("arguments[0].click();", water_bill)

            rr_input = self.wait.until(
                EC.visibility_of_element_located((By.ID, "SearchRRNumber"))
            )

            self.driver.execute_script("""
                arguments[0].scrollIntoView({block:'center'});
                arguments[0].click();
                arguments[0].value='';
            """, rr_input)

            # ✅ FIXED
            for ch in rr_number:
                rr_input.send_keys(ch)
                time.sleep(0.1)

            print("RR FIELD VALUE:", rr_input.get_attribute("value"))

            search_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='Search']")
                )
            )
            self.driver.execute_script("arguments[0].click();", search_btn)

            self.wait.until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Consumer Name')]")
                )
            )
            time.sleep(2)

            def get_text(el):
                return self.driver.execute_script(
                    "return arguments[0].value || arguments[0].innerText || arguments[0].textContent;",
                    el
                ).strip()

            consumer_name = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//*[contains(text(),'Consumer Name')]/ancestor::div[contains(@class,'form-group')]//input")
                )
            )

            consumer_address = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//*[contains(text(),'Consumer Address')]/ancestor::div[contains(@class,'form-group')]//input")
                )
            )

            bill_number = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//*[contains(text(),'Bill Number')]/ancestor::div[contains(@class,'form-group')]//input")
                )
            )

            bill_date = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//*[contains(text(),'Bill Date')]/ancestor::div[contains(@class,'form-group')]//input")
                )
            )

            bill_amount = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//*[contains(text(),'Bill Amount')]/ancestor::div[contains(@class,'form-group')]//input")
                )
            )

            return {
                "RR Number": rr_number,   # ✅ FIXED
                "Consumer Name": get_text(consumer_name),
                "Consumer Address": get_text(consumer_address),
                "Bill Number": get_text(bill_number),
                "Bill Date": get_text(bill_date),
                "Bill Amount": get_text(bill_amount)
            }
        finally:
            # Capture screenshot
            if self.screenshot_dir and self.session_id:
                import os
                os.makedirs(self.screenshot_dir, exist_ok=True)
                path = os.path.join(self.screenshot_dir, f"water_result_{self.session_id}.png")
                self.driver.save_screenshot(path)
                print(f"DEBUG: Saved WATER screenshot to {path}")
    def close(self):
        self.driver.quit()
