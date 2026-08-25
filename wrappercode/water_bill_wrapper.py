import os
import time
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from webdriver_manager.chrome import ChromeDriverManager


class WaterBillScraper:

    def __init__(
        self,
        rr_number,
        timeout=40,
        headless=False,
        session_id=None,
        screenshot_dir=None,
    ):

        self.rr_number = rr_number
        self.url = "https://www.karnatakaone.gov.in/"
        self.session_id = session_id
        self.screenshot_dir = screenshot_dir

        options = Options()

        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        self.wait = WebDriverWait(self.driver, timeout)

    # ---------------------------------------------------
    # OPEN WEBSITE
    # ---------------------------------------------------

    def open_site(self):

        print("Opening KarnatakaOne...")
        for _ in range(3):

            self.driver.get(self.url)

            try:

                self.wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//a[normalize-space()='Quick Pay']")
                    )
                )

                return

            except Exception:
                time.sleep(2)
            self.close_popup()
        raise Exception("Unable to load KarnatakaOne")

    # ---------------------------------------------------
    # NAVIGATION
    # ---------------------------------------------------
    def close_popup(self):
        try:
            self.wait.until(
                EC.presence_of_element_located(
                    (By.ID, "BTPModal")
                )
            )

            self.driver.execute_script("""

                var popup=document.getElementById("BTPModal");

                if(popup){
                    popup.remove();
                }

                document.querySelectorAll(".modal-backdrop")
                        .forEach(x=>x.remove());

                document.body.classList.remove("modal-open");
                document.body.style.overflow="auto";

            """)

            print("Traffic popup removed")

            time.sleep(1)

        except Exception as e:
            print("Popup not found:", e)

    def navigate_to_water_bill(self):

        print("Navigating...")

        quick_pay = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[normalize-space()='Quick Pay']")
            )
        )

        self.driver.execute_script(
            """
            arguments[0].scrollIntoView({block:'center'});
            arguments[0].click();
            """,
            quick_pay
        )

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
            EC.visibility_of_element_located(
                (By.ID, "collapse1")
            )
        )

        services = panel.find_element(
            By.XPATH,
            ".//a[normalize-space()='Services']"
        )

        self.driver.execute_script(
            "arguments[0].click();",
            services
        )

        water_bill = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//a[contains(text(),'Water Bill')]"
                )
            )
        )

        self.driver.execute_script(
            "arguments[0].click();",
            water_bill
        )

        time.sleep(2)

    # ---------------------------------------------------
    # RR NUMBER
    # ---------------------------------------------------

    def enter_rr_number(self):

        print("Entering RR Number...")

        rr = self.wait.until(
            EC.visibility_of_element_located(
                (By.ID, "SearchRRNumber")
            )
        )

        rr.clear()

        rr.send_keys(self.rr_number)

        print("RR:", rr.get_attribute("value"))

        search = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@value='Search']")
            )
        )

        self.driver.execute_script(
            "arguments[0].click();",
            search
        )

        # Invalid RR detection

        try:

            err = WebDriverWait(
                self.driver,
                5
            ).until(

                EC.visibility_of_element_located(

                    (
                        By.XPATH,
                        "//*[contains(text(),'No Records') or contains(text(),'Invalid')]"
                    )

                )

            )

            raise Exception(err.text)

        except TimeoutException:
            pass

    # ---------------------------------------------------
    # FETCH DATA
    # ---------------------------------------------------

    def fetch_bill_details(self):

        print("Reading bill...")

        self.wait.until(

            EC.visibility_of_element_located(

                (
                    By.XPATH,
                    "//*[contains(text(),'Consumer Name')]"
                )

            )

        )

        def value(xpath):

            e = self.driver.find_element(
                By.XPATH,
                xpath
            )

            return self.driver.execute_script(

                """
                return arguments[0].value ||
                       arguments[0].innerText ||
                       arguments[0].textContent;
                """,

                e

            ).strip()

        amount = value(
            "//*[contains(text(),'Bill Amount')]/ancestor::div[contains(@class,'form-group')]//input"
        )

        amount = (
            amount
            .replace("₹", "")
            .replace(",", "")
            .strip()
        )

        try:
            amount = float(amount)
        except:
            amount = None

        return {

            "status": "SUCCESS",

            "risk_score": 0,

            "rr_number": self.rr_number,

            "consumer_name": value(
                "//*[contains(text(),'Consumer Name')]/ancestor::div[contains(@class,'form-group')]//input"
            ),

            "consumer_address": value(
                "//*[contains(text(),'Consumer Address')]/ancestor::div[contains(@class,'form-group')]//input"
            ),

            "bill_number": value(
                "//*[contains(text(),'Bill Number')]/ancestor::div[contains(@class,'form-group')]//input"
            ),

            "bill_date": value(
                "//*[contains(text(),'Bill Date')]/ancestor::div[contains(@class,'form-group')]//input"
            ),

            "bill_amount": amount

        }

    # ---------------------------------------------------
    # RUN
    # ---------------------------------------------------

    def run(self):

        try:

            self.open_site()

            self.navigate_to_water_bill()

            self.enter_rr_number()

            return self.fetch_bill_details()

        except Exception as e:

            return {

                "status": "FAILED",

                "risk_score": None,

                "error": str(e)

            }

        finally:

            try:

                if self.screenshot_dir and self.session_id:

                    os.makedirs(
                        self.screenshot_dir,
                        exist_ok=True
                    )

                    self.driver.save_screenshot(

                        os.path.join(

                            self.screenshot_dir,

                            f"water_result_{self.session_id}.png"

                        )

                    )

            except Exception as ex:

                print("Screenshot Error:", ex)

            try:

                self.driver.quit()

            except:
                pass

            print("Browser Closed")


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

if __name__ == "__main__":

    RR_NUMBER = "N-435608"      # Change to your RR Number
    scraper = WaterBillScraper(
        rr_number=RR_NUMBER,
        headless=False
    )

    result = scraper.run()

    print("\nRESULT\n")

    print(json.dumps(result, indent=4))