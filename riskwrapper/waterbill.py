import os
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

            self.wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            time.sleep(2)

            # ---------------- Close Traffic Popup ----------------
            try:
                close_btn = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#BTPModal .close.close-btn")
                    )
                )

                self.driver.execute_script(
                    "arguments[0].click();",
                    close_btn
                )

                # Remove Bootstrap backdrop if it remains
                self.driver.execute_script("""
                    document.querySelectorAll('.modal-backdrop')
                        .forEach(e => e.remove());

                    document.body.classList.remove('modal-open');
                    document.body.style.overflow='auto';
                """)

                time.sleep(1)

                print("Traffic popup closed")

            except Exception as e:
                print("Traffic popup not found:", e)

            # ---------------- Quick Pay ----------------
            quick_pay = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[normalize-space()='Quick Pay']")
                )
            )

            self.driver.execute_script("""
                arguments[0].scrollIntoView({block:'center'});
            """, quick_pay)

            time.sleep(0.5)

            self.driver.execute_script(
                "arguments[0].click();",
                quick_pay
            )

            print("Quick Pay opened")
            self.driver.execute_script("""
                [...document.querySelectorAll('*')]
                .find(e => e.textContent.trim() === 'SELECT CITY')
                ?.click();
            """)

            self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//div[contains(@class,'modal')]//a[normalize-space()='Bengaluru']"
                    )
                )
            ).click()

            self.wait.until(
                EC.invisibility_of_element_located(
                    (By.CLASS_NAME, "modal")
                )
            )

            time.sleep(2)
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
            self.save_water_evidence_screenshot()

            return {
                "RR Number": rr_number,   # ✅ FIXED
                "Consumer Name": get_text(consumer_name),
                "Consumer Address": get_text(consumer_address),
                "Bill Number": get_text(bill_number),
                "Bill Date": get_text(bill_date),
                "Bill Amount": get_text(bill_amount)
            }
        except Exception as e:
            raise e
    def save_water_evidence_screenshot(self):
        """
        Capture the water bill details section.
        """

        if not (self.screenshot_dir and self.session_id):
            return

        os.makedirs(self.screenshot_dir, exist_ok=True)

        path = os.path.join(
            self.screenshot_dir,
            f"water_result_{self.session_id}.png"
        )

        try:

            # Scroll to details
            element = self.driver.find_element(
                By.XPATH,
                "//*[contains(text(),'Consumer Name')]"
            )

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                element
            )

            time.sleep(1)

            # Capture the complete details card
            bill_section = self.driver.find_element(
                By.XPATH,
                "//*[contains(text(),'Consumer Name')]/ancestor::div[contains(@class,'panel-body')][1]"
            )

            bill_section.screenshot(path)

            print(f"Saved WATER evidence screenshot → {path}")

        except Exception as e:

            print(f"Panel screenshot failed: {e}")

            try:

                # Capture whole page as fallback
                self.driver.save_screenshot(path)

                print(f"Saved full page screenshot → {path}")

            except Exception as ex:

                print(f"Screenshot failed: {ex}")
                
    def close(self):
        self.driver.quit()
