import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.select import Select
from webdriver_manager.chrome import ChromeDriverManager


class BBMPPropertyTaxScraper:

    def __init__(self, pid_number, owner_name, application_number,
                 output_file="bbmp_property_details.xlsx", timeout=40):

        self.pid_number = pid_number
        self.owner_prefix = owner_name[:3].upper()
        self.application_number = application_number
        self.output_file = output_file

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, timeout)

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

    # ---------------- NAVIGATE TO PAYMENT HISTORY ---------------- #
    def open_payment_history(self):
        click_here = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(text(),'click here')]")
            )
        )
        self.driver.execute_script("arguments[0].click();", click_here)

        # Dropdown (Application Number)
        try:
            dropdown = self.wait.until(EC.presence_of_element_located((By.XPATH, "//select")))
            try:
                Select(dropdown).select_by_visible_text("Application Number")
            except:
                pass
        except:
            pass

        app_input = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[contains(@class,'form-control') or contains(@id,'txt')]")
            )
        )
        app_input.clear()
        app_input.send_keys(self.application_number)
        app_input.send_keys("\t")
        time.sleep(1)

        retrieve2 = self.wait.until(
            EC.element_to_be_clickable(
                (By.ID, "ContentPlaceHolder1_ContentPlaceHolder1_Button1")
            )
        )
        self.driver.execute_script("arguments[0].click();", retrieve2)

        print("✅ Payment history loaded")

    # ---------------- EXTRACT TABLE ---------------- #
    def extract_payment_history(self):
        self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//th[contains(text(),'SAS App. No')]")
            )
        )

        # Auto scroll
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        table = self.driver.find_element(
            By.XPATH, "//table[.//th[contains(text(),'SAS App. No')]]"
        )

        headers = [h.text.strip() for h in table.find_elements(By.XPATH, ".//th")]
        rows = table.find_elements(By.XPATH, ".//tr")[1:]

        data = []
        for row in rows:
            cells = row.find_elements(By.XPATH, ".//td")
            data.append([c.text.strip() for c in cells])

        df = pd.DataFrame(data, columns=headers)
        df.to_excel(self.output_file, index=False)

        print(f"✅ Property tax data saved: {self.output_file}")
        return df

    # ---------------- RUN ---------------- #
    def run(self):
        try:
            self.open_site()
            self.retrieve_property()
            self.open_payment_history()
            return self.extract_payment_history()
        finally:
            self.driver.quit()
            print("✅ BBMP browser closed")